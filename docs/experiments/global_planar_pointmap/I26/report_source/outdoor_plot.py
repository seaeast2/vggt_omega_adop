"""Static scientific plots; run in the isolated reporting environment."""
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def run(source,out):
    data=json.loads(source.read_text());out.mkdir(parents=True,exist_ok=True)
    arms=['omega_raw','fov','plane_fixed','plane_distance','plane_distance_normal','retained']
    labels=['raw','FoV','fixed','distance','dist+normal','retained']
    colors=['#777777','#0072b2','#009e73','#e69f00','#cc79a7','#333333']
    fig,axes=plt.subplots(len(data),3,figsize=(16,4.4*len(data)),squeeze=False,layout='constrained')
    for row,(dataset,record) in enumerate(data.items()):
        metrics=record['metrics'];x=np.arange(len(arms))
        for col,(field,title) in enumerate([('depth','Held-out depth MAE (m)'),('focal','Focal absolute relative error (%)')]):
            ax=axes[row,col]
            values=[metrics[a]['all']['depth']['mae_m'] if field=='depth' else metrics[a]['focal']['mean_abs_relative_percent'] for a in arms]
            bars=ax.bar(x,values,color=colors);ax.bar_label(bars,fmt='%.3f',fontsize=8,padding=3)
            ax.set_xticks(x,labels,rotation=35,ha='right');ax.set_title(dataset+'\n'+title);ax.set_ylim(0,max(values)*1.2 or 1)
        ax=axes[row,2]
        for offset,name,label,color in [(-.18,'world_pose','camera-pose alignment','#0072b2'),(.18,'world_raw_surface','raw FIT surface alignment','#e69f00')]:
            values=[metrics[a]['all'][name]['mean_m'] if metrics[a]['all'][name] else np.nan for a in arms]
            ax.bar(x+offset,values,width=.36,label=label,color=color)
        ax.set_xticks(x,labels,rotation=35,ha='right');ax.set_title(dataset+'\n3D point mean error (m)');ax.legend(fontsize=8)
        for ax in axes[row]:ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True)
    fig.suptitle('Outdoor LiDAR transfer: common evaluation masks and alignments\nRaw and FoV preserve camera-Z; unsupported plane stages can produce identical outputs',fontsize=12)
    for ext in ['png','svg','pdf']:fig.savefig(out/f'outdoor_comparison.{ext}',dpi=180)
    plt.close(fig)

if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
