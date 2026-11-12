"""Supplementary plane finite differences, hard-visibility boundary and reload checks."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
import torch
from renderer import render

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage
def t(x):return torch.as_tensor(x,dtype=torch.float64,device='cuda')
k=t([[30.,0,15.3],[0,31.,15.7],[0,0,1.]]);e=t([[1.,0,0,0],[0,1,0,0],[0,0,1,0]]);e2=e.clone();e2[0,3]=-.4
with np.load(s/'artifacts/synthetic/plane.npz') as saved:
    gt=t(saved['gt']);initial=t(saved['initial']);final=t(saved['final']);color=t(saved['rgb'])
targets=[render(gt,color,k,cam,32,32,depth_rtol=1000)[0].detach() for cam in [e,e2]]
def loss(x):return sum((render(x,color,k,cam,32,32,depth_rtol=1000)[0]-target).square().mean() for cam,target in zip([e,e2],targets))
v=initial.clone().requires_grad_();g=torch.autograd.grad(loss(v),v)[0];eps=1e-5;checks=[]
for idx in [0,40,80]:
    numeric=[]
    for j in range(3):
        step=torch.zeros_like(initial);step[idx,j]=eps
        numeric.append(float((loss(initial+step)-loss(initial-step))/(2*eps)))
    ng=t(numeric);ok=torch.allclose(g[idx],ng,rtol=.001,atol=1e-7);assert ok
    checks.append({'point':idx,'epsilon':eps,'autograd':g[idx].tolist(),'finite_difference':numeric,'max_abs_error':float((g[idx]-ng).abs().max()),'passed':ok})
# Crossing the 3% front-layer threshold is intentionally not differentiable.
colors=t([[1,0,0],[0,0,1]]);boundary=[]
for z in [2.0599,2.06,2.0601]:
    out,_,_=render(t([[0,0,2],[0,0,z]]),colors,k,e,32,32)
    boundary.append({'back_z':z,'blue_max':float(out[...,2].max())})
assert boundary[0]['blue_max']>0 and boundary[-1]['blue_max']==0
for i in range(3):
    with np.load(s/'artifacts/renders'/f'frame_{i:02d}.npz') as r:
        assert r['rgb'].shape==(96,128,3)
        assert np.isfinite(r['rgb']).all() and np.isfinite(r['depth']).all()
        assert np.array_equal(r['coverage'],r['alpha']>=.5)
        assert (r['depth'][r['coverage']]>0).all()
        assert cv2.imread(str(s/'artifacts/renders'/f'frame_{i:02d}.png')).shape==(126,384,3)
pan=np.full((2*32+25,3*32,3),255,np.uint8)
for i,cam in enumerate([e,e2]):
    for j,xyz in enumerate([gt,initial,final]):
        rgb=render(xyz,color,k,cam,32,32,depth_rtol=1000)[0].detach().cpu().numpy()
        pan[25+i*32:25+(i+1)*32,j*32:(j+1)*32]=np.rint(rgb.clip(0,1)*255).astype('uint8')[...,::-1]
pan=cv2.resize(pan,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
for j,name in enumerate(['GT RGB','initial','final']):cv2.putText(pan,name,(j*128+4,40),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
assert cv2.imwrite(str(s/'artifacts/synthetic/plane_comparison.png'),pan)
result={'plane_xyz_finite_differences':checks,'visibility_threshold_sweep':boundary,'hard_boundary_derivative_valid':False,'render_reload':'passed','plane_initial_3d_error':float((initial-gt).norm(dim=1).mean()),'plane_final_3d_error':float((final-gt).norm(dim=1).mean()),'scope':'smooth region checks passed; hard visibility transition remains discontinuous'}
(s/'evaluation/verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
