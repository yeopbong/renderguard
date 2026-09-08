import copy
import json
from pathlib import Path
import numpy as np
import pytest
import torch
from safetensors.torch import load_file, save_file
from ml.model import ObservationModel, masked_bce
from ml.metrics import calibrate, metrics, apply_calibration
from ml.prepare import overlap

def test_masked_unknown_has_zero_gradient():
    logits=torch.zeros(1,5,requires_grad=True)
    loss=masked_bce(logits,torch.ones(1,5),torch.tensor([[1.,0.,1.,0.,1.]]))
    loss.backward()
    assert logits.grad[0,1]==0 and logits.grad[0,3]==0
    assert logits.grad[0,0]!=0

def test_all_four_image_branches_have_effect_and_freezing_is_real(tmp_path):
    torch.set_num_threads(2);torch.manual_seed(3)
    m=ObservationModel().eval()
    inputs=[torch.randn(2,3,96,96,requires_grad=True) for _ in range(4)]+[torch.rand(2,12)]
    output=m(*inputs);output.sum().backward()
    for image in inputs[:4]:assert image.grad is not None and image.grad.abs().sum()>0
    m.train();m.set_stage(False)
    before={k:v.clone() for k,v in m.encoder.state_dict().items()}
    optimizer=torch.optim.SGD(m.head.parameters(),lr=.1)
    optimizer.zero_grad();m(*[a.detach() for a in inputs]).sum().backward();optimizer.step()
    assert all(torch.equal(before[k],v) for k,v in m.encoder.state_dict().items())
    m.set_stage(True)
    optimizer=torch.optim.SGD([p for p in m.parameters() if p.requires_grad],lr=.1)
    optimizer.zero_grad();m(*[a.detach() for a in inputs]).sum().backward();optimizer.step()
    assert any(not torch.equal(before[k],v) for k,v in m.encoder.state_dict().items() if 'weight' in k)
    assert all(torch.equal(before[k],v) for k,v in m.encoder.state_dict().items() if 'running_' in k)
    m.eval();path=tmp_path/'weights.safetensors';save_file(m.state_dict(),str(path));loaded=ObservationModel().eval();loaded.load_state_dict(load_file(str(path)))
    torch.testing.assert_close(m(*inputs),loaded(*inputs),atol=0,rtol=0)

def test_calibration_refuses_unsupported_class_and_metrics_absent():
    y=np.zeros((20,5));mask=np.ones((20,5));z=np.zeros((20,5))
    classes=calibrate(z,y,mask)
    assert all(c['status']=='uncalibrated' for c in classes)
    result=metrics(y,apply_calibration(z,classes),mask,[.5]*5)
    assert all(c['prAuc'] is None for c in result['classes'])

def test_candidate_coverage_is_not_iou():
    assert overlap({'x':0,'y':0,'width':1000,'height':1000},{'x':20,'y':20,'width':10,'height':10})==(1.,.0001)

def test_family_and_raster_source_leakage():
    path=Path('artifacts/data-manifest.jsonl')
    if not path.exists():pytest.skip('Full corpus manifest is an optional release artifact')
    records=[json.loads(s) for s in path.read_text().splitlines()];families={};hashes={}
    for r in records:
        assert families.setdefault(r['family'],r['split'])==r['split']
        for key in ['beforeSha256','afterSha256']:
            assert hashes.setdefault(r[key],r['split'])==r['split']
    assert len(families)==24

def test_published_model_runtime_is_actual_onnx():
    import onnxruntime as ort
    path=Path('web/public/models/model.onnx')
    if not path.exists():pytest.skip('Download the versioned release model first')
    session=ort.InferenceSession(str(path),providers=['CPUExecutionProvider'])
    feed={i.name:np.zeros([1,3,96,96] if i.name!='geometry' else [1,12],dtype=np.float32) for i in session.get_inputs()}
    scores=session.run(None,feed)[0]
    assert scores.shape==(1,5) and np.isfinite(scores).all()
    feed['local_after'][:]=1
    changed=session.run(None,feed)[0]
    assert not np.allclose(scores,changed)
