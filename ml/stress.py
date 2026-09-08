import argparse
import json
from pathlib import Path
import numpy as np
import torch
from scipy.special import expit
from .train import arrays,train_one,predict,atomic_json,STRIDE
from .metrics import metrics,thresholds
from .prepare import overlap

def secondary(rows,x,y,m,splits,train_ids,dev_ids,name,device):
    selected={**splits,'train':np.array(train_ids),'dev':np.array(dev_ids)}
    model,evidence=train_one(x,y,m,selected,107,name,device,epochs=6)
    devlog=predict(model,x,selected['dev'],device);cut=thresholds(y[selected['dev']],expit(devlog),m[selected['dev']]);return model,evidence,cut

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',default='cpu');args=p.parse_args();torch.set_num_threads(3);rows,x,y,m,splits=arrays();records={r['id']:r for r in map(json.loads,Path('artifacts/data-manifest.jsonl').read_text().splitlines())};device=args.device
    train_light=[i for i in splits['train'] if records[rows[i]['pageId']]['variant'] in [0,2]];dev_light=[i for i in splits['dev'] if records[rows[i]['pageId']]['variant'] in [0,2]]
    model,evidence,cut=secondary(rows,x,y,m,splits,train_light,dev_light,'domain_exclusion',device);domains={}
    for name,variants in [('light_english',[0,2]),('dark_english',[1,3])]:
        ids=np.array([i for i in splits['test'] if records[rows[i]['pageId']]['variant'] in variants]);domains[name]=metrics(y[ids],expit(predict(model,x,ids,device)),m[ids],cut)
    records2=list(map(json.loads,Path('artifacts/stress-manifest.jsonl').read_text().splitlines()))
    for language in ['ja','zh']:
        tx=[];ty=[];tm=[]
        for r in records2:
            if r['language']!=language:continue
            cs=json.loads(Path(r['tensors']+'.json').read_text())['candidates'];a=np.fromfile(r['tensors']+'.f32',dtype=np.float32).reshape(-1,STRIDE)
            for i,c in enumerate(cs):
                matched=[o for o in r['observations'] if max(overlap(c['box'],o['box']))>=.1];labels=[]
                for j in range(5):
                    values=[o['labels'][j] for o in matched];labels.append(True if True in values else None if None in values else False)
                tx.append(a[i]);ty.append([float(v is True) for v in labels]);tm.append([float(v is not None) for v in labels])
        a=np.asarray(tx);domains[language]=metrics(np.asarray(ty),expit(predict(model,a,np.arange(len(a)),device)),np.asarray(tm),cut)
    result={'selection':'Secondary probes fixed after main model freeze; do not alter release selection.','domainExclusion':{'trainVariants':[0,2],'devVariants':[0,2],'trainingCandidates':len(train_light),'developmentCandidates':len(dev_light),'description':'Train/dev use light English scenes only. Test source families are reserved. Dark English uses original variants1/3. Japanese/Chinese replacements are separately rendered and contain no training labels.','metrics':domains,'training':evidence}}
    del model
    excluded={r['pageId'] for r in rows if r['split']=='train' and r['labels'][1] is True};train_without=[i for i in splits['train'] if rows[i]['pageId'] not in excluded]
    dev_without=[i for i in splits['dev'] if y[i,1]==0];model,evidence,cut=secondary(rows,x,y,m,splits,train_without,dev_without,'symptom_exclusion',device)
    ids=splits['test'];score=expit(predict(model,x,ids,device));result['symptomExclusion']={'excluded':'overlap_or_occlusion positive training page pairs','removedPages':len(excluded),'remainingTrainingCandidates':len(train_without),'thresholds':cut,'metric':metrics(y[ids],score,m[ids],cut),'training':evidence,'interpretation':'The excluded class has no positive task supervision and no calibrated detection claim. Its PR-AUC measures score ordering only; failure is expected and retained.'};atomic_json('artifacts/stress-results.json',result)

if __name__=='__main__':main()
