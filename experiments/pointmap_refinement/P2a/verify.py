"""Ray degeneracy, plane FD at tied/stable depth order, saved outputs and bin timing."""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
import torch
from adapter import render as p3d
from run import t,ar,module

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage
c=json.loads((s/'config_resolved.json').read_text());p2=Path(c['p2_stage']);e0=Path(c['e0_stage'])
k=t([[30,0,15.3],[0,31,15.7],[0,0,1]]);e=t([[1,0,0,0],[0,1,0,0],[0,0,1,0]]);e2=e.clone();e2[0,3]=-.4
def render(name,x,col,cam):
    return module.render(x,col,k,cam,32,32,depth_rtol=1000) if name=='p2' else p3d(x,col,k,cam,32,32,mode=name,depth_rtol=1000)
with np.load(p2/'artifacts/synthetic/plane.npz') as data:initial=t(data['initial']);gt=t(data['gt']);colors=t(data['rgb'])
results=[]
for name in c['backends']:
    point=t([[.08,.04,2.4]]).requires_grad_();ray=point.detach()/point.detach().norm();col=t([[.8,.4,.2]])
    self_g=torch.autograd.grad(render(name,point,col,e)[0].square().sum(),point)[0]
    other_g=torch.autograd.grad(render(name,point,col,e2)[0].square().sum(),point)[0]
    dself=float((self_g*ray).sum());dother=float((other_g*ray).sum());assert abs(dself)<1e-5 and abs(dother)>1e-5
    targets=[render(name,gt,colors,cam)[0].detach() for cam in [e,e2]]
    def loss(x):return sum((render(name,x,colors,cam)[0]-target).square().mean() for cam,target in zip([e,e2],targets))
    fd=[]
    for state in ['coplanar','separated_order','separated_order_screen_offset']:
        x=initial.clone()
        if state!='coplanar':x=x*(1+torch.arange(len(x),device='cuda')[:,None]*.002/2.6)
        if state=='separated_order_screen_offset':x=x+t([.013,.017,0])
        x.requires_grad_();grad=torch.autograd.grad(loss(x),x)[0]
        for idx in [0,40,80]:
            numeric=[];eps=.0003
            for j in range(3):
                delta=torch.zeros_like(x);delta[idx,j]=eps;numeric.append(float((loss(x.detach()+delta)-loss(x.detach()-delta))/(2*eps)))
            ng=t(numeric);ok=torch.allclose(ng,grad[idx],rtol=.05,atol=1e-5)
            fd.append({'state':state,'point':idx,'epsilon':eps,'autograd':ar(grad[idx]).tolist(),'numeric':numeric,'max_abs_error':float((ng-grad[idx]).abs().max()),'passed':ok})
    results.append({'backend':name,'self_ray_derivative':dself,'other_ray_derivative':dother,'plane_fd':fd})
(s/'evaluation/additional_gradients.json').write_text(json.dumps(results,indent=2))
with np.load(e0/'artifacts/baseline/observations.npz') as d:obs={key:d[key] for key in d.files}
with np.load(p2/'artifacts/source/selected_observations.npz') as d:ids=d['source_indices']
x=t(obs['world_xyz_initial'][ids]);col=t(obs['rgb'][ids]/255);bins=[]
for i in range(3):
    with np.load(p2/'artifacts/renders'/f'frame_{i:02d}.npz') as d:kk=t(d['intrinsics']);ee=t(d['extrinsics'])
    for name in ['standard','matched']:
        with torch.no_grad():
            for _ in range(2):p3d(x,col,kk,ee,96,128,mode=name,bin_size=None)
            times=[]
            for _ in range(5):
                torch.cuda.synchronize();start=time.perf_counter();rgb,dep,alpha=p3d(x,col,kk,ee,96,128,mode=name,bin_size=None);torch.cuda.synchronize();times.append(time.perf_counter()-start)
        with np.load(s/'artifacts/renders'/f'{name}_frame_{i:02d}.npz') as old:
            difference=float(np.max(np.abs(ar(rgb)-old['rgb'])))
        bins.append({'frame':i,'backend':name,'bin_size':'auto','median_seconds':float(np.median(times)),'rgb_max_difference_from_naive_bins':difference})
for path in (s/'artifacts/renders').glob('*.npz'):
    with np.load(path) as d:
        assert np.isfinite(d['rgb']).all() and np.isfinite(d['depth']).all()
        assert np.array_equal(d['coverage'],d['alpha']>=.5)
for path in (s/'artifacts/renders').glob('*.png'):assert cv2.imread(str(path)).shape==(126,512,3)
(s/'evaluation/bins_and_reload.json').write_text(json.dumps({'bin_comparisons':bins,'saved_outputs':'passed'},indent=2))
print(json.dumps({'rays_passed':True,'plane_fd':[(r['backend'],[(q['state'],q['point'],q['passed']) for q in r['plane_fd']]) for r in results],'bins':bins},indent=2))
