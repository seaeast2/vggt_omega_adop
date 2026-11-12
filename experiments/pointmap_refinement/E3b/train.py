"""Actual RGB backpropagation on E0b vertices; run on host GPU, no GT reads."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import traceback

import numpy as np
import torch
from prepare import load_module


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',type=Path,required=True); a=parser.parse_args(); s=a.stage
    c=json.loads((s/'config_resolved.json').read_text())
    p=load_module('projection',s/'artifacts/source/projection.py'); renderer=load_module('renderer',s/'artifacts/source/renderer.py')
    manifest=json.loads((s/'manifest.json').read_text()); assert manifest['phase']=='prepared'
    manifest.update(phase='training'); p.json_write(s/'manifest.json',manifest)
    def log(value):
        message=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        print(message,flush=True)
        with (s/'logs/train.log').open('a') as stream: stream.write(message+'\n')
    try:
        torch.manual_seed(c['seed']); torch.cuda.init(); torch.cuda.reset_peak_memory_stats()
        def t(value): return torch.as_tensor(value,device='cuda',dtype=torch.float32)
        with np.load(s/'artifacts/initial/shared_map_initial.npz') as data:
            base64=data['xyz0']; color=t(data['rgb_fixed']); active=np.flatnonzero(data['active_candidate'])
            rays64=data['owner_ray_world'][active]; distance64=data['owner_ray_distance'][active]
        with np.load(s/'artifacts/initial/cameras_and_targets.npz') as data:
            ks=data['intrinsics']; es=data['extrinsics']; target_cpu=data['targets']; eval_masks=data['e1_masks']
        base=t(base64); idx=torch.as_tensor(active,device='cuda'); rays=t(rays64); distance=t(distance64); initial_active=base[idx]
        delta=torch.nn.Parameter(torch.zeros(len(active),device='cuda'))
        height,width=c['render_hw']; sy,sx=height/384,width/512
        affine=np.array([[sx,0,(sx-1)/2],[0,sy,(sy-1)/2],[0,0,1]],np.float32)
        cams=[(t(affine@k),t(e)) for k,e in zip(ks,es)]
        targets=[t(image) for image in target_cpu]; masks=[]; initial_images=[]
        for camera,(k,e) in enumerate(cams):
            with torch.no_grad(): image,z,alpha=renderer.render(base,color,k,e,height,width)
            rgb=image.cpu().numpy(); al=alpha.cpu().numpy(); mask=eval_masks[camera]&(al>=.5)
            assert mask.any(); masks.append(torch.as_tensor(mask,device='cuda')); initial_images.append(rgb)
            np.savez_compressed(s/f'artifacts/renders/initial_frame_{camera}.npz',rgb=rgb,depth=z.cpu().numpy(),alpha=al,
                                target=target_cpu[camera],e1_mask=eval_masks[camera],train_mask=mask,coverage=al>=.5)
        def positions(parameter):
            return base.index_copy(0,idx,initial_active+rays*(distance*torch.expm1(parameter))[:,None])
        def photo(image,camera):
            return torch.sqrt((image-targets[camera]).square()+c['charbonnier_epsilon']**2)[masks[camera]].mean()
        def camera_loss(parameter,camera):
            image,_,_=renderer.render(positions(parameter),color,*cams[camera],height,width)
            return photo(image,camera)/3
        optimizer=torch.optim.Adam([delta],lr=c['learning_rate']); history=[]; steps=[]; best=float('inf'); beststep=0
        def checkpoint(step):
            nonlocal best,beststep
            with torch.no_grad():
                xyz=positions(delta); total=0.; rows=[]
                for camera,(k,e) in enumerate(cams):
                    image,_,alpha=renderer.render(xyz,color,k,e,height,width); total+=float(photo(image,camera))/3
                    rgb=image.cpu().numpy(); coverage=alpha.cpu().numpy()>=.5; mask=eval_masks[camera]
                    mse=float(((rgb-target_cpu[camera])**2)[mask].mean())
                    row={'camera':camera,'psnr_fixed_e1_mask':float(-10*np.log10(max(mse,1e-20))),
                         'coverage_all':float(coverage.mean()),'missing_e1_pixels':int((mask&~coverage).sum())}
                    if step==0:
                        row['initial_render_max_difference']=float(np.abs(rgb-initial_images[camera]).max())
                        assert row['initial_render_max_difference']<2e-6
                    rows.append(row)
                row={'step':step,'training_charbonnier':total,'frames':rows,'delta_abs_max':float(delta.abs().max()),
                     'points_at_bound':int((delta.abs()>=c['log_ray_delta_bound']-1e-6).sum())}
                history.append(row)
                state=optimizer.state_dict()
                cpu_state={key:{name:(value.detach().cpu() if torch.is_tensor(value) else value) for name,value in data.items()}
                           for key,data in state['state'].items()}
                torch.save({'step':step,'delta':delta.detach().cpu(),'active_indices':torch.as_tensor(active),
                            'optimizer':{'state':cpu_state,'param_groups':state['param_groups']},
                            'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state().cpu()},
                           s/f'artifacts/checkpoints/step_{step:04d}.pt')
                np.savez_compressed(s/f'artifacts/checkpoints/step_{step:04d}.npz',delta=delta.cpu().numpy(),active_indices=active)
                if total<best: best=total; beststep=step
                p.json_write(s/'evaluation/checkpoint_history.json',history); log(row)
        checkpoint(0); torch.cuda.synchronize(); start=time.perf_counter()
        for step in range(1,c['steps']+1):
            optimizer.zero_grad(set_to_none=True); total=0.
            for camera in range(3):
                loss=camera_loss(delta,camera); loss.backward(); total+=float(loss.detach()); del loss
            assert delta.grad is not None and torch.isfinite(delta.grad).all()
            gradient_norm=float(delta.grad.norm()); torch.nn.utils.clip_grad_norm_([delta],c['gradient_clip_norm'])
            optimizer.step()
            with torch.no_grad(): delta.clamp_(-c['log_ray_delta_bound'],c['log_ray_delta_bound'])
            steps.append({'step':step,'pre_update_photo_loss':total,'gradient_norm':gradient_norm})
            if step%c['checkpoint_interval']==0: checkpoint(step)
        torch.cuda.synchronize(); elapsed=time.perf_counter()-start
        assert any(row['gradient_norm']>0 for row in steps)
        for label,step in [('selected',beststep),('last',c['steps'])]:
            with np.load(s/f'artifacts/checkpoints/step_{step:04d}.npz') as data: parameter=data['delta'].astype(float)
            xyz=base64.copy(); xyz[active]+=rays64*(distance64*np.expm1(parameter))[:,None]
            np.savez_compressed(s/f'artifacts/maps/{label}_positions.npz',xyz=xyz,delta=parameter,active_indices=active)
            with torch.no_grad():
                delta.copy_(t(parameter)); current=positions(delta)
                for camera,(k,e) in enumerate(cams):
                    image,z,alpha=renderer.render(current,color,k,e,height,width)
                    np.savez_compressed(s/f'artifacts/renders/{label}_frame_{camera}.npz',rgb=image.cpu().numpy(),depth=z.cpu().numpy(),
                                        alpha=alpha.cpu().numpy(),coverage=alpha.cpu().numpy()>=.5,target=target_cpu[camera],
                                        e1_mask=eval_masks[camera],train_mask=masks[camera].cpu().numpy())
        # Finite differences include the hard visibility/stencil changes ignored by autograd.
        parameter=torch.zeros(len(active),device='cuda',requires_grad=True); initial_loss=0.
        for camera in range(3):
            loss=camera_loss(parameter,camera); loss.backward(); initial_loss+=float(loss.detach())
        gradient=parameter.grad.detach(); direction=-gradient/(gradient.abs()+1e-8); analytic=float((gradient*direction).sum()); probes=[]
        with torch.no_grad():
            for epsilon in [1e-6,1e-5,1e-4,.001]:
                plus=sum(float(camera_loss(direction*epsilon,camera)) for camera in range(3))
                minus=sum(float(camera_loss(-direction*epsilon,camera)) for camera in range(3))
                probes.append({'epsilon':epsilon,'plus_loss':plus,'minus_loss':minus,'central_derivative':(plus-minus)/(2*epsilon),
                               'first_order_predicted_plus':initial_loss+epsilon*analytic})
        p.json_write(s/'evaluation/direction_diagnostic.json',{'initial_loss':initial_loss,'gradient_norm':float(gradient.norm()),
                     'autograd_adam_direction_derivative':analytic,'probes':probes,
                     'scope':'full initial scene; changing hard visibility/stencil and float32 precision are included in finite differences'})
        result={'initial_points':len(base64),'active_points':len(active),'steps':c['steps'],'selected_step':beststep,
                'selected_by':'lowest checkpoint training Charbonnier; no GT',
                'initial_photo_loss':history[0]['training_charbonnier'],'selected_photo_loss':best,'last_photo_loss':history[-1]['training_charbonnier'],
                'optimization_seconds':elapsed,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
                'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),
                'driver_snapshot':subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,memory.used,driver_version','--format=csv,noheader'],text=True).strip(),
                'execution_context':'host GPU outside sandbox','gt_read_during_training':False}
        p.json_write(s/'evaluation/step_log.json',steps); p.json_write(s/'evaluation/training.json',result)
        events=json.loads((s/'progress.json').read_text()); events['events'].append({'time':p.stamp(),'phase':'trained',**result}); p.json_write(s/'progress.json',events)
        manifest.update(phase='trained',selected_step=beststep); p.json_write(s/'manifest.json',manifest); log(result)
    except Exception:
        log(traceback.format_exc()); manifest.update(status='failed',phase='training',error=traceback.format_exc()); p.json_write(s/'manifest.json',manifest); raise


if __name__=='__main__': main()
