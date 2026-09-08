"""Map independently observed regions to official candidates and cache formal tensors."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np

STRIDE = 4 * 3 * 96 * 96 + 12

def overlap(a, b):
    area = max(0, min(a['x']+a['width'], b['x']+b['width'])-max(a['x'],b['x'])) * max(0,min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y']))
    return area / max(1, b['width']*b['height']), area / max(1,a['width']*a['height'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',default='artifacts/data-manifest.jsonl');args=parser.parse_args()
    records=[json.loads(s) for s in Path(args.manifest).read_text().splitlines()];cache=Path('data/tensors');cache.mkdir(parents=True,exist_ok=True)
    pairs=[dict(before=r['before'],after=r['after'],output=str(cache/r['id'])) for r in records]
    batch=cache/'requests.json';batch.write_text(json.dumps(pairs))
    subprocess.run([os.environ.get('NODE','node'),'--import','tsx','capture/tensors.ts',str(batch)],check=True)
    rows=[];missed=[];page_stats=[];position=0
    with (cache/'all.f32').open('wb') as out:
        for r in records:
            prefix=cache/r['id'];metadata=json.loads(prefix.with_suffix('.json').read_text());candidates=metadata.get('candidates',metadata.get('analysis',{}).get('candidates',[]))
            binary=prefix.with_suffix('.f32');raw=binary.read_bytes();assert len(raw)==len(candidates)*STRIDE*4
            out.write(raw);binary.unlink()
            page_stats.append({'id':r['id'],'family':r['family'],'split':r['split'],'candidates':len(candidates),'changedPixels':r['changedPixels']})
            for observation in r['observations']:
                if any(v is True for v in observation['labels']):
                    cov=max([overlap(c['box'],observation['box'])[0] for c in candidates] or [0])
                    tight=max([overlap(c['box'],observation['box'])[1] for c in candidates] or [0])
                    missed.append({'pageId':r['id'],'family':r['family'],'split':r['split'],'labels':observation['labels'],'coverage':cov,'tightness':tight,'matched':cov>=.1})
            for c in candidates:
                labels=[False]*5;matched=[]
                for o in r['observations']:
                    coverage,intersection=overlap(c['box'],o['box'])
                    if coverage>=.1 or intersection>=.1:
                        matched.append(o)
                for j in range(5):
                    vals=[o['labels'][j] for o in matched]
                    labels[j]=True if True in vals else None if None in vals else False
                rows.append({'index':position,'pageId':r['id'],'family':r['family'],'split':r['split'],'candidateId':c['id'],'box':c['box'],'stats':c['stats'],'labels':labels});position+=1
    Path('artifacts/candidates.jsonl').write_text('\n'.join(json.dumps(r,separators=(',',':')) for r in rows)+'\n')
    Path('artifacts/candidate-evaluation.json').write_text(json.dumps({'groundTruth':missed,'pages':page_stats,'rows':position,'tensorSha256':hashlib.file_digest((cache/'all.f32').open('rb'),'sha256').hexdigest()},indent=2))
    print(json.dumps({'candidateRows':position,'tensorBytes':(cache/'all.f32').stat().st_size}))

if __name__=='__main__':main()
