import hashlib
import json
from pathlib import Path
import platform
import resource
import subprocess
import time
import numpy as np
import onnxruntime as ort
import torch
from safetensors.torch import load_file
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from .train import arrays,inputs,atomic_json
from .model import ObservationModel,INPUT_NAMES,LABELS
from .metrics import metrics,apply_calibration
from .prepare import overlap
from .numerical import deployment_model

def main():
    torch.set_num_threads(4);rows,x,y,mask,splits=arrays();test=splits['test'];dev=splits['dev'];tr=splits['train'];sources=list(map(json.loads,Path('artifacts/data-manifest.jsonl').read_text().splitlines()));page_sources={r['id']:r for r in sources};manifest=json.loads(Path('web/public/models/manifest.json').read_text());cal=json.loads(Path('web/public/models/calibration.json').read_text());pred=np.load('artifacts/final-predictions.npz',allow_pickle=False);scores=apply_calibration(pred['test'],cal['classes']);thresholds=manifest['thresholds'];candidate_eval=json.loads(Path('artifacts/candidate-evaluation.json').read_text());localization={}
    for split in ['train','dev','calibration','test']:
        gt=[g for g in candidate_eval['groundTruth'] if g['split']==split];pages=[p for p in candidate_eval['pages'] if p['split']==split]
        localization[split]={'positiveObservationRegions':len(gt),'recallAtPoint1Coverage':np.mean([g['coverage']>=.1 for g in gt]),'recallAtPoint5Coverage':np.mean([g['coverage']>=.5 for g in gt]),'missingAtPoint1':sum(g['coverage']<.1 for g in gt),'missingAtPoint5':sum(g['coverage']<.5 for g in gt),'meanMaxCoverage':np.mean([g['coverage'] for g in gt]),'meanMaxTightness':np.mean([g['tightness'] for g in gt]),'pagePairs':len(pages),'meanCandidatesPerPage':np.mean([p['candidates'] for p in pages]),'p95CandidatesPerPage':np.percentile([p['candidates'] for p in pages],95),'maximumCandidatesPerPage':max(p['candidates'] for p in pages),'zeroCandidatePages':sum(p['candidates']==0 for p in pages)}
    page_candidates={p['id']:[] for p in candidate_eval['pages'] if p['split']=='test'}
    for k,i in enumerate(test):page_candidates[rows[i]['pageId']].append((rows[i],scores[k]))
    system=[]
    for j,label in enumerate(LABELS):
        positives=[(s,o) for s in sources if s['split']=='test' for o in s['observations'] if o['labels'][j] is True];hits=0
        for s,o in positives:
            if any(max(overlap(r['box'],o['box']))>=.1 and score[j]>=thresholds[j] for r,score in page_candidates[s['id']]):hits+=1
        system.append({'label':label,'allPositiveObservationRegions':len(positives),'captured':hits,'missed':len(positives)-hits,'recall':hits/len(positives) if positives else None})
    family_names=sorted(set(rows[i]['family'] for i in test));bootstrap=[];rng=np.random.default_rng(1009)
    for _ in range(500):
        sample=rng.choice(family_names,len(family_names),replace=True);indices=np.concatenate([np.array([k for k,i in enumerate(test) if rows[i]['family']==f]) for f in sample]);bootstrap.append(metrics(y[test][indices],scores[indices],mask[test][indices],thresholds)['macroPrAuc'])
    interval={'resamplingUnit':'source family','families':family_names,'replicates':500,'macroPrAuc95Percentile':[float(v) for v in np.percentile(bootstrap,[2.5,97.5])],'warning':'Only three held-out families; intervals are unstable and conditional on this authored corpus.'}
    rankings={'local_context':scores};geom=np.asarray(x[:,-12:]);stats=np.empty_like(y[test]);pixel=np.repeat(geom[test,4:5],5,axis=1)
    for j in range(5):
        known=tr[mask[tr,j].astype(bool)];clf=LogisticRegression(max_iter=1000,class_weight='balanced',random_state=17).fit(geom[known],y[known,j]);stats[:,j]=clf.predict_proba(geom[test])[:,1]
    rankings.update(difference_statistics=stats,pixel_difference=pixel)
    for kind in ['frozen','local_only']:
        runs=[r for r in json.loads(Path('artifacts/experiments.json').read_text())['models'] if r['kind']==kind];selected=max(runs,key=lambda r:r['dev']['macroPrAuc']);rankings[kind]=expit(np.load(f"artifacts/checkpoints/{kind}-{selected['seed']}-predictions.npz",allow_pickle=False)['test'])
    budget_results={}
    for method,values in rankings.items():
        page_scores={p:0. for p in page_candidates}
        for k,i in enumerate(test):page_scores[rows[i]['pageId']]=max(page_scores[rows[i]['pageId']],float(values[k].max()))
        ranking=sorted(page_scores,key=lambda p:(-page_scores[p],p));positive_pages={s['id'] for s in sources if s['split']=='test' and any(True in o['labels'] for o in s['observations'])};curve=[]
        for fraction in [.1,.25,.5]:
            count=int(np.ceil(len(ranking)*fraction));selected=set(ranking[:count]);captured=len(selected&positive_pages);curve.append({'pageFraction':fraction,'reviewedPagePairs':count,'totalPagePairs':len(ranking),'positiveObservationPages':len(positive_pages),'capturedObservationPages':captured,'missedObservationPages':len(positive_pages)-captured,'captureRate':captured/max(1,len(positive_pages))})
        budget_results[method]=curve
    start=time.perf_counter();session=ort.InferenceSession('web/public/models/model.onnx',providers=['CPUExecutionProvider']);load_ms=(time.perf_counter()-start)*1000;feed={n:v.numpy() for n,v in zip(INPUT_NAMES,inputs(x,test[:1],'cpu'))};start=time.perf_counter();session.run(None,feed);cold_ms=(time.perf_counter()-start)*1000;times=[]
    for _ in range(40):
        start=time.perf_counter();session.run(None,feed);times.append((time.perf_counter()-start)*1000)
    model=ObservationModel().eval();model.load_state_dict(load_file('artifacts/model.safetensors'));model=deployment_model(model);args=inputs(x,test[:24],'cpu');pt_batches=[];ort_batches=[]
    for offset in range(0,len(args[0]),4):
        block=[v[offset:offset+4] for v in args]
        with torch.no_grad():pt_batches.append(model(*block).numpy())
        ort_batches.append(session.run(None,{n:v.numpy() for n,v in zip(INPUT_NAMES,block)})[0])
    pytorch=np.concatenate(pt_batches);onnx=np.concatenate(ort_batches);ps=apply_calibration(pytorch,cal['classes']);os=apply_calibration(onnx,cal['classes']);numerical={'reference':'PyTorch with standard frozen Conv/BN fusion matching the exported graph','productBatchSize':4,'rawUnfusedComparison':'Exceeds 1e-4; retained in numerical-batch-diagnostic.json','pairs':len(args[0]),'maxLogitError':float(np.max(np.abs(pytorch-onnx))),'maxScoreError':float(np.max(np.abs(ps-os))),'thresholdDisagreements':int(np.sum((ps>=thresholds)!=(os>=thresholds))),'candidateRankingAgrees':bool(np.array_equal(np.argsort(-ps.max(1),kind='stable'),np.argsort(-os.max(1),kind='stable'))),'tolerance':1e-4};assert numerical['maxLogitError']<1e-4
    result={'modelSha256':manifest['sha256'],'dataSha256':manifest['dataSha256'],'preprocessVersion':manifest['preprocessVersion'],'localization':localization,'localizationDefinition':'Max candidate intersection divided by before/after element-union extent; tightness is max intersection/candidate area. These are coarse observation boxes, not pixel-exact defect segmentation.','endToEndObservationRecall':system,'familyBootstrap':interval,'pageReviewBudgets':budget_results,'budgetDefinition':'Rank all test page pairs by maximum candidate observation score; pixel method uses changed-pixel density. Count observation-bearing pages, not defects. Candidate-free pages remain in denominators.','timing':{'platform':platform.platform(),'machine':platform.machine(),'cpuThreads':torch.get_num_threads(),'onnxProviders':session.get_providers(),'modelLoadMilliseconds':load_ms,'coldInferenceMilliseconds':cold_ms,'warmInferenceMedianMilliseconds':float(np.median(times)),'warmInferenceP95Milliseconds':float(np.percentile(times,95)),'warmTrials':40,'batch':1,'inputs':'four 96x96 RGB crops and 12 geometry values','processMaxRSSBytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if platform.system()=='Darwin' else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'modelBytes':Path('web/public/models/model.onnx').stat().st_size},'numericalParity':numerical}
    atomic_json('artifacts/extended-evaluation.json',result);print(json.dumps({'localization':localization['test'],'numerical':numerical,'timing':result['timing']},indent=2))

if __name__=='__main__':main()
