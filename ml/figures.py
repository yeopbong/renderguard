import json
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR',str(Path('data/matplotlib-cache').resolve()))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':140,'savefig.bbox':'tight','font.family':'DejaVu Sans'})

def main():
    dest=Path('docs/figures');dest.mkdir(parents=True,exist_ok=True);experiments=json.loads(Path('artifacts/experiments.json').read_text());final=json.loads(Path('artifacts/model-results.json').read_text());replay=json.loads(Path('artifacts/replay-results.json').read_text())
    colors={'frozen':'#718594','local_only':'#ba7d35','local_context':'#218a78'}
    fig,axes=plt.subplots(1,3,figsize=(12,3.3),sharey=True)
    for ax,kind in zip(axes,colors):
        for run in [r for r in experiments['models'] if r['kind']==kind]:ax.plot([e['epoch'] for e in run['curve']],[e['devLoss'] for e in run['curve']],marker='o',ms=3,label=f"Seed {run['seed']}")
        ax.axvline(2.5,color='#aaa',linestyle=':',lw=1);ax.set(title=kind.replace('_',' ').title(),xlabel='Epoch');ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Development masked BCE');axes[-1].legend(frameon=False);fig.suptitle('Saved development curves · head warmup followed by fine-tuning');fig.tight_layout();fig.savefig(dest/'training-curves.png');plt.close(fig)
    names=['Uninformed prior','Pixel difference','Difference statistics','Frozen encoder','Local only','Local + context'];values=[experiments['baselines'][k]['test']['macroPrAuc'] for k in ['uninformed_prior','pixel_difference','difference_statistics']];error=[0.,0.,0.]
    for kind in colors:
        scores=[r['test']['macroPrAuc'] for r in experiments['models'] if r['kind']==kind];values.append(float(np.mean(scores)));error.append(float(np.std(scores,ddof=1)))
    fig,ax=plt.subplots(figsize=(8.8,3.5));ax.barh(names,values,xerr=error,color=['#ced4d9','#b9c1c9','#919da7']+list(colors.values()),capsize=3);ax.invert_yaxis();ax.set(xlim=(0,1.03),xlabel='Held-out candidate macro PR-AUC');ax.set_title('Original synthetic families · neural bars show three-seed mean ± SD');ax.grid(axis='x',alpha=.15);fig.tight_layout();fig.savefig(dest/'comparison.png');plt.close(fig)
    fig,axes=plt.subplots(1,5,figsize=(14,3),sharex=True,sharey=True)
    for ax,r in zip(axes,final['testReliability']):
        ax.plot([0,1],[0,1],linestyle=':',color='#9aa5ab');ax.plot([b['score'] for b in r['bins']],[b['frequency'] for b in r['bins']],marker='o',color='#218a78');ax.set(title=r['label'].replace('_','\n'),xlabel='Score',xlim=(0,1),ylim=(0,1));ax.text(.04,.92,f"n={r['n']}\nECE={r['ece']:.3f}",transform=ax.transAxes,va='top',fontsize=8)
    axes[0].set_ylabel('Observed frequency');fig.suptitle('Reliability on original held-out families · candidate population');fig.tight_layout();fig.savefig(dest/'reliability.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4));styles={'random':('#718594','Random'),'uncertainty':('#ba7d35','Low confidence'),'uncertainty_diversity':('#218a78','Low confidence + diversity')}
    for strategy,(color,label) in styles.items():
        runs=[r for r in replay['runs'] if r['strategy']==strategy];a=np.array([[c['test']['macroPrAuc'] for c in r['curve']] for r in runs]);budgets=replay['budgets'];mean=a.mean(0);sd=a.std(0,ddof=1);ax.plot(budgets,mean,marker='o',label=label,color=color);ax.fill_between(budgets,mean-sd,mean+sd,alpha=.12,color=color)
    ax.set(xlabel='Revealed page-pair labels',ylabel='Held-out macro PR-AUC',title='Offline label replay · three-seed mean ± SD');ax.legend(frameon=False);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(dest/'replay.png');plt.close(fig)

if __name__=='__main__':main()
