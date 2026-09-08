import argparse
import json
from pathlib import Path
import numpy as np
import torch
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from .model import ObservationModel
from .train import arrays, inputs, atomic_json
from .metrics import metrics, thresholds

class Oracle:
    def __init__(self,rows,truth,mask):
        self._rows=rows;self._truth=truth;self._mask=mask;self.pages=set();self.candidates=set()
    def reveal(self,pages):
        self.pages.update(pages)
        self.candidates.update(i for i,r in enumerate(self._rows) if r['split']=='train' and r['pageId'] in pages)
        ids=np.array(sorted(self.candidates));return ids,self._truth[ids].copy(),self._mask[ids].copy()


def fit(features,ids,y,m):
    outputs=[]
    for j in range(5):
        keep=m[:,j].astype(bool);truth=y[keep,j]
        if len(np.unique(truth))<2:outputs.append(float(truth.mean()) if len(truth) else .5)
        else:outputs.append(LogisticRegression(max_iter=300,C=.1,class_weight='balanced').fit(features[ids[keep]],truth))
    return outputs

def predict(models,features):
    return np.column_stack([np.repeat(c,len(features)) if isinstance(c,float) else c.predict_proba(features)[:,1] for c in models])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',default='cpu');args=parser.parse_args();torch.set_num_threads(3)
    rows,x,y,m,splits=arrays();device=args.device;model=ObservationModel(pretrained=True).to(device).eval();features=[]
    with torch.no_grad():
        for k in range(0,len(rows),24):features.append(model.features(*inputs(x,np.arange(k,min(k+24,len(rows))),device)).cpu().numpy())
    full=np.concatenate(features);rng=np.random.default_rng(812);projection=rng.normal(size=(full.shape[1],96)).astype(np.float32)/np.sqrt(96)
    features=StandardScaler().fit(full[splits['train']]@projection).transform(full@projection)
    pages=sorted(set(rows[i]['pageId'] for i in splits['train']));by_page={p:np.array([i for i in splits['train'] if rows[i]['pageId']==p]) for p in pages};page_features={p:features[ids].mean(0) for p,ids in by_page.items()};results=[]
    dev=splits['dev'];test=splits['test']
    for seed in [17,29,43]:
        rng=np.random.default_rng(seed);initial=rng.choice(pages,12,replace=False).tolist()
        for strategy in ['random','uncertainty','uncertainty_diversity']:
            rng=np.random.default_rng(seed);oracle=Oracle(rows,y,m);selected=list(initial);curve=[]
            for budget in [12,24,48,96]:
                if budget>12:
                    remaining=[p for p in pages if p not in oracle.pages];count=budget-len(oracle.pages)
                    if strategy=='random':addition=rng.choice(remaining,count,replace=False).tolist()
                    else:
                        probability=predict(models,features);uncertainty={p:float(np.min(np.abs(probability[by_page[p]]-.5))) for p in remaining};ranked=sorted(remaining,key=lambda p:(uncertainty[p],p))
                        if strategy=='uncertainty':addition=ranked[:count]
                        else:
                            pool=ranked[:min(len(ranked),count*4)];addition=[]
                            while len(addition)<count:
                                references=np.array([page_features[p] for p in list(oracle.pages)+addition]);pick=max(pool,key=lambda p:float(np.min(np.sum((references-page_features[p])**2,axis=1))))
                                addition.append(pick);pool.remove(pick)
                    selected.extend(addition)
                ids,revealed_y,revealed_m=oracle.reveal(selected);models=fit(features,ids,revealed_y,revealed_m);p=predict(models,features[dev]);cut=thresholds(y[dev],p,m[dev]);testp=predict(models,features[test])
                curve.append({'pageBudget':budget,'revealedCandidates':len(ids),'revealedPages':sorted(oracle.pages),'dev':metrics(y[dev],p,m[dev],cut),'test':metrics(y[test],testp,m[test],cut)})
                print(seed,strategy,budget,curve[-1]['dev']['macroPrAuc'],flush=True)
            results.append({'seed':seed,'strategy':strategy,'initialPages':initial,'curve':curve})
            atomic_json('artifacts/replay-results.json',{'protocol':'Generic pretrained frozen features, fixed random projection, logistic heads. Labels revealed only after page selection. Development thresholds; final held-out metrics.','budgets':[12,24,48,96],'calibrationLabelCost':0,'calibrationNote':'No calibration labels used; selection scores are uncalibrated.','developmentLabelCost':len(set(rows[i]['pageId'] for i in dev)),'poolPages':len(pages),'scope':'Synthetic offline label-efficiency experiment; not measured human time savings.','runs':results})

if __name__=='__main__':main()
