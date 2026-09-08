import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import numpy as np
import onnxruntime as ort
from .train import atomic_json,STRIDE
from .model import INPUT_NAMES

def main():
    samples=json.loads(Path('web/public/examples/index.json').read_text());start=time.perf_counter();session=ort.InferenceSession('web/public/models/model.onnx',providers=['CPUExecutionProvider']);load=(time.perf_counter()-start)*1000;results=[]
    with tempfile.TemporaryDirectory(prefix='visual-benchmark-') as tmp:
        for sample in samples:
            times=[]
            for trial in range(3):
                t0=time.perf_counter();prefix=Path(tmp)/'batch';request={side:str(Path('web/public/examples')/sample[side]) for side in ['before','after']};request['output']=str(prefix);input_file=Path(tmp)/'request.json';input_file.write_text(json.dumps(request));subprocess.run([os.environ.get('NODE','node'),'--import','tsx','capture/tensors.ts',str(input_file)],check=True,capture_output=True);t1=time.perf_counter();x=np.fromfile(prefix.with_suffix('.f32'),dtype=np.float32).reshape(-1,STRIDE);count=len(x)
                if count:
                    image=3*96*96;feed={INPUT_NAMES[i]:x[:,i*image:(i+1)*image].reshape(count,3,96,96) for i in range(4)};feed['geometry']=x[:,-12:];result=session.run(None,feed)[0];assert np.isfinite(result).all()
                t2=time.perf_counter();times.append({'freshNodeTensorProcessMilliseconds':(t1-t0)*1000,'inferenceMilliseconds':(t2-t1)*1000,'endToEndMilliseconds':(t2-t0)*1000,'candidates':count})
            results.append({'id':sample['id'],'trials':times})
    atomic_json('artifacts/end-to-end-timing.json',{'modelColdLoadMilliseconds':load,'scope':'Actual PNG files -> fresh Node process with official decode/candidates/tensors -> CPU ONNX; includes process and disk transfer. URL screenshot acquisition and UI rendering are separate. No inference for zero-candidate pairs.','results':results})
if __name__=='__main__':main()
