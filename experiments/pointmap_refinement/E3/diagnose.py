"""Initial Adam direction vs finite-difference loss; no optimization or GT access."""
import argparse,json
from pathlib import Path
import numpy as np,torch
from train import mod
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());parent=Path(c['parent_stage']);e1=Path(json.loads((parent/'config_resolved.json').read_text())['parent_stage'])
def t(x):return torch.as_tensor(x,device='cuda',dtype=torch.float32)
with np.load(parent/'artifacts/shared/shared_map_initial.npz') as d:base=t(d['xyz0']);color=t(d['rgb_fixed'])
with np.load(parent/'artifacts/shared/ray_initialization.npz') as d:ids=np.flatnonzero(d['active_candidate']);ray=t(d['owner_ray_world'][ids]);distance=t(d['owner_ray_distance'][ids])
with np.load(e1/'artifacts/f0/vggt_omega_raw.npz') as d:ks=d['intrinsics'][0];es=d['extrinsics'][0]
idx=torch.as_tensor(ids,device='cuda');initial=base[idx];aff=np.array([[.25,0,-.375],[0,.25,-.375],[0,0,1]],np.float32);cams=[(t(aff@k),t(e)) for k,e in zip(ks,es)];target=[];mask=[]
for i in range(3):
    with np.load(parent/'artifacts/renders'/f'f1_frame_{i}.npz') as d:target.append(t(d['target']))
    with np.load(s/'artifacts/source'/f'fixed_masks_{i}.npz') as d:mask.append(torch.as_tensor(d['train_mask'],device='cuda'))
def loss(delta,i):
    x=base.index_copy(0,idx,initial+ray*(distance*torch.expm1(delta))[:,None]);rgb,_,_=mod.render(x,color,*cams[i],96,128)
    return torch.sqrt((rgb-target[i]).square()+c['charbonnier_epsilon']**2)[mask[i]].mean()/3
parameter=torch.zeros(len(ids),device='cuda',requires_grad=True);start=0.
for i in range(3):v=loss(parameter,i);v.backward();start+=float(v.detach())
g=parameter.grad.detach();direction=-g/(g.abs()+1e-8);analytic=float((g*direction).sum());probes=[]
with torch.no_grad():
    for eps in [1e-6,1e-5,1e-4,.001]:
        plus=sum(float(loss(direction*eps,i)) for i in range(3));minus=sum(float(loss(-direction*eps,i)) for i in range(3))
        probes.append({'epsilon':eps,'plus_direction_loss':plus,'minus_direction_loss':minus,'central_derivative':(plus-minus)/(2*eps),'first_order_predicted_plus':start+eps*analytic})
result={'initial_loss':start,'initial_gradient_norm':float(g.norm()),'adam_initial_direction_derivative_autograd':analytic,'probes':probes,'scope':'actual dense-scene initial topology; finite differences include changing hard front/stencil decisions; float32 small-epsilon precision also matters','positions_updated':False}
(s/'evaluation/direction_diagnostic.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
