"""Validate the versioned model bundle and execute a real CPU inference."""
import hashlib
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort

root = Path(__file__).resolve().parents[1]
folder = root / 'web/public/models'
manifest = json.loads((folder / 'manifest.json').read_text())
model = folder / 'model.onnx'
actual = hashlib.sha256(model.read_bytes()).hexdigest()
assert actual == manifest['modelSha256'], 'Model checksum mismatch'
calibration = json.loads((folder / 'calibration.json').read_text())
assert calibration['modelSha256'] == actual
assert calibration['preprocessVersion'] == manifest['preprocessVersion']
options = ort.SessionOptions()
options.intra_op_num_threads = 2
session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
feeds = {name: np.zeros((1, 3, 96, 96), dtype=np.float32) for name in ('local_before', 'local_after', 'context_before', 'context_after')}
feeds['geometry'] = np.zeros((1, 12), dtype=np.float32)
out = session.run(None, feeds)[0]
assert out.shape == (1, 5) and np.isfinite(out).all()
print(json.dumps({'version': manifest['version'], 'modelSha256': actual, 'realInference': True, 'shape': list(out.shape)}))
