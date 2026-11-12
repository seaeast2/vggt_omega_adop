"""Photo-only constrained ray-depth optimization; no GT access in this process."""
import argparse,importlib.util,json,time,hashlib,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import cv2,numpy as np,torch
spec=importlib.util.spec_from_file_location('p2','experiments/pointmap_refinement/P2/renderer.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def rec(p):
    p=Path(p)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args();c=json.loads(Path('experiments/pointmap_refinement/E3/config.json').read_text());parent=Path(c['parent_stage'])
    s=Path('results/pointmap_refinement')/a.run_id/'stages/E3';s.mkdir(parents=True,exist_ok=False)
    for n in ['logs','evaluation','artifacts/checkpoints','artifacts/maps','artifacts/renders','artifacts/source']:(s/n).mkdir(parents=True)
    (s/'manifest.json').write_text(json.dumps({'status':'running','experiment_code':'E3','run_id':a.run_id,'started_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat()}));(s/'config_resolved.json').write_text(json.dumps(c,indent=2))
    pm=json.loads((parent/'manifest.json').read_text());assert pm['status']=='completed'
    for row in pm['artifacts']:assert rec(row['path'])==row
    with np.load(parent/'artifacts/shared/shared_map_initial.npz') as d:shared={k:d[k] for k in d.files}
    with np.load(parent/'artifacts/shared/ray_initialization.npz') as d:active=np.flatnonzero(d['active_candidate']);rays=d['owner_ray_world'][active];distance=d['owner_ray_distance'][active]
    e1=Path(json.loads((parent/'config_resolved.json').read_text())['parent_stage'])
    with np.load(e1/'artifacts/f0/vggt_omega_raw.npz') as d:ks=d['intrinsics'][0];es=d['extrinsics'][0]
    def t(x):return torch.as_tensor(x,device='cuda',dtype=torch.float32)
    torch.manual_seed(c['seed']);torch.cuda.reset_peak_memory_stats()
    base=t(shared['xyz0']);color=t(shared['rgb_fixed']);idx=torch.as_tensor(active,device='cuda');ray=t(rays);dist=t(distance);initial_active=base[idx];delta=torch.nn.Parameter(torch.zeros(len(active),device='cuda'))
    h,w=c['render_hw'];aff=np.array([[.25,0,-.375],[0,.25,-.375],[0,0,1]],np.float32);cams=[(t(aff@k),t(e)) for k,e in zip(ks,es)];targets=[];fixed=[];evalmask=[]
    for i in range(3):
        with np.load(parent/'artifacts/renders'/f'f1_frame_{i}.npz') as d:
            targets.append(t(d['target']));m=d['initial_e1_mask'];train=m&d['coverage'];fixed.append(torch.as_tensor(train,device='cuda'));evalmask.append(m.copy())
        np.savez_compressed(s/'artifacts/source'/f'fixed_masks_{i}.npz',train_mask=train,e1_mask=m)
    def positions():return base.index_copy(0,idx,initial_active+ray*(dist*torch.expm1(delta))[:,None])
    def photo(image,i):return torch.sqrt((image-targets[i]).square()+c['charbonnier_epsilon']**2)[fixed[i]].mean()
    optimizer=torch.optim.Adam([delta],lr=c['learning_rate']);history=[];steps=[];best=float('inf');beststep=0
    def evaluate(step):
        nonlocal best,beststep
        with torch.no_grad():
            xyz=positions();loss=0.;rows=[]
            for i,(k,e) in enumerate(cams):
                image,z,alpha=mod.render(xyz,color,k,e,h,w);loss+=float(photo(image,i))/3
                out=image.cpu().numpy();al=alpha.cpu().numpy();target=targets[i].cpu().numpy();mask=evalmask[i];mse=float(((out-target)**2)[mask].mean());coverage=al>=.5
                rows.append({'frame':i,'psnr_fixed_e1_mask':float(-10*np.log10(mse)),'coverage_all':float(coverage.mean()),'missing_on_e1_mask':int((mask&~coverage).sum()),'mse_fixed_e1_mask':mse})
                if step==0:
                    with np.load(parent/'artifacts/renders'/f'f1_frame_{i}.npz') as old:rows[-1]['initial_rgb_max_difference_from_e2']=float(np.abs(old['rgb']-out).max())
            row={'step':step,'training_charbonnier':loss,'frames':rows,'delta_abs_max':float(delta.abs().max()),'points_at_bound':int((delta.abs()>=c['log_ray_delta_bound']-1e-6).sum())};history.append(row)
            data={'step':step,'delta':delta.detach().cpu(),'active_indices':torch.as_tensor(active),'optimizer':{k:{sk:(sv.detach().cpu() if torch.is_tensor(sv) else sv) for sk,sv in v.items()} for k,v in optimizer.state_dict()['state'].items()},'param_groups':optimizer.state_dict()['param_groups'],'cuda_rng':torch.cuda.get_rng_state().cpu(),'torch_rng':torch.get_rng_state()}
            torch.save(data,s/'artifacts/checkpoints'/f'step_{step:04d}.pt')
            np.savez_compressed(s/'artifacts/checkpoints'/f'step_{step:04d}.npz',delta=delta.cpu().numpy(),active_indices=active)
            if loss<best:best=loss;beststep=step
            (s/'evaluation/checkpoint_history.json').write_text(json.dumps(history,indent=2));print('checkpoint',step,loss,rows,flush=True)
    evaluate(0);torch.cuda.synchronize();start=time.perf_counter()
    try:
        for step in range(1,c['steps']+1):
            optimizer.zero_grad(set_to_none=True);total=0.
            # Sequential camera graphs keep full-scene rendering within VRAM.
            for i,(k,e) in enumerate(cams):
                xyz=positions();image,_,_=mod.render(xyz,color,k,e,h,w);loss=photo(image,i)/3;loss.backward();total+=float(loss.detach());del xyz,image,loss
            assert torch.isfinite(delta.grad).all();gn=float(delta.grad.norm());torch.nn.utils.clip_grad_norm_([delta],c['gradient_clip_norm']);optimizer.step()
            with torch.no_grad():delta.clamp_(-c['log_ray_delta_bound'],c['log_ray_delta_bound'])
            steps.append({'step':step,'pre_update_photo_loss':total,'delta_gradient_norm':gn})
            if step%c['checkpoint_interval']==0:evaluate(step)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start
        for label,step in [('selected',beststep),('last',c['steps'])]:
            with np.load(s/'artifacts/checkpoints'/f'step_{step:04d}.npz') as d:parameter=d['delta'].astype('float64')
            xyz64=shared['xyz0'].copy();xyz64[active]+=rays*(distance*np.expm1(parameter))[:,None]
            np.savez_compressed(s/'artifacts/maps'/f'{label}_positions.npz',xyz=xyz64,delta=parameter,active_indices=active)
            # Save images from the same float32 parameterization used in training.
            with torch.no_grad():
                delta.copy_(t(parameter));xyz=positions()
                for i,(k,e) in enumerate(cams):
                    image,z,alpha=mod.render(xyz,color,k,e,h,w);np.savez_compressed(s/'artifacts/renders'/f'{label}_frame_{i}.npz',rgb=image.cpu().numpy(),depth=z.cpu().numpy(),alpha=alpha.cpu().numpy(),coverage=alpha.cpu().numpy()>=.5,target=targets[i].cpu().numpy(),e1_mask=evalmask[i],train_mask=fixed[i].cpu().numpy())
        result={'active_points':len(active),'total_points':len(base),'selected_step':beststep,'selected_by':'lowest checkpoint training Charbonnier; no GT','initial_photo_loss':history[0]['training_charbonnier'],'selected_photo_loss':best,'last_photo_loss':history[-1]['training_charbonnier'],'steps':c['steps'],'optimization_seconds':elapsed,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'parent_manifest':rec(parent/'manifest.json'),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),'project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'execution_context':'host GPU outside sandbox','gt_accessed_during_training':False}
        (s/'evaluation/training.json').write_text(json.dumps(result,indent=2));(s/'evaluation/step_log.json').write_text(json.dumps(steps,indent=2));print(json.dumps(result,indent=2))
    except Exception as error:
        (s/'manifest.json').write_text(json.dumps({'status':'failed','error':str(error),'last_step':step},indent=2));raise


if __name__=='__main__':main()
