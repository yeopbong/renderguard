"""Train and compare observation models with family-separated development and calibration."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time
import numpy as np
import torch
from safetensors.torch import save_file, load_file
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from .model import ObservationModel, LABELS, INPUT_NAMES, masked_bce
from .metrics import metrics, thresholds, calibrate, apply_calibration, reliability
from .prepare import STRIDE

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False));temp.replace(path)

def arrays():
    rows=[json.loads(s) for s in Path('artifacts/candidates.jsonl').read_text().splitlines()]
    x=np.memmap('data/tensors/all.f32',dtype=np.float32,mode='r',shape=(len(rows),STRIDE))
    y=np.array([[float(v is True) for v in r['labels']] for r in rows],dtype=np.float32)
    mask=np.array([[float(v is not None) for v in r['labels']] for r in rows],dtype=np.float32)
    splits={s:np.array([i for i,r in enumerate(rows) if r['split']==s]) for s in ['train','dev','calibration','test']}
    return rows,x,y,mask,splits

def inputs(x,index,device):
    a=torch.tensor(np.asarray(x[index]),device=device)
    n=len(index);image=3*96*96
    return [a[:,i*image:(i+1)*image].reshape(n,3,96,96) for i in range(4)]+[a[:,-12:]]

def predict(model,x,indices,device,batch=24):
    model.eval();output=[]
    with torch.no_grad():
        for k in range(0,len(indices),batch):output.append(model(*inputs(x,indices[k:k+batch],device)).cpu().numpy())
    return np.concatenate(output) if output else np.empty((0,5),dtype=np.float32)

def train_one(x,y,mask,splits,seed,kind,device,epochs=6):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    model=ObservationModel(context=kind!='local_only',pretrained=True).to(device)
    initial={k:v.detach().cpu().clone() for k,v in model.encoder.state_dict().items()}
    tr=splits['train'];dev=splits['dev'];positive=(y[tr]*mask[tr]).sum(0);negative=((1-y[tr])*mask[tr]).sum(0)
    weight=torch.tensor(np.minimum(negative/np.maximum(positive,1),10),device=device,dtype=torch.float32)
    log=[];best=None;best_loss=float('inf');rng=np.random.default_rng(seed);start=time.monotonic()
    # Warm up heads from cached generic visual features. No labels enter feature extraction.
    model.eval();features=[]
    with torch.no_grad():
        for k in range(0,len(tr),24):features.append(model.features(*inputs(x,tr[k:k+24],device)).cpu())
    feature_tensor=torch.cat(features).to(device);ty=torch.tensor(y[tr],device=device);tm=torch.tensor(mask[tr],device=device)
    for epoch in range(epochs):
        fine=kind!='frozen' and epoch>=2;model.train();model.set_stage(fine)
        optimizer=torch.optim.AdamW([{'params':model.head.parameters(),'lr':.001 if not fine else .0004},{'params':[p for p in model.encoder.parameters() if p.requires_grad],'lr':.0001}],weight_decay=.001)
        total=0.;count=0;gradient=0.
        order=rng.permutation(len(tr));batch=24 if fine else 64
        for offset in range(0,len(order),batch):
            local=order[offset:offset+batch];idx=tr[local];optimizer.zero_grad(set_to_none=True)
            logits=model(*inputs(x,idx,device)) if fine else model.head(feature_tensor[local])
            loss=masked_bce(logits,torch.tensor(y[idx],device=device),torch.tensor(mask[idx],device=device),weight)
            loss.backward();gradient+=sum(float(p.grad.detach().norm().cpu()) for p in model.encoder.parameters() if p.grad is not None)
            torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step();total+=float(loss.detach().cpu())*len(idx);count+=len(idx)
        prediction=predict(model,x,dev,device)
        valid_loss=float(masked_bce(torch.from_numpy(prediction),torch.from_numpy(y[dev]),torch.from_numpy(mask[dev])))
        entry={'epoch':epoch+1,'stage':'finetune' if fine else 'head','trainLoss':total/count,'devLoss':valid_loss,'encoderGradientNormSum':gradient,'elapsedSeconds':time.monotonic()-start};log.append(entry);print(kind,seed,json.dumps(entry),flush=True)
        # A finetuned model must be released for finetuning experiments; warm-up remains a baseline.
        if valid_loss<best_loss and (fine or kind=='frozen'):
            best_loss=valid_loss;best={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
    model.load_state_dict(best);model.eval()
    delta={k:float((v.detach().cpu()-initial[k]).abs().max()) for k,v in model.encoder.state_dict().items() if v.dtype.is_floating_point}
    bn_keys=[k for k in initial if 'running_' in k]
    frozen_bn=all(torch.equal(model.encoder.state_dict()[k].cpu(),initial[k]) for k in bn_keys)
    assert frozen_bn
    if kind!='frozen':assert max(delta.values())>0
    else:assert max(delta.values())==0
    directory=Path('artifacts/checkpoints');directory.mkdir(parents=True,exist_ok=True);weights=directory/f'{kind}-{seed}.safetensors';save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(weights))
    check=ObservationModel(context=kind!='local_only').to(device);check.load_state_dict(load_file(str(weights)));check.eval()
    idx=dev[:3];error=float(np.max(np.abs(predict(model,x,idx,device)-predict(check,x,idx,device))));assert error<1e-6
    evidence={'kind':kind,'seed':seed,'curve':log,'encoderMaxWeightChange':max(delta.values()),'batchNormUnchanged':frozen_bn,'reloadMaxError':error,'seconds':time.monotonic()-start,'weightsSha256':sha(weights)}
    return model,evidence

def baseline(x,y,mask,splits):
    tr,dev,te=splits['train'],splits['dev'],splits['test'];geometry=np.asarray(x[:,-12:]).copy();allp=np.zeros_like(y)
    for j in range(5):
        known=tr[mask[tr,j].astype(bool)]
        clf=LogisticRegression(max_iter=1000,class_weight='balanced',random_state=17).fit(geometry[known],y[known,j]);allp[:,j]=clf.predict_proba(geometry)[:,1]
    cut=thresholds(y[dev],allp[dev],mask[dev]);out={'difference_statistics':{'dev':metrics(y[dev],allp[dev],mask[dev],cut),'test':metrics(y[te],allp[te],mask[te],cut),'thresholds':cut}}
    pixel=np.repeat(np.minimum(1,geometry[:,4:5]),5,axis=1);pcut=thresholds(y[dev],pixel[dev],mask[dev]);out['pixel_difference']={'dev':metrics(y[dev],pixel[dev],mask[dev],pcut),'test':metrics(y[te],pixel[te],mask[te],pcut),'thresholds':pcut}
    prior=np.repeat(((y[tr]*mask[tr]).sum(0)/mask[tr].sum(0))[None,:],len(te),axis=0);out['uninformed_prior']={'test':metrics(y[te],prior,mask[te],[.5]*5)}
    return out

def export(model,output,example):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);model=model.cpu().eval()
    args=tuple(t.cpu() for t in example)
    torch.onnx.export(model,args,str(output),input_names=INPUT_NAMES,output_names=['logits'],dynamic_axes={n:{0:'batch'} for n in INPUT_NAMES+['logits']},opset_version=17,dynamo=False)
    import onnxruntime as ort
    session=ort.InferenceSession(str(output),providers=['CPUExecutionProvider'])
    with torch.no_grad():expected=model(*args).numpy()
    actual=session.run(None,{name:t.numpy() for name,t in zip(INPUT_NAMES,args)})[0]
    error=float(np.max(np.abs(expected-actual)));assert error<1e-4,error
    return {'maxAbsoluteError':error,'batch':len(args[0]),'tolerance':1e-4,'opset':17,'bytes':output.stat().st_size}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--epochs',type=int,default=6);parser.add_argument('--device',default='auto');parser.add_argument('--seeds',default='17,29,43');args=parser.parse_args()
    os.chdir(ROOT);torch.set_num_threads(4);torch.hub.set_dir(str(ROOT/'data/pretrained'))
    device='mps' if args.device=='auto' and torch.backends.mps.is_available() else 'cpu' if args.device=='auto' else args.device
    if args.preflight:
        model=ObservationModel(pretrained=True);example=[torch.randn(1,3,96,96) for _ in range(4)]+[torch.randn(1,12)];result=export(model,'artifacts/preflight.onnx',example);atomic_json('artifacts/onnx-preflight.json',result);print(result);return
    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    rows,x,y,mask,splits=arrays();start=time.monotonic();all_results=baseline(x,y,mask,splits);experiments=[];chosen=None;chosen_dev=-1;chosen_seed=None
    for kind in ['frozen','local_only','local_context']:
        for seed in map(int,args.seeds.split(',')):
            model,evidence=train_one(x,y,mask,splits,seed,kind,device,args.epochs)
            devlog=predict(model,x,splits['dev'],device);testlog=predict(model,x,splits['test'],device);cut=thresholds(y[splits['dev']],expit(devlog),mask[splits['dev']]);devmetric=metrics(y[splits['dev']],expit(devlog),mask[splits['dev']],cut)
            # Selection depends only on development performance; test metrics are recorded afterwards.
            if kind=='local_context' and devmetric['macroPrAuc']>chosen_dev:chosen={k:v.detach().cpu().clone() for k,v in model.state_dict().items()};chosen_dev=devmetric['macroPrAuc'];chosen_seed=seed
            evidence.update(dev=devmetric,test=metrics(y[splits['test']],expit(testlog),mask[splits['test']],cut),thresholds=cut)
            np.savez_compressed(f'artifacts/checkpoints/{kind}-{seed}-predictions.npz',dev=devlog,test=testlog)
            experiments.append(evidence);atomic_json('artifacts/experiments.json',{'baselines':all_results,'models':experiments,'selection':'maximum development macro PR-AUC among local_context seeds','device':device,'elapsedSeconds':time.monotonic()-start})
            del model
            if device=='mps':torch.mps.empty_cache()
    model=ObservationModel().to(device);model.load_state_dict(chosen);model.eval();cal=splits['calibration'];dev=splits['dev'];test=splits['test'];cal_logits=predict(model,x,cal,device);classes=calibrate(cal_logits,y[cal],mask[cal]);dev_logits=predict(model,x,dev,device);test_logits=predict(model,x,test,device)
    dev_score=apply_calibration(dev_logits,classes);test_score=apply_calibration(test_logits,classes);cut=thresholds(y[dev],dev_score,mask[dev]);dest=Path('web/public/models');dest.mkdir(parents=True,exist_ok=True)
    numerical=export(model,dest/'model.onnx',inputs(x,dev[:3],device));save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},'artifacts/model.safetensors');model_hash=sha(dest/'model.onnx')
    preprocessor=json.loads(Path('data/tensors/requests.json').read_text())[0]['output'];metadata=json.loads(Path(preprocessor+'.json').read_text());version=metadata.get('version',metadata.get('analysis',{}).get('version','1'))
    calibration={'modelSha256':model_hash,'preprocessVersion':version,'target':'candidate visual observation frequency on original synthetic calibration families','classes':classes};atomic_json(dest/'calibration.json',calibration)
    manifest={'version':'0.1.0-rc.1','architecture':'shared MobileNetV3-Small / ordered local and context pair fusion / 128-unit head','sha256':model_hash,'modelSha256':model_hash,'preprocessVersion':version,'labels':LABELS,'inputSize':96,'geometrySize':12,'inputs':INPUT_NAMES,'output':'logits','thresholds':cut,'weightsSha256':sha('artifacts/model.safetensors'),'calibrationSha256':sha(dest/'calibration.json'),'calibration':'calibration.json','seed':chosen_seed,'initialization':'timm mobilenetv3_small_100.lamb_in1k at 1824797e7887cbec1990e4adbd6675960a36c589','trainingSourceSha':source_sha,'dataSha256':sha('artifacts/data-manifest.jsonl'),'groupsSha256':sha('artifacts/groups.json'),'sourceHashes':{str(p):sha(p) for p in sorted(Path('ml').glob('*')) if p.is_file()},'upstreamWeightsSha256':sha('data/pretrained/timm-mobilenetv3.safetensors'),'license':'Apache-2.0 for the pretrained and derived model; see docs/model.md','scope':'Research review assistant for tested synthetic scenes; scores are observations, not defect probabilities.'}
    atomic_json(dest/'manifest.json',manifest)
    final={'selectedSeed':chosen_seed,'selectionDevMacroPrAuc':chosen_dev,'calibratedTest':metrics(y[test],test_score,mask[test],cut),'calibration':reliability(y[cal],apply_calibration(cal_logits,classes),mask[cal]),'testReliability':reliability(y[test],test_score,mask[test]),'onnx':numerical,'device':device,'platform':platform.platform(),'torch':torch.__version__,'seconds':time.monotonic()-start,'candidateCount':len(rows),'families':{s:sorted(set(rows[i]['family'] for i in inds)) for s,inds in splits.items()}}
    atomic_json('artifacts/model-results.json',final);np.savez_compressed('artifacts/final-predictions.npz',test=test_logits,calibration=cal_logits,dev=dev_logits);print(json.dumps(final,indent=2))

if __name__=='__main__':main()
