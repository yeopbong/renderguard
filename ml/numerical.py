"""Separate raw PyTorch arithmetic from the exported frozen Conv/BN deployment graph."""
import copy
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import numpy_helper
import onnxruntime as ort
import torch
from safetensors.torch import load_file
from .model import ObservationModel,INPUT_NAMES
from .train import arrays,inputs,atomic_json
from .metrics import apply_calibration

def deployment_model(source):
    model=copy.deepcopy(source).eval()
    def fuse(module):
        for child in list(module.children()):fuse(child)
        items=list(module._modules.items())
        for (conv_name,conv),(bn_name,bn) in zip(items,items[1:]):
            if isinstance(conv,torch.nn.Conv2d) and isinstance(bn,torch.nn.modules.batchnorm._BatchNorm):
                if hasattr(bn,'drop') and not isinstance(bn.drop,torch.nn.Identity):raise ValueError('A non-identity BN drop layer cannot be omitted')
                module._modules[conv_name]=torch.nn.utils.fuse_conv_bn_eval(conv,bn)
                module._modules[bn_name]=copy.deepcopy(getattr(bn,'act',torch.nn.Identity()))
    fuse(model)
    return model

def main():
    torch.set_num_threads(4);rows,x,y,mask,splits=arrays();indices=splits['test'][:24];model=ObservationModel().eval();model.load_state_dict(load_file('artifacts/model.safetensors'));fused=deployment_model(model);session=ort.InferenceSession('web/public/models/model.onnx',providers=['CPUExecutionProvider']);cal=json.loads(Path('web/public/models/calibration.json').read_text());manifest=json.loads(Path('web/public/models/manifest.json').read_text());thresholds=manifest['thresholds'];results=[]
    for batch in [1,3,4,24]:
        raw=[];deployed=[];ort_outputs=[]
        for k in range(0,len(indices),batch):
            a=inputs(x,indices[k:k+batch],'cpu')
            with torch.no_grad():raw.append(model(*a).numpy());deployed.append(fused(*a).numpy())
            ort_outputs.append(session.run(None,{n:v.numpy() for n,v in zip(INPUT_NAMES,a)})[0])
        raw=np.concatenate(raw);deployed=np.concatenate(deployed);ort_logits=np.concatenate(ort_outputs);item={'batchSize':batch,'candidates':len(indices),'tolerance':1e-4}
        for name,reference in [('unfusedPyTorch',raw),('deploymentFusedPyTorch',deployed)]:
            p=apply_calibration(reference,cal['classes']);q=apply_calibration(ort_logits,cal['classes']);difference=float(np.max(np.abs(reference-ort_logits)));item[name]={'maxLogitError':difference,'maxScoreError':float(np.max(np.abs(p-q))),'thresholdDisagreements':int(np.sum((p>=thresholds)!=(q>=thresholds))),'passesOriginalLogitTolerance':difference<1e-4}
        results.append(item)
    graph=onnx.load('web/public/models/model.onnx');constants={p.name:numpy_helper.to_array(p) for p in graph.graph.initializer};errors=[]
    for node in graph.graph.node:
        if node.op_type=='Conv' and node.input[0] in ['local_after','context_before','context_after']:break
        if node.op_type!='Conv' or not node.name.startswith('/encoder/'):continue
        name=''
        for part in node.name.strip('/').split('/')[:-1]:
            if part.startswith('encoder.'):name=part
            elif part!='encoder':name+='.'+part
        module=fused.get_submodule(name)
        if node.input[1] in constants:
            reference=constants[node.input[1]];actual=module.weight.detach().numpy();difference=np.abs(actual-reference);worst=np.unravel_index(difference.argmax(),difference.shape)
            ulps=np.abs(actual.view(np.int32).astype(np.int64)-reference.view(np.int32).astype(np.int64))
            errors.append({'module':name,'maxAbsoluteDifference':float(difference.max()),'referenceAtLargestAbsoluteDifference':float(reference[worst]),'fusedAtLargestAbsoluteDifference':float(actual[worst]),'maxRelativeDifference':float(np.max(difference/np.maximum(np.abs(reference),1e-30))),'maxFloat32UlpDistance':int(ulps.max()),'withinFourFloat32EpsRelative':bool(np.allclose(actual,reference,atol=0,rtol=4*np.finfo(np.float32).eps))})
    a=inputs(x,indices,'cpu')
    with torch.no_grad():precise=model.double()(*[v.double() for v in a]).numpy()
    diagnostic={'modelSha256':manifest['sha256'],'dataSha256':manifest['dataSha256'],'preprocessVersion':manifest['preprocessVersion'],'torchThreads':torch.get_num_threads(),'toleranceUnchanged':1e-4,'batches':results,'exportGraph':{'batchNormalizationNodes':sum(n.op_type=='BatchNormalization' for n in graph.graph.node),'firstBranchConvWeightsCompared':len(errors),'maxFusedWeightDifference':max(r['maxAbsoluteDifference'] for r in errors),'maxFusedWeightRelativeDifference':max(r['maxRelativeDifference'] for r in errors),'maxFusedWeightUlpDistance':max(r['maxFloat32UlpDistance'] for r in errors),'weightRoundingCheck':'Zero absolute slack; four float32 eps relative budget for independent frozen-BN folding arithmetic. Separate from the unchanged 1e-4 output-logit requirement.','convolutions':errors},'float64Reference':{'unfusedPyTorchFloat32MaxError':float(np.max(np.abs(raw-precise))),'onnxFloat32MaxError':float(np.max(np.abs(ort_logits-precise)))},'interpretation':'The raw float32 PyTorch comparison exceeds the original absolute logit budget and remains a recorded failure. ONNX folds frozen BatchNorm into convolution. Standard PyTorch Conv/BN fusion preserves activation and agrees with the exported convolution weights within recorded float32 rounding; this separately named deployment-equivalence check keeps the original tolerance. Model weights, ONNX, calibration, inputs and thresholds are unchanged.'}
    atomic_json('artifacts/numerical-batch-diagnostic.json',diagnostic)
    assert diagnostic['exportGraph']['batchNormalizationNodes']==0 and diagnostic['exportGraph']['firstBranchConvWeightsCompared']>30
    assert all(r['withinFourFloat32EpsRelative'] for r in errors)
    assert all(r['deploymentFusedPyTorch']['passesOriginalLogitTolerance'] for r in results)
    print(json.dumps(diagnostic,indent=2))

if __name__=='__main__':main()
