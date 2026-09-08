import hashlib
import json
import shutil
from pathlib import Path

SAMPLES=[('profile-0-cover','A covered biography','A new panel covers part of the profile text.'),('ledger-1-intentional_move','An intentional move','The layout displacement remains visible after choosing Intentional change.'),('settings-0-clip','A clipped control','Inspect the control boundary and its visible text.'),('kanban-1-overflow','A card outside its lane','A task card crosses a visible lane boundary.'),('invoice-0-hide','A missing total','The amount due disappears from the invoice.'),('article-0-repeat','A stable long page','Repeated capture has no pixel changes.'),('catalog-1-content','An ordinary content update','Changed product content still requires an explicit review decision.')]

def main():
    records={r['id']:r for r in map(json.loads,Path('artifacts/data-manifest.jsonl').read_text().splitlines())};dest=Path('web/public/examples');dest.mkdir(parents=True,exist_ok=True);index=[]
    for sample,title,description in SAMPLES:
        r=records[sample];item={'id':sample,'title':title,'description':description,'source':'original synthetic training family','license':'CC0-1.0'}
        for side in ['before','after']:
            name=f'{sample}-{side}.png';shutil.copyfile(r[side],dest/name);item[side]=name;item[side+'Sha256']=r[side+'Sha256']
        index.append(item)
    (dest/'index.json').write_text(json.dumps(index,indent=2));Path('examples/index.json').write_text(json.dumps(index,indent=2))
    Path('examples/README.md').write_text('''# Reproducible examples\n\nThe browser examples are copied from the original synthetic **training** sources and are licensed CC0-1.0. They are demonstration material, not held-out evaluation. Their image hashes are in `index.json`; the PNG files are served from `web/public/examples/`.\n\nRebuild them after rendering the corpus with `python -m ml.publish_examples`. The failed-width import case is exercised by the independent integration tests.\n''')
if __name__=='__main__':main()
