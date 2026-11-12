"""Host-GPU renderer ablations, synthetic controls, full E0b derivatives and 10 steps."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import traceback

import cv2
import numpy as np
import torch


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def cpu(tensor):return tensor.detach().cpu().numpy()


def write_ply(path,xyz,rgb,owner):
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('owner','<i2')]);a=np.empty(len(xyz),dtype)
    for i,name in enumerate(['x','y','z']):a[name]=xyz[:,i]
    for i,name in enumerate(['red','green','blue']):a[name]=rgb[:,i]
    a['owner']=owner
    head=(f'ply\nformat binary_little_endian 1.0\ncomment P2c short diagnostic; model units\nelement vertex {len(a)}\n'
          'property double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty short owner\nend_header\n')
    with path.open('xb') as stream:stream.write(head.encode());a.tofile(stream)
    with path.open('rb') as stream:
        while stream.readline()!=b'end_header\n':pass
        assert np.array_equal(np.fromfile(stream,dtype),a)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    src=Path('experiments/pointmap_refinement/P2c');c=json.loads((src/'config.json').read_text())
    s=Path('results/pointmap_refinement')/args.run_id/'stages/P2c';s.mkdir(parents=True,exist_ok=False)
    for name in ['artifacts/source','artifacts/synthetic','artifacts/renders','artifacts/checkpoints','artifacts/maps','artifacts/figures','evaluation','logs']:(s/name).mkdir(parents=True)
    for path in src.iterdir():
        if path.is_file():shutil.copy2(path,s/'artifacts/source'/path.name)
    for name,path in [('legacy.py','experiments/pointmap_refinement/P2/renderer.py'),('projection.py','experiments/pointmap_refinement/E0a/run.py')]:shutil.copy2(path,s/'artifacts/source'/name)
    p=module('projection',s/'artifacts/source/projection.py');old=module('legacy',s/'artifacts/source/legacy.py');new=module('candidate',s/'artifacts/source/renderer.py')
    manifest={'experiment_code':'P2c','run_id':args.run_id,'status':'running','started_at':p.stamp()};p.json_write(s/'manifest.json',manifest);p.json_write(s/'config_resolved.json',c|{'run_id':args.run_id})
    start=time.perf_counter()
    def log(value):
        message=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        print(message,flush=True)
        with (s/'logs/run.log').open('a') as stream:stream.write(message+'\n')
    def event(phase,result):
        p.json_write(s/f'evaluation/{phase}.json',result)
        with (s/'progress.md').open('a') as stream:stream.write(f'- {p.stamp()} {phase} 저장 완료.\n')
    try:
        torch.manual_seed(c['seed']);torch.cuda.init();torch.cuda.reset_peak_memory_stats()
        def t(value,dtype=torch.float64):return torch.as_tensor(value,device='cuda',dtype=dtype)
        def render(x,color,k,e,h,w,variant,tau):
            if variant=='legacy':return old.render(x,color,k,e,h,w)
            return new.render(x,color,k,e,h,w,mode=variant,sigma=c['sigma_pixels'],radius=c['support_radius_pixels'],depth_rtol=c['hard_depth_relative'],tau=tau)
        # Explicit weak-tail and strong-foreground controls.
        k=t([[10.,0,8],[0,10.,8],[0,0,1.]]);e=t(np.c_[np.eye(3),np.zeros(3)]);colors=t([[1.,0,0],[0,0,1.]])
        occlusion={}
        for name,u,zback in [('outside_compact',10.4,1.2),('weak_inside',9.99,1.2),('strong_front',8.,2.)]:
            xyz=t([[(u-8)/10,0,1.],[0,0,zback]]);tau=float(np.median([1.,zback]))*c['soft_depth_temperature_fraction'];rows={}
            for variant in c['variants']:
                rgb,depth,alpha=render(xyz,colors,k,e,16,16,variant,tau)
                rows[variant]={'rgb':cpu(rgb[8,8]).tolist(),'depth':float(depth[8,8]),'alpha':float(alpha[8,8])}
            occlusion[name]=rows
        _,_,empty=render(t([[0,0,-1.],[100,100,1.]]),colors,k,e,16,16,'compact_soft',.15)
        occlusion_pass=(occlusion['outside_compact']['compact_soft']['rgb'][2]>.9 and
                        occlusion['weak_inside']['compact_soft']['rgb'][2]>.9 and
                        occlusion['strong_front']['compact_soft']['rgb'][0]>.95 and float(empty.max())==0)
        # Finite difference across an integer stencil boundary with a dense background.
        yy,xx=torch.meshgrid(torch.arange(16,device='cuda',dtype=torch.float64),torch.arange(16,device='cuda',dtype=torch.float64),indexing='ij')
        bg=torch.stack(((xx-8)/10*2,(yy-8)/10*2,torch.full_like(xx,2)),dim=-1).reshape(-1,3)
        bgc=t([[.1,.2,.8]]).expand(len(bg),-1);boundary_color=torch.cat([t([[1.,.2,.1]]),bgc]);ramp=(xx+2*yy)/48
        def boundary_loss(u):
            point=torch.stack([(u-8)/10,u*0,u*0+1])[None]
            image=render(torch.cat([point,bg]),boundary_color,k,e,16,16,'compact_soft',.15)[0]
            return (image[...,0]*ramp).sum()
        boundary=torch.tensor(8.,device='cuda',dtype=torch.float64,requires_grad=True);gradient=float(torch.autograd.grad(boundary_loss(boundary),boundary)[0]);boundary_rows=[]
        for epsilon in [1e-4,1e-5]:
            numeric=float((boundary_loss(boundary.detach()+epsilon)-boundary_loss(boundary.detach()-epsilon))/(2*epsilon))
            boundary_rows.append({'epsilon':epsilon,'autograd':gradient,'finite_difference':numeric,'passed':abs(numeric-gradient)<=1e-7+1e-3*abs(gradient)})
        # Known textured plane, scalar depth, two cameras and fixed initial masks.
        sk=t([[30.,0,15.3],[0,31.,15.7],[0,0,1.]]);se=e.clone();other=se.clone();other[0,3]=-.4
        v,u=torch.meshgrid(torch.linspace(8.2,22.2,9,device='cuda',dtype=torch.float64),torch.linspace(8.4,22.4,9,device='cuda',dtype=torch.float64),indexing='ij')
        plane_rays=torch.stack(((u-15.3)/30,(v-15.7)/31,torch.ones_like(u)),dim=-1).reshape(-1,3)
        plane_colors=torch.rand((81,3),device='cuda',dtype=torch.float64)*.8+.1;ztruth=c['synthetic_plane_depth'];zstart=c['synthetic_plane_initial_depth'];stau=ztruth*c['soft_depth_temperature_fraction']
        truth_images=[];plane_masks=[]
        for cam in [se,other]:
            target,_,alpha=render(plane_rays*ztruth,plane_colors,sk,cam,32,32,'compact_soft',stau)
            _,_,a0=render(plane_rays*zstart,plane_colors,sk,cam,32,32,'compact_soft',stau)
            truth_images.append(target.detach());plane_masks.append((alpha>.05)&(a0>.05))
        def plane_loss(z):
            return sum(((render(plane_rays*z,plane_colors,sk,cam,32,32,'compact_soft',stau)[0]-target)**2)[mask].mean() for cam,target,mask in zip([se,other],truth_images,plane_masks))
        z=torch.tensor(zstart,device='cuda',dtype=torch.float64,requires_grad=True);pg=float(torch.autograd.grad(plane_loss(z),z)[0]);plane_fd=[]
        for epsilon in [1e-4,1e-5]:
            numeric=float((plane_loss(z.detach()+epsilon)-plane_loss(z.detach()-epsilon))/(2*epsilon))
            plane_fd.append({'epsilon':epsilon,'autograd':pg,'finite_difference':numeric,'passed':abs(numeric-pg)<=1e-7+1e-3*abs(pg)})
        z=torch.nn.Parameter(torch.tensor(zstart,device='cuda',dtype=torch.float64));opt=torch.optim.Adam([z],lr=c['synthetic_plane_learning_rate']);plane_history=[]
        for step in range(c['synthetic_plane_steps']+1):
            ls=plane_loss(z);plane_history.append({'step':step,'depth':float(z.detach()),'loss':float(ls.detach()),'mean_3d_error':float((torch.linalg.norm(plane_rays,dim=1)*torch.abs(z-ztruth)).mean())})
            if step==c['synthetic_plane_steps']:break
            opt.zero_grad();ls.backward();opt.step()
            with torch.no_grad():z.clamp_(1.5,3.5)
        plane_pass=plane_history[-1]['mean_3d_error']<plane_history[0]['mean_3d_error']*c['plane_required_error_ratio']
        synthetic={'occlusion':occlusion,'occlusion_controls_pass':occlusion_pass,'boundary_finite_differences':boundary_rows,
                   'plane_finite_differences':plane_fd,'plane_initial':plane_history[0],'plane_final':plane_history[-1],
                   'plane_recovery_pass':plane_pass,'all_passed':occlusion_pass and all(row['passed'] for row in boundary_rows+plane_fd) and plane_pass}
        event('synthetic',synthetic);event('synthetic_plane_history',plane_history);log({'synthetic_passed':synthetic['all_passed'],'plane_initial_error':plane_history[0]['mean_3d_error'],'plane_final_error':plane_history[-1]['mean_3d_error']})
        np.savez_compressed(s/'artifacts/synthetic/plane.npz',truth=cpu(plane_rays*ztruth),initial=cpu(plane_rays*zstart),final=cpu(plane_rays*z),colors=cpu(plane_colors))
        parent=Path(c['parent_stage']);pm=json.loads((parent/'manifest.json').read_text());assert pm['status']=='completed';inputs=[p.record(parent/'manifest.json')]
        def tracked(path):
            row=next(row for row in pm['artifacts'] if row['path']==str(path));assert p.record(path)==row;inputs.append(row);return path
        with np.load(tracked(parent/'artifacts/initial/shared_map_initial.npz')) as data:shared={key:data[key] for key in data.files}
        with np.load(tracked(parent/'artifacts/initial/cameras_and_targets.npz')) as data:ks=data['intrinsics'];es=data['extrinsics'];targets_cpu=data['targets'];e1_masks=data['e1_masks']
        masks_cpu=[];cached=[]
        for camera in range(3):
            with np.load(tracked(parent/f'artifacts/renders/initial_frame_{camera}.npz')) as data:masks_cpu.append(data['train_mask']);cached.append(data['rgb'])
        frames_path=tracked(parent/'artifacts/initial/frames.json');frames=json.loads(frames_path.read_text())
        base64=shared['xyz0'];active=np.flatnonzero(shared['active_candidate']);rays64=shared['owner_ray_world'][active];dist64=shared['owner_ray_distance'][active]
        assert len(active)==135193 and len(base64)==341325
        taus=[float(np.median((base64@cam[:,:3].T+cam[:,3])[:,2][(base64@cam[:,:3].T+cam[:,3])[:,2]>0]))*c['soft_depth_temperature_fraction'] for cam in es]
        height,width=c['render_hw'];affine=np.array([[width/512,0,(width/512-1)/2],[0,height/384,(height/384-1)/2],[0,0,1.]])
        def setup(dtype):
            base=t(base64,dtype);colors=t(shared['rgb_fixed'],dtype);idx=torch.as_tensor(active,device='cuda');ray=t(rays64,dtype);distance=t(dist64,dtype)
            cameras=[(t(affine@k,dtype),t(e,dtype)) for k,e in zip(ks,es)];targets=[t(image,dtype) for image in targets_cpu];masks=[torch.as_tensor(mask,device='cuda') for mask in masks_cpu]
            def positions(delta):return base.index_copy(0,idx,base[idx]+ray*(distance*torch.expm1(delta))[:,None])
            def image(delta,camera,variant):return render(positions(delta),colors,*cameras[camera],height,width,variant,taus[camera])
            def loss(delta,camera,variant):return torch.sqrt((image(delta,camera,variant)[0]-targets[camera]).square()+c['charbonnier_epsilon']**2)[masks[camera]].mean()/3
            return positions,image,loss
        def direction_probe(variant,dtype,epsilons):
            positions,image,loss=setup(dtype);parameter=torch.zeros(len(active),device='cuda',dtype=dtype,requires_grad=True);initial=0.
            for camera in range(3):
                value=loss(parameter,camera,variant);value.backward();initial+=float(value.detach())
            gradient=parameter.grad.detach();assert torch.isfinite(gradient).all();direction=-gradient/(gradient.abs()+1e-8);analytic=float((gradient*direction).sum());rows=[]
            with torch.no_grad():
                for epsilon in epsilons:
                    plus=sum(float(loss(direction*epsilon,i,variant)) for i in range(3));minus=sum(float(loss(-direction*epsilon,i,variant)) for i in range(3));numeric=(plus-minus)/(2*epsilon)
                    rows.append({'epsilon':epsilon,'plus_loss':plus,'minus_loss':minus,'initial_loss':initial,'finite_difference':numeric,'autograd':analytic,
                                 'relative_error':abs(numeric-analytic)/max(abs(analytic),1e-12),'actual_plus_decreases':plus<initial})
            return {'variant':variant,'dtype':str(dtype),'initial_loss':initial,'gradient_norm':float(gradient.norm()),'autograd_direction':analytic,'probes':rows}
        fd=[]
        for variant in c['variants']:
            result=direction_probe(variant,torch.float32,c['finite_difference_epsilons']);fd.append(result);event('real_float32_directions',fd);log({'direction':variant,**result})
        double=direction_probe('compact_soft',torch.float64,c['fp64_check_epsilons']);event('real_float64_direction',double);log({'float64_direction':double})
        fp64_pass=all(abs(row['finite_difference']-row['autograd'])<=c['fp64_direction_absolute_tolerance']+c['fp64_direction_relative_tolerance']*abs(row['autograd']) for row in double['probes'])
        soft32=next(row for row in fd if row['variant']=='compact_soft');fp32_pass=all(row['actual_plus_decreases'] for row in soft32['probes'] if row['epsilon']>=1e-4)
        short=[];initial_images={};final_images={};rgb_before=[];rgb_after=[]
        for variant in c['variants']:
            positions,image,loss=setup(torch.float32);parameter=torch.nn.Parameter(torch.zeros(len(active),device='cuda'));optimizer=torch.optim.Adam([parameter],lr=c['short_learning_rate']);history=[]
            for step in range(c['short_steps']+1):
                with torch.no_grad():
                    total=sum(float(loss(parameter,i,variant)) for i in range(3));rows=[];images=[]
                    for camera in range(3):
                        rgb,z,alpha=image(parameter,camera,variant);out=cpu(rgb);a=cpu(alpha);images.append(out)
                        mse=float(((out-targets_cpu[camera])**2)[e1_masks[camera]].mean())
                        rows.append({'camera':camera,'psnr_fixed_e1_mask':float(-10*np.log10(max(mse,1e-20))),
                                     'support_coverage_fixed_train_mask':float((a[masks_cpu[camera]]>=.5).mean()),'coverage_all':float((a>=.5).mean())})
                        if step in [0,c['short_steps']]:
                            np.savez_compressed(s/f'artifacts/renders/{variant}_step_{step:02d}_camera_{camera}.npz',rgb=out,depth=cpu(z),alpha=a,target=targets_cpu[camera],train_mask=masks_cpu[camera],e1_mask=e1_masks[camera])
                    if step==0:initial_images[variant]=images
                    if step==c['short_steps']:final_images[variant]=images
                history.append({'step':step,'loss':total,'frames':rows})
                np.savez_compressed(s/f'artifacts/checkpoints/{variant}_step_{step:02d}.npz',delta=cpu(parameter),active_indices=active)
                if step==c['short_steps']:break
                optimizer.zero_grad(set_to_none=True)
                for camera in range(3):loss(parameter,camera,variant).backward()
                assert torch.isfinite(parameter.grad).all();torch.nn.utils.clip_grad_norm_([parameter],c['gradient_clip_norm']);optimizer.step()
                with torch.no_grad():parameter.clamp_(-c['log_ray_delta_bound'],c['log_ray_delta_bound'])
            delta=cpu(parameter).astype(float);xyz=base64.copy();xyz[active]+=rays64*(dist64*np.expm1(delta))[:,None]
            assert np.array_equal(xyz[~shared['active_candidate']],base64[~shared['active_candidate']])
            displacement=np.linalg.norm(xyz-base64,axis=1)
            np.savez_compressed(s/f'artifacts/maps/{variant}_short_final.npz',xyz0=base64,xyz=xyz,delta=delta,active_indices=active)
            write_ply(s/f'artifacts/maps/{variant}_short_source_mix.ply',xyz,shared['source_mix_rgb'],shared['owner_camera'])
            coverage_drop=max(history[0]['frames'][i]['support_coverage_fixed_train_mask']-history[-1]['frames'][i]['support_coverage_fixed_train_mask'] for i in range(3))
            result={'variant':variant,'initial_loss':history[0]['loss'],'last_loss':history[-1]['loss'],'history':history,
                    'moved_points_over_1e_8':int((displacement>1e-8).sum()),'active_displacement_mean':float(displacement[active].mean()),
                    'active_displacement_max':float(displacement[active].max()),'max_fixed_mask_support_drop':coverage_drop,
                    'loss_decreased':history[-1]['loss']<history[0]['loss'],'support_preserved':coverage_drop<=c['max_fixed_mask_support_coverage_drop']}
            short.append(result);event('short_optimization',short);log({'short':variant,'initial':result['initial_loss'],'last':result['last_loss'],'moved':result['moved_points_over_1e_8'],'max_support_drop':coverage_drop})
        initial_cells=[];final_cells=[]
        for camera in range(3):
            def upscale(image):return cv2.resize(np.rint(image.clip(0,1)*255).astype(np.uint8),(512,384),interpolation=cv2.INTER_NEAREST)
            initial_cells.append([upscale(targets_cpu[camera])]+[upscale(initial_images[v][camera]) for v in c['variants']])
            final_cells.append([upscale(targets_cpu[camera]),upscale(initial_images['compact_soft'][camera]),upscale(final_images['compact_soft'][camera])])
        p.panel(s/'artifacts/figures/initial_ablation.png',initial_cells,['Target RGB']+c['variants'],frames,384,512)
        p.panel(s/'artifacts/figures/soft_short_comparison.png',final_cells,['Target RGB','compact_soft initial','compact_soft after 10'],frames,384,512)
        legacy_max=max(float(np.abs(initial_images['legacy'][i]-cached[i]).max()) for i in range(3));assert legacy_max<5e-6
        soft_short=next(row for row in short if row['variant']=='compact_soft')
        ready=synthetic['all_passed'] and fp64_pass and fp32_pass and soft_short['loss_decreased'] and soft_short['support_preserved']
        decision={'ready_for_E3b':ready,'synthetic_passed':synthetic['all_passed'],'full_scene_float64_direction_passed':fp64_pass,
                  'float32_actual_descent_passed':fp32_pass,'short_loss_decreased':soft_short['loss_decreased'],'short_support_preserved':soft_short['support_preserved'],
                  'real_points':len(base64),'active_points':len(active),'fixed_temperature_by_camera':taus,'legacy_cached_rgb_max_difference':legacy_max,
                  'real_GT_evaluated':False,'full_E3b_training_performed':False,
                  'limitations':'Renderer/derivative diagnostics only; soft depth weighting is approximate visibility; GT geometry, heldout views and long optimization unverified.'}
        event('decision',decision)
        for row in inputs:assert p.record(row['path'])==row
        for path in (s/'artifacts/maps').glob('*.npz'):
            with np.load(path) as data:assert np.isfinite(data['xyz']).all() and np.array_equal(data['xyz0'],base64)
        event('verification',{'status':'passed','input_hashes_unchanged':True,'initial_points_exact_E0b_via_E3b':True,
                             'same_active_indices_targets_masks_all_variants':True,'legacy_reproduced':True,'inactive_xyz_unchanged':True,
                             'finite_gradients_and_saved_point_changes':True,'PLY_NPZ_PNG_reload':True})
        p.json_write(s/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,
                     'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
                     'execution_context':'host GPU outside sandbox','project_commit_before_run':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                     'wall_seconds':time.perf_counter()-start,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
                     'source_files':[p.record(path) for path in sorted((s/'artifacts/source').glob('*')) if path.is_file()]})
        log({'decision':decision});manifest.update(status='completed',ended_at=p.stamp(),completion_criteria_met=True,ready_for_E3b=ready,inputs=inputs)
        manifest['artifacts']=[p.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts]
        p.json_write(s/'manifest.json',manifest)
    except Exception:
        log(traceback.format_exc());manifest.update(status='failed',error=traceback.format_exc(),ended_at=p.stamp());p.json_write(s/'manifest.json',manifest);raise


if __name__=='__main__':main()
