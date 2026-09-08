import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from scipy.optimize import minimize
from scipy.special import expit
from .model import LABELS

def thresholds(y, p, m):
    values=[]
    for j in range(5):
        known=m[:,j].astype(bool)
        if not known.any() or not y[known,j].any():values.append(.5);continue
        choices=np.arange(.1,.91,.05)
        f=[precision_recall_fscore_support(y[known,j],p[known,j]>=t,average='binary',zero_division=0)[2] for t in choices]
        values.append(float(choices[np.argmax(f)]))
    return values

def metrics(y,p,m,cutoffs):
    classes=[]
    for j,label in enumerate(LABELS):
        known=m[:,j].astype(bool);truth=y[known,j];prob=p[known,j]
        if not known.any():classes.append({'label':label,'n':0});continue
        pr,re,f1,_=precision_recall_fscore_support(truth,prob>=cutoffs[j],average='binary',zero_division=0)
        classes.append({'label':label,'n':int(known.sum()),'positive':int(truth.sum()),'validFraction':float(known.mean()),'precision':float(pr),'recall':float(re),'f1':float(f1),'prAuc':float(average_precision_score(truth,prob)) if len(np.unique(truth))==2 else None,'brier':float(np.mean((truth-prob)**2))})
    return {'classes':classes,'macroF1':float(np.mean([c['f1'] for c in classes if 'f1'in c])),'macroPrAuc':float(np.mean([c['prAuc'] for c in classes if c.get('prAuc') is not None])) if any(c.get('prAuc') is not None for c in classes) else None}

def calibrate(logits,y,m):
    result=[]
    for j,label in enumerate(LABELS):
        known=m[:,j].astype(bool);truth=y[known,j];z=logits[known,j];pos=int(truth.sum());neg=int(len(truth)-pos)
        item={'label':label,'n':len(truth),'positive':pos,'negative':neg,'status':'uncalibrated','temperature':1.,'bias':0.}
        if pos>=15 and neg>=15:
            def objective(v):
                p=expit(z/np.exp(v[0])+v[1]);return -np.mean(truth*np.log(p+1e-8)+(1-truth)*np.log(1-p+1e-8))+.002*np.sum(v*v)
            fit=minimize(objective,[0.,0.],bounds=[(-2,3),(-5,5)],method='L-BFGS-B')
            if fit.success:item.update(status='calibrated',temperature=float(np.exp(fit.x[0])),bias=float(fit.x[1]))
        result.append(item)
    return result

def apply_calibration(logits,classes):
    return np.column_stack([expit(logits[:,j]/c['temperature']+c['bias']) for j,c in enumerate(classes)])

def reliability(y,p,m):
    result=[]
    for j,label in enumerate(LABELS):
        k=m[:,j].astype(bool);truth=y[k,j];prob=p[k,j];bins=[];ece=0.
        for low in np.arange(0,1,.1):
            sel=(prob>=low)&(prob<(low+.1) if low<.9 else prob<=1)
            if sel.any():
                confidence=float(prob[sel].mean());frequency=float(truth[sel].mean());count=int(sel.sum());ece+=count/max(1,len(prob))*abs(confidence-frequency)
                bins.append({'low':float(low),'n':count,'score':confidence,'frequency':frequency})
        result.append({'label':label,'n':len(prob),'ece':float(ece),'brier':float(np.mean((truth-prob)**2)) if len(prob) else None,'bins':bins})
    return result
