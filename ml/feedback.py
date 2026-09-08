import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
import torch
from safetensors.torch import load_file, save_file
from scipy.special import expit
from .model import ObservationModel, LABELS, masked_bce
from .train import STRIDE, inputs, export, atomic_json, sha
from .metrics import metrics, apply_calibration, thresholds

def build_buffer():
    from .train import arrays
    rows,x,y,m,splits=arrays();selected={}
    sources={r['id']:r for r in map(json.loads,Path('artifacts/data-manifest.jsonl').read_text().splitlines())}
    for split in ['train','dev']:
        chosen=[]
        for family in sorted(set(rows[i]['family'] for i in splits[split])):
            ids=[i for i in splits[split] if rows[i]['family']==family]
            chosen.extend(ids[::max(1,len(ids)//12)][:12])
        selected[split]=np.array(chosen)
    np.savez_compressed('artifacts/replay-buffer.npz',**{f'{key}_{split}':np.asarray(value[selected[split]]) for split in selected for key,value in [('x',x),('y',y),('mask',m)]})
    atomic_json('artifacts/replay-buffer.json',{'sha256':sha('artifacts/replay-buffer.npz'),'source':'Representative original train rows and independent development rows','rows':{k:len(v) for k,v in selected.items()},'families':{k:sorted(set(rows[i]['family'] for i in v)) for k,v in selected.items()},'preprocessVersion':'rgba-diff-rle-letterbox-v1','devInputHashes':sorted({sources[rows[i]['pageId']][side+'Sha256'] for i in selected['dev'] for side in ['before','after']})})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--feedback');parser.add_argument('--output');parser.add_argument('--build-buffer',action='store_true');args=parser.parse_args()
    torch.set_num_threads(2)
    if args.build_buffer:build_buffer();return
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    def progress(stage,completed,total):atomic_json(out/'progress.json',{'stage':stage,'completed':completed,'total':total})
    try:
        feedback=json.loads(Path(args.feedback).read_text());pairs=feedback.get('pagePairs',[])
        if not pairs:raise ValueError('No explicit corrected observations are available.')
        root=Path(__file__).resolve().parents[1];buffer_path=root/'artifacts/replay-buffer.npz';weights=root/'artifacts/model.safetensors'
        if not buffer_path.exists() or not weights.exists():raise ValueError('Install the versioned training assets before a feedback update.')
        buffer_meta=json.loads((root/'artifacts/replay-buffer.json').read_text());parent_manifest=json.loads((root/'web/public/models/manifest.json').read_text())
        if sha(buffer_path)!=buffer_meta['sha256']:raise ValueError('Retained data buffer hash mismatch.')
        if sha(weights)!=parent_manifest['weightsSha256']:raise ValueError('Safe model weight hash mismatch.')
        old=np.load(buffer_path,allow_pickle=False);new_x=[];new_y=[];new_m=[]
        for position,pair in enumerate(pairs):
            progress('prepare_feedback',position,len(pairs));prefix=out/f'pair-{position}'
            for side in ['before','after']:
                if pair.get('inputHashes',{}).get(side) in buffer_meta['devInputHashes']:raise ValueError('Feedback overlaps the independent retained development examples.')
                encoded=pair['images'][side].split(',',1)[-1];blob=base64.b64decode(encoded,validate=True)
                if len(blob)>20*1024*1024 or not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Feedback image is not a supported PNG.')
                if pair.get('inputHashes',{}).get(side) and hashlib.sha256(blob).hexdigest()!=pair['inputHashes'][side]:raise ValueError('Feedback image hash mismatch.')
                prefix.with_name(prefix.name+f'-{side}.png').write_bytes(blob)
            request={'before':str(prefix.with_name(prefix.name+'-before.png')),'after':str(prefix.with_name(prefix.name+'-after.png')),'masks':pair.get('analysis',{}).get('masks',[]),'output':str(prefix)}
            request_path=prefix.with_suffix('.request.json');request_path.write_text(json.dumps(request))
            subprocess.run([os.environ.get('NODE','node'),'--import','tsx',str(root/'capture/tensors.ts'),str(request_path)],check=True,cwd=root,capture_output=True)
            generated=json.loads(prefix.with_suffix('.json').read_text());a=np.fromfile(prefix.with_suffix('.f32'),dtype=np.float32).reshape(-1,STRIDE)
            explicit={i['candidateId']:i['observations'] for i in pair['labels']}
            for j,candidate in enumerate(generated['candidates']):
                correction=explicit.get(candidate['id'])
                if correction is None:continue
                mask=[float(correction.get(label) is not None) for label in LABELS]
                if not any(mask):continue
                new_x.append(a[j]);new_y.append([float(correction.get(label) is True) for label in LABELS]);new_m.append(mask)
        if not new_x:raise ValueError('No known observation labels survived candidate matching.')
        model=ObservationModel();model.load_state_dict(load_file(str(weights)));model.eval();model.set_stage(False)
        x=np.concatenate((old['x_train'],np.asarray(new_x)));y=np.concatenate((old['y_train'],np.asarray(new_y)));mask=np.concatenate((old['mask_train'],np.asarray(new_m)));train_features=[]
        with torch.no_grad():
            for k in range(0,len(x),16):train_features.append(model.features(*inputs(x,np.arange(k,min(k+16,len(x))),'cpu')))
        features=torch.cat(train_features);y=torch.tensor(y,dtype=torch.float32);mask=torch.tensor(mask,dtype=torch.float32)
        cut=json.loads((root/'web/public/models/manifest.json').read_text()).get('thresholds',[.5]*5)
        from .train import predict
        dev=old['x_dev'];before=predict(model,dev,np.arange(len(dev)),'cpu');parent_calibration=json.loads((root/'web/public/models/calibration.json').read_text())
        before_metric=metrics(old['y_dev'],apply_calibration(before,parent_calibration['classes']),old['mask_dev'],cut)
        original={k:v.clone() for k,v in model.encoder.state_dict().items()};optimizer=torch.optim.AdamW(model.head.parameters(),lr=.0004);curve=[];torch.manual_seed(61)
        for epoch in range(5):
            progress('train_head',epoch,5);model.train();optimizer.zero_grad();logits=model.head(features);loss=masked_bce(logits,y,mask);loss.backward();optimizer.step();curve.append(float(loss.detach()))
        assert all(torch.equal(original[k],v) for k,v in model.encoder.state_dict().items());model.eval()
        after=predict(model,dev,np.arange(len(dev)),'cpu');new_cut=thresholds(old['y_dev'],expit(after),old['mask_dev']);after_metric=metrics(old['y_dev'],expit(after),old['mask_dev'],new_cut)
        acceptable=after_metric['macroPrAuc']>=before_metric['macroPrAuc']-.03
        numerical=export(model,out/'model.onnx',inputs(x,np.arange(min(2,len(x))),'cpu'));save_file(model.state_dict(),str(out/'model.safetensors'));h=sha(out/'model.onnx')
        calibration={'modelSha256':h,'preprocessVersion':'rgba-diff-rle-letterbox-v1','classes':[{'label':l,'status':'uncalibrated','temperature':1.,'bias':0.,'n':0,'positive':0,'negative':0} for l in LABELS]};atomic_json(out/'calibration.json',calibration)
        manifest=json.loads((root/'web/public/models/manifest.json').read_text());manifest.update(version=f'feedback-{int(time.time())}',sha256=h,modelSha256=h,weightsSha256=sha(out/'model.safetensors'),calibrationSha256=sha(out/'calibration.json'),parentModelSha256=manifest['sha256'],feedbackSha256=sha(args.feedback),calibration='calibration.json',evaluationPassed=acceptable,thresholds=new_cut)
        atomic_json(out/'manifest.json',manifest);atomic_json(out/'evaluation.json',{'status':'eligible' if acceptable else 'rejected','rule':'Independent retained dev macro PR-AUC may decrease by at most 0.03; explicit activation required.','before':before_metric,'after':after_metric,'feedbackPages':len(pairs),'feedbackCandidates':len(new_x),'oldTrainingCandidates':len(old['x_train']),'devCandidates':len(dev),'curve':curve,'encoderUnchanged':True,'onnx':numerical,'calibration':'Invalidated because model weights changed.'});progress('complete',5,5)
        print(json.dumps({'version':manifest['version'],'evaluationPassed':acceptable,'output':out.name}))
    except Exception as error:
        atomic_json(out/'progress.json',{'stage':'error','completed':0,'total':1,'error':str(error)});raise

if __name__=='__main__':main()
