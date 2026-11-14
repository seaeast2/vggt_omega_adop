"""Standalone scientific figures; run in isolated .venvs/blur-report."""
import argparse,json,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

def run(data,out):
    out.mkdir(parents=True,exist_ok=True);labels=['clean','G0.75','G1.5','G3','motion9','frame1 G3'];x=np.arange(6)
    fig,axes=plt.subplots(2,4,figsize=(17,7),constrained_layout=True)
    for row,(dataset,value) in enumerate(data['datasets'].items()):
        cond=value['conditions'];ax=axes[row,0];ax.plot(x,[100*r['raw']['depth']['mae_m'] for r in cond],'o-',label='raw Omega')
        ax.set_ylabel(dataset+'\ndepth MAE (cm)');ax.set_title('Same scene, fixed GT pixels');ax.grid(alpha=.25)
        ax=axes[row,1];ax.plot(x,[r['optimization']['arms']['native']['fit_correspondences'] for r in cond],'o-',label='native FIT links')
        ax.plot(x,[r['optimization']['arms']['F01']['fit_correspondences'] for r in cond],'s--',label='clean geometry / blur RGB')
        ax.set_title('Matching support');ax.set_ylabel('FIT correspondences');ax.legend(fontsize=8);ax.grid(alpha=.25)
        ax=axes[row,2];ax.plot(x,[r['raw']['focal']['mean_abs_relative_percent'] for r in cond],'o-',label='raw K')
        ax.plot(x,[r['arms']['native']['focal']['mean_abs_relative_percent'] for r in cond],'s-',label='FoV K')
        ax.set_title('Direct GT focal calibration');ax.set_ylabel('mean absolute focal error (%)');ax.legend(fontsize=8);ax.grid(alpha=.25)
        ax=axes[row,3];ax.plot(x,[r['alignment']['pose_to_depth_scale_ratio'] for r in cond],'o-',label='synthetic blur')
        ref=value.get('TUM_reference',{}).get('tum-freiburg1_desk',{}).get('ratio')
        if ref is not None:ax.axhline(ref,color='red',ls='--',label=f'TUM historical reference {ref:.3f}')
        ax.axhline(1,color='gray',ls=':');ax.set_title('Camera-baseline / depth scale');ax.set_ylabel('scale ratio');ax.legend(fontsize=8);ax.grid(alpha=.25)
        for ax in axes[row]:ax.set_xticks(x,labels,rotation=30,ha='right')
    fig.suptitle('Controlled blur interventions: shared RGB scenes and fixed laser GT evaluation masks')
    for ext in ['png','svg','pdf']:fig.savefig(out/f'blur_diagnostics.{ext}',dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    width=.24
    for ax,(dataset,value) in zip(axes,data['datasets'].items()):
        cond=value['conditions'];fixed=[100*r['plane_fixed']['depth']['mae_m'] for r in cond]
        ax.plot(x,fixed,'k--',label='plane fixed');ax.plot(x,[100*r['plane_RGB']['distance']['depth']['mae_m'] for r in cond],'o-',label='distance')
        ax.plot(x,[100*r['plane_RGB']['distance_normal']['depth']['mae_m'] for r in cond],'s-',label='distance + normal')
        ax.set_xticks(x,labels,rotation=30,ha='right');ax.set_ylabel('GT depth MAE (cm)');ax.set_title(dataset+' | frozen clean geometry/support')
        ax.legend(fontsize=8);ax.grid(alpha=.25)
    for ext in ['png','svg','pdf']:fig.savefig(out/f'frozen_plane_RGB.{ext}',dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    for ax,(dataset,value) in zip(axes,data['datasets'].items()):
        wanted=[r for r in value['conditions'] if r['case'] in ['g300','frame1_g300']]
        xx=np.arange(2)
        for k,key in enumerate(['matching_only','geometry_only','interaction']):ax.bar(xx+(k-1)*width,[r['factorial'][key] for r in wanted],width,label=key)
        ax.axhline(0,color='black',lw=.8);ax.set_xticks(xx,['all-view G3','frame1-only G3']);ax.set_ylabel('Focal error change (percentage points)')
        ax.set_title(dataset+' | conditional 2x2 contrasts');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.25)
    for ext in ['png','svg','pdf']:fig.savefig(out/f'factorial_contrasts.{ext}',dpi=180)
    plt.close(fig)
    (out/'plot_environment.json').write_text(json.dumps(dict(python=sys.version,matplotlib=matplotlib.__version__,numpy=np.__version__,backend='Agg'),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('summary');p.add_argument('out');args=p.parse_args();run(json.loads(Path(args.summary).read_text()),Path(args.out))
