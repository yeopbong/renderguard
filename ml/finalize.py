import json
from pathlib import Path
import numpy as np
import onnxruntime as ort
from .model import INPUT_NAMES
from .train import arrays,inputs,sha,atomic_json
from .metrics import apply_calibration

def main():
    rows,x,y,m,splits=arrays();tr=splits['train'];pos=(y[tr]*m[tr]).sum(0);neg=((1-y[tr])*m[tr]).sum(0);directory=Path('web/public/models');manifest=json.loads((directory/'manifest.json').read_text());experiments=json.loads(Path('artifacts/experiments.json').read_text());selected=next(r for r in experiments['models'] if r['kind']=='local_context' and r['seed']==manifest['seed'])
    config={'seeds':sorted({r['seed'] for r in experiments['models']}),'epochs':len(selected['curve']),'headWarmupEpochs':sum(e['stage']=='head' for e in selected['curve']),'fineTuneEpochs':sum(e['stage']=='finetune' for e in selected['curve']),'optimizer':'AdamW','optimizerResetEachEpoch':True,'weightDecay':.001,'headWarmupLearningRate':.001,'fineTuneHeadLearningRate':.0004,'encoderLearningRate':.0001,'headBatchSize':64,'fineTuneBatchSize':24,'positiveWeight':np.minimum(neg/np.maximum(pos,1),10).tolist(),'trainingPositive':pos.tolist(),'trainingNegative':neg.tolist(),'trainingCandidates':len(tr),'allCandidates':len(rows),'frozenBatchNormStatistics':True,'fineTuneEncoderStages':3,'gradientClipNorm':5,'dropout':.15,'preprocessVersion':manifest['preprocessVersion'],'trainingSourceSha':manifest['trainingSourceSha'],'dataSha256':manifest['dataSha256']}
    assert sha('artifacts/data-manifest.jsonl')==manifest['dataSha256']
    atomic_json('artifacts/training-config.json',config);manifest['configurationSha256']=sha('artifacts/training-config.json');manifest['limitations']='Research assistance only. Independent structural evaluations reveal material class-level failures. Observation scores do not establish defects or authorize release approval.';atomic_json(directory/'manifest.json',manifest)
    sample='profile-0-cover';metadata=json.loads(Path(f'data/tensors/{sample}.json').read_text());ids=np.array([i for i,r in enumerate(rows) if r['pageId']==sample]);session=ort.InferenceSession(str(directory/'model.onnx'),providers=['CPUExecutionProvider']);logits=session.run(None,{name:v.numpy() for name,v in zip(INPUT_NAMES,inputs(x,ids,'cpu'))})[0];calibration=json.loads((directory/'calibration.json').read_text());scores=apply_calibration(logits,calibration['classes'])
    result={'modelSha256':manifest['sha256'],'before':f'examples/{sample}-before.png','after':f'examples/{sample}-after.png','candidates':[{'id':c['id'],'box':c['box']} for c in metadata['candidates']],'predictions':[{'candidateId':metadata['candidates'][i]['id'],'logits':r.tolist(),'scores':scores[i].tolist()} for i,r in enumerate(logits)]};atomic_json(directory/'parity.json',result)

if __name__=='__main__':main()
