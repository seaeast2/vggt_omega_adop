import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import time
import cv2
import numpy as np
import torch
import pytorch3d
from pytorch3d import _C
from adapter import render as p3d

spec=importlib.util.spec_from_file_location('p2_renderer','experiments/pointmap_refinement/P2/renderer.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def rec(p):
    p=Path(p)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h}


def t(x):return torch.as_tensor(x,device='cuda',dtype=torch.float32)
def ar(x):return x.detach().cpu().numpy()


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage
    c=json.loads(Path('experiments/pointmap_refinement/P2a/config.json').read_text());(s/'config_resolved.json').write_text(json.dumps(c,indent=2))
    torch.manual_seed(0)
    e0=Path(c['e0_stage']);p2=Path(c['p2_stage']);parents=[]
    for parent in [e0,p2]:
        m=json.loads((parent/'manifest.json').read_text());assert m['status']=='completed'
        for row in m['artifacts']:assert rec(row['path'])==row
        parents.append(rec(parent/'manifest.json'))
    def render(backend,x,color,k,e,h,w,plane=False):
        if backend=='p2':return module.render(x,color,k,e,h,w,depth_rtol=1000 if plane else .03)
        return p3d(x,color,k,e,h,w,mode=backend,points_per_pixel=c['points_per_pixel'],radius_pixels=c['radius_pixels'],depth_rtol=1000 if plane else .03)
    k=t([[30,0,15.3],[0,31,15.7],[0,0,1]]);e=t([[1,0,0,0],[0,1,0,0],[0,0,1,0]]);e2=e.clone();e2[0,3]=-.4
    # Asymmetric non-square pixel landmarks with nontrivial world->camera pose.
    uv=t([[8,5],[26,13],[43,24]]);z=t([2,2.5,3]);kk=t([[50,0,23.4],[0,48,14.8],[0,0,1]])
    theta=.31;r=t([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]]);ee=torch.cat((r,t([.2,-.1,.3])[:,None]),1)
    camera=torch.stack(((uv[:,0]-kk[0,2])/kk[0,0]*z,(uv[:,1]-kk[1,2])/kk[1,1]*z,z),1);world=(camera-ee[:,3])@r
    landmark=[]
    for idx in range(3):
        image,_,_=render('standard',world[idx:idx+1],t([[1,1,1]]),kk,ee,32,48)
        maxidx=int(image[...,0].argmax());found=[maxidx%48,maxidx//48];assert found==uv[idx].int().tolist(),(found,uv[idx])
        landmark.append({'expected':uv[idx].tolist(),'observed':found})
    syn=[]
    with np.load(p2/'artifacts/synthetic/plane.npz') as data:gt=t(data['gt']);initial=t(data['initial']);colors=t(data['rgb'])
    for backend in c['backends']:
        point=t([[.115,.02,2.55]]).requires_grad_();color=t([[.8,.4,.2]]);truth=t([[.08,.04,2.4]])
        targets=[render(backend,truth,color,k,cam,32,32)[0].detach() for cam in [e,e2]]
        def loss(x):return sum((render(backend,x,color,k,cam,32,32)[0]-target).square().sum() for cam,target in zip([e,e2],targets))
        grad=torch.autograd.grad(loss(point),point)[0];fd=[]
        for eps in c['finite_difference_eps']:
            numeric=torch.zeros_like(point)
            for j in range(3):
                delta=torch.zeros_like(point);delta[0,j]=eps;numeric[0,j]=(loss(point.detach()+delta)-loss(point.detach()-delta))/(2*eps)
            ok=torch.allclose(numeric,grad,rtol=c['finite_difference_rtol'],atol=c['finite_difference_atol'])
            fd.append({'epsilon':eps,'autograd':ar(grad).tolist(),'numeric':ar(numeric).tolist(),'max_abs_error':float((numeric-grad).abs().max()),'passed':ok})
        rays=gt/2.4;depth=torch.nn.Parameter(torch.full((len(gt),1),2.6,device='cuda'));opt=torch.optim.Adam([depth],lr=c['synthetic_lr'])
        targets=[render(backend,gt,colors,k,cam,32,32,True)[0].detach() for cam in [e,e2]];history=[]
        for step in range(c['synthetic_steps']):
            opt.zero_grad();ls=sum((render(backend,rays*depth,colors,k,cam,32,32,True)[0]-target).square().mean() for cam,target in zip([e,e2],targets))
            ls.backward();assert torch.isfinite(depth.grad).all();opt.step()
            with torch.no_grad():depth.clamp_(1.5,3.5)
            history.append({'step':step,'loss':float(ls.detach()),'mean_3d_error':float((rays*depth.detach()-gt).norm(dim=1).mean())})
        ini=float((initial-gt).norm(dim=1).mean());end=history[-1]['mean_3d_error']
        syn.append({'backend':backend,'finite_differences':fd,'initial_mean_3d_error':ini,'final_mean_3d_error':end,'recovery_passed':end<ini*.2,'history':history})
        np.savez_compressed(s/'artifacts/synthetic'/f'{backend}.npz',gt=ar(gt),initial=ar(initial),final=ar(rays*depth.detach()),rgb=ar(colors))
        print('synthetic',backend,'fd',all(x['passed'] for x in fd),'recovery',ini,end,flush=True)
    (s/'evaluation/synthetic.json').write_text(json.dumps(syn,indent=2))
    with np.load(e0/'artifacts/baseline/observations.npz') as data:obs={key:data[key] for key in data.files}
    with np.load(p2/'artifacts/source/selected_observations.npz') as data:ids=data['source_indices']
    with np.load(e0/'artifacts/baseline/vggt_omega_raw.npz') as data:ks=data['intrinsics'][0];es=data['extrinsics'][0]
    xyz=t(obs['world_xyz_initial'][ids]);color=t(obs['rgb'][ids]/255.)
    aresize=np.array([[.25,0,-.375],[0,.25,-.375],[0,0,1]],np.float32);h,w=c['render_hw'];rows=[]
    for i in range(3):
        with np.load(p2/'artifacts/renders'/f'frame_{i:02d}.npz') as data:target=data['target_rgb'];reference_mask=data['coverage'];old=data['rgb']
        k=t(aresize@ks[i]);e=t(es[i]);outputs={};alphas={}
        for backend in c['backends']:
            torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();baseline=torch.cuda.memory_allocated()
            with torch.no_grad():
                for _ in range(c['timing_warmup']):render(backend,xyz,color,k,e,h,w)
                timings=[]
                for _ in range(c['timing_repeats']):
                    torch.cuda.synchronize();start=time.perf_counter();out,depth,alpha=render(backend,xyz,color,k,e,h,w);torch.cuda.synchronize();timings.append(time.perf_counter()-start)
            image=ar(out);al=ar(alpha);dep=ar(depth);mask=al>=.5;assert np.isfinite(image).all() and np.isfinite(dep).all()
            outputs[backend]=image;alphas[backend]=al
            np.savez_compressed(s/'artifacts/renders'/f'{backend}_frame_{i:02d}.npz',rgb=image,depth=dep,alpha=al,coverage=mask,target=target,reference_p2_mask=reference_mask)
            variable=xyz.detach().clone().requires_grad_();pred,_,_=render(backend,variable,color,k,e,h,w);ls=(pred-t(target)).square()[torch.as_tensor(reference_mask,device='cuda')].mean();ls.backward();g=variable.grad;assert torch.isfinite(g).all()
            mse=lambda a,b,m:float(((a-b)**2)[m].mean())
            psnr=lambda m:-10*np.log10(max(m,1e-20))
            row={'frame':i,'backend':backend,'coverage_fraction':float(mask.mean()),'psnr_p2_fixed_mask':psnr(mse(image,target,reference_mask)),'psnr_own_mask':psnr(mse(image,target,mask)),'psnr_all':psnr(float(((image-target)**2).mean())),'render_seconds_median':float(np.median(timings)),'render_seconds':timings,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'initial_allocated_bytes':baseline,'gradient_norm':float(g.norm()),'gradient_nonzero_points':int((g.norm(dim=1)>0).sum()),'rgb_difference_from_archived_p2_max':float(np.abs(image-old).max())}
            rows.append(row);print('real',backend,i,row['psnr_p2_fixed_mask'],flush=True)
            del variable,pred,ls,g,out,depth,alpha
        common=reference_mask.copy()
        for al in alphas.values():common&=al>=.5
        for row in rows[-3:]:
            row['common_mask_pixels']=int(common.sum());row['psnr_common_mask']=float(-10*np.log10(((outputs[row['backend']]-target)**2)[common].mean()))
        panel=np.full((h+30,w*4,3),255,np.uint8)
        for col,(name,image) in enumerate([('target',target)]+list(outputs.items())):
            panel[30:,col*w:(col+1)*w]=np.rint(image.clip(0,1)*255).astype('uint8')[...,::-1];cv2.putText(panel,name,(col*w+3,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
        cv2.imwrite(str(s/'artifacts/renders'/f'comparison_{i:02d}.png'),panel)
    (s/'evaluation/real.json').write_text(json.dumps(rows,indent=2))
    (s/'evaluation/coordinate_adapter.json').write_text(json.dumps({'non_square_landmarks':landmark,'passed':True,'ndc_formula':'((W-1-2u)/min(H,W), (H-1-2v)/min(H,W), camera_z)','selected_points':len(ids),'selected_indices_source':rec(p2/'artifacts/source/selected_observations.npz')},indent=2))
    (s/'environment.json').write_text(json.dumps({'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),'python':platform.python_version(),'pytorch3d':pytorch3d.__version__,'cuda_extension':_C.__file__,'pytorch3d_commit':c['pytorch3d_commit'],'patch':'pytorch3d-cxx20.patch','execution_context':'host GPU outside sandbox','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
    (s/'evaluation/completion.json').write_text(json.dumps({'execution_completed':True,'parent_manifests':parents,'real_geometry_updated':False,'gt_accuracy_evaluated':False,'all_single_point_fd_passed':all(x['passed'] for r in syn for x in r['finite_differences'])},indent=2))


if __name__=='__main__':main()
