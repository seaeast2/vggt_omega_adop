import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import cv2
import numpy as np
import torch
from renderer import render


def record(path):
    p=Path(path)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h}


def arr(x):return x.detach().cpu().numpy()


def tensor(a,dtype=torch.float64):return torch.as_tensor(a,dtype=dtype,device='cuda')


def synthetic(c,stage):
    k=tensor([[30.,0,15.3],[0,31.,15.7],[0,0,1.]])
    e=tensor([[1.,0,0,0],[0,1,0,0],[0,0,1,0]])
    other=e.clone();other[0,3]=-.4
    truth=tensor([[.08,.04,2.4]]);color=tensor([[.8,.4,.2]])
    x=(truth+tensor([[.035,-.02,.15]])).requires_grad_()
    targets=[render(truth,color,k,cam,32,32)[0].detach() for cam in [e,other]]
    def loss(v,cameras=[e,other]):
        return sum((render(v,color,k,cam,32,32)[0]-target).square().sum() for cam,target in zip(cameras,targets))
    g=torch.autograd.grad(loss(x),x)[0];checks=[]
    for eps in c['gradient_epsilon']:
        numeric=torch.zeros_like(x)
        for j in range(3):
            d=torch.zeros_like(x);d[0,j]=eps
            numeric[0,j]=(loss(x.detach()+d)-loss(x.detach()-d))/(2*eps)
        error=(numeric-g).abs();ok=torch.allclose(numeric,g,rtol=c['gradient_rtol'],atol=c['gradient_atol'])
        checks.append({'epsilon':eps,'autograd':arr(g).tolist(),'finite_difference':arr(numeric).tolist(),'max_abs_error':float(error.max()),'passed':ok})
        assert ok,checks[-1]
    point=truth.clone().requires_grad_();ray=truth/torch.linalg.norm(truth)
    self_rgb=render(point,color,k,e,32,32)[0]
    self_grad=torch.autograd.grad(self_rgb.square().sum(),point)[0]
    self_ray=float((self_grad*ray).sum());assert abs(self_ray)<1e-10
    multi_grad=torch.autograd.grad(render(point,color,k,other,32,32)[0].square().sum(),point)[0]
    multi_ray=float((multi_grad*ray).sum());assert abs(multi_ray)>1e-6
    # Known textured plane, fixed RGB and source rays, two fixed cameras; no GT loss.
    v,u=torch.meshgrid(torch.linspace(8.2,22.2,9,device='cuda',dtype=torch.float64),torch.linspace(8.4,22.4,9,device='cuda',dtype=torch.float64),indexing='ij')
    rays=torch.stack(((u-15.3)/30,(v-15.7)/31,torch.ones_like(u)),dim=-1).reshape(-1,3)
    colors=torch.rand((81,3),device='cuda',dtype=torch.float64)*.8+.1
    gt=rays*2.4;z=torch.nn.Parameter(torch.full((81,1),2.6,device='cuda',dtype=torch.float64))
    targets=[render(gt,colors,k,cam,32,32,depth_rtol=c['synthetic_plane_depth_rtol'])[0].detach() for cam in [e,other]]
    opt=torch.optim.Adam([z],lr=c['synthetic_lr']);history=[]
    initial=float(torch.linalg.norm((rays*z.detach())-gt,dim=1).mean())
    for step in range(c['synthetic_steps']):
        opt.zero_grad();xyz=rays*z
        ls=sum((render(xyz,colors,k,cam,32,32,depth_rtol=c['synthetic_plane_depth_rtol'])[0]-target).square().mean() for cam,target in zip([e,other],targets))
        ls.backward();assert torch.isfinite(z.grad).all();opt.step()
        with torch.no_grad():z.clamp_(1.5,3.5)
        history.append({'step':step,'rgb_loss':float(ls.detach()),'mean_3d_error':float(torch.linalg.norm(rays*z-gt,dim=1).mean())})
    final=history[-1]['mean_3d_error']
    (stage/'evaluation/plane_history.json').write_text(json.dumps(history,indent=2))
    assert final<initial*.2,(initial,final)
    np.savez_compressed(stage/'artifacts/synthetic/plane.npz',gt=arr(gt),initial=arr(rays*2.6),final=arr(rays*z),rgb=arr(colors))
    # Occlusion and empty/frustum boundary checks; hard visibility is intentionally discrete.
    near=tensor([[0.,0.,2.],[0.,0.,3.]]);cols=tensor([[1.,0,0],[0,0,1.]])
    oc,dep,alpha=render(near,cols,k,e,32,32);assert float(oc[...,2].max())==0
    _,_,empty=render(tensor([[0.,0.,-1.],[100.,100.,1.]]),cols,k,e,32,32);assert float(empty.max())==0
    result={'finite_differences':checks,'self_ray_directional_derivative':self_ray,'parallax_ray_directional_derivative':multi_ray,'plane_initial_mean_3d_error':initial,'plane_final_mean_3d_error':final,'plane_history':history,'occluded_back_color_rejected':True,'behind_and_outside_rejected':True,'limitations':'finite differences on stable stencils/front sets; hard topology and z visibility are not differentiated'}
    (stage/'evaluation/synthetic.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
    c=json.loads(Path('experiments/pointmap_refinement/P2/config.json').read_text());s=Path('results/pointmap_refinement')/a.run_id/'stages/P2';s.mkdir(parents=True,exist_ok=False)
    for n in ['artifacts/synthetic','artifacts/renders','artifacts/source','evaluation','logs']:(s/n).mkdir(parents=True)
    start=datetime.now(ZoneInfo('Asia/Seoul')).isoformat();(s/'manifest.json').write_text(json.dumps({'status':'running','started_at':start}))
    (s/'config_resolved.json').write_text(json.dumps(c|{'run_id':a.run_id},indent=2))
    try:
        torch.manual_seed(c['seed']);torch.cuda.reset_peak_memory_stats()
        syn=synthetic(c,s);print('synthetic passed',syn['plane_initial_mean_3d_error'],syn['plane_final_mean_3d_error'],flush=True)
        parent=Path(c['parent_stage']);m=json.loads((parent/'manifest.json').read_text());assert m['status']=='completed'
        for row in m['artifacts']:assert record(row['path'])==row
        with np.load(parent/'artifacts/baseline/observations.npz') as data:obs={k:data[k] for k in data.files}
        with np.load(parent/'artifacts/baseline/vggt_omega_raw.npz') as raw:
            rgb=raw['images'][0].transpose(0,2,3,1);ks=raw['intrinsics'][0];es=raw['extrinsics'][0]
        uv=obs['pixel_uv'];stride=c['source_pixel_stride'];keep=(uv[:,0]%stride==2)&(uv[:,1]%stride==2)
        xyz=tensor(obs['world_xyz_initial'][keep],torch.float32);colors=tensor(obs['rgb'][keep]/255.,torch.float32)
        np.savez_compressed(s/'artifacts/source/selected_observations.npz',source_indices=np.flatnonzero(keep))
        h,w=c['render_hw'];sh,sw=rgb.shape[1:3];aff=np.array([[w/sw,0,(w/sw-1)/2],[0,h/sh,(h/sh-1)/2],[0,0,1]],np.float32)
        rows=[]
        for i in range(3):
            k=tensor(aff@ks[i],torch.float32);e=tensor(es[i],torch.float32)
            torch.cuda.synchronize();t=time.perf_counter()
            with torch.no_grad():out,depth,alpha=render(xyz,colors,k,e,h,w,c['sigma_pixels'],c['radius_pixels'],c['depth_rtol'])
            torch.cuda.synchronize();seconds=time.perf_counter()-t
            image,dep,al=arr(out),arr(depth),arr(alpha);assert np.isfinite(image).all() and np.isfinite(dep).all()
            target=cv2.resize(rgb[i],(w,h),interpolation=cv2.INTER_AREA);mask=al>=c['coverage_alpha_threshold']
            mse=float(((image-target)**2)[mask].mean());allmse=float(((image-target)**2).mean())
            path=s/'artifacts/renders'/f'frame_{i:02d}.npz';np.savez_compressed(path,rgb=image,depth=dep,alpha=al,coverage=mask,target_rgb=target,intrinsics=arr(k),extrinsics=arr(e))
            with np.load(path) as check:assert np.array_equal(check['rgb'],image)
            panels=[np.rint(target*255).astype('uint8')[...,::-1],np.rint(image.clip(0,1)*255).astype('uint8')[...,::-1],cv2.applyColorMap(np.rint(al*255).astype('uint8'),cv2.COLORMAP_TURBO)]
            canvas=np.full((h+30,w*3,3),255,np.uint8)
            for j,(panel,name) in enumerate(zip(panels,['target','render','alpha'])):
                canvas[30:,j*w:(j+1)*w]=panel;cv2.putText(canvas,name,(j*w+3,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
            assert cv2.imwrite(str(s/'artifacts/renders'/f'frame_{i:02d}.png'),canvas)
            # Real geometry gradient smoke check on a frozen initial coverage mask.
            variable=xyz.clone().requires_grad_();pred,_,_=render(variable,colors,k,e,h,w,c['sigma_pixels'],c['radius_pixels'],c['depth_rtol'])
            loss=(pred-tensor(target,torch.float32)).square()[tensor(mask,torch.bool)].mean();loss.backward()
            gradient=variable.grad;assert torch.isfinite(gradient).all() and float(gradient.norm())>0
            rows.append({'frame':i,'coverage_fraction':float(mask.mean()),'fixed_initial_mask_pixels':int(mask.sum()),'mse_initial_mask':mse,'psnr_initial_mask':float(-10*np.log10(mse)),'psnr_all_pixels':float(-10*np.log10(allmse)),'render_seconds':seconds,'xyz_gradient_norm':float(gradient.norm()),'gradient_nonzero_points':int((gradient.norm(dim=1)>0).sum())})
            del variable,pred,gradient,loss
        result={'selected_points':len(xyz),'source_total':len(uv),'stride':stride,'render_hw':[h,w],'frames':rows,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'real_geometry_updated':False,'gt_accuracy_evaluated':False,'interpretation':'self-view RGB diagnostic with fixed initial masks; no heldout or geometry improvement claim'}
        (s/'evaluation/real.json').write_text(json.dumps(result,indent=2)+'\n')
        (s/'environment.json').write_text(json.dumps({'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'python':platform.python_version(),'execution_context':'host GPU outside sandbox','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
        (s/'manifest.json').write_text(json.dumps({'status':'completed','experiment_code':'P2','run_id':a.run_id,'started_at':start,'ended_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'parent_manifest':record(parent/'manifest.json'),'completion_criteria_met':True},indent=2));print(json.dumps(result,indent=2),flush=True)
    except Exception as error:
        (s/'manifest.json').write_text(json.dumps({'status':'failed','started_at':start,'error':str(error)},indent=2));raise


if __name__=='__main__':main()
