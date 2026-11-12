"""E1 fixed-pixel diagnostics and unchanged-renderer F0/F1 comparison."""
import argparse,importlib.util,json,time
from pathlib import Path
import cv2,numpy as np,torch
spec=importlib.util.spec_from_file_location('e1','experiments/pointmap_refinement/E1/geometry.py');e1=importlib.util.module_from_spec(spec);spec.loader.exec_module(e1)
spec=importlib.util.spec_from_file_location('p2','experiments/pointmap_refinement/P2/renderer.py');p2=importlib.util.module_from_spec(spec);spec.loader.exec_module(p2)

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());source=Path(c['parent_stage'])
with np.load(source/'artifacts/f0/vggt_omega_raw.npz') as d:depth=d['depth'][0,...,0].astype('float64');ks=d['intrinsics'][0];es=d['extrinsics'][0]
with np.load(source/'artifacts/f0/observations.npz') as d:obs={key:d[key] for key in d.files}
with np.load(s/'artifacts/shared/shared_map_initial.npz') as d:shared={key:d[key] for key in d.files}
xyz=shared['xyz'];observed=shared['observed_camera_mask'];n,h,w=depth.shape;pairs=[];layers=[]
for j in range(n):
    maps=[];ids=[]
    for i in range(n):
        selected=np.flatnonzero(observed[:,i]);z,win,_=e1.front_map(xyz[selected],ks[j].astype('float64'),es[j].astype('float64'),h,w);gid=np.full((h,w),-1,np.int64);hit=win>=0;gid[hit]=selected[win[hit]];maps.append(z);ids.append(gid)
        if i==j:continue
        with np.load(source/'artifacts/diagnostics'/f'pair_{i}_to_{j}.npz') as old:fixed=old['evaluation_mask'];target=old['target_initial_depth'];before=old['source_front_depth']
        valid=fixed&np.isfinite(z);rel=np.abs(z[valid]-target[valid])/target[valid];oldrel=np.abs(before[fixed]-target[fixed])/target[fixed]
        pairs.append({'source':i,'target':j,'fixed_pixels':int(fixed.sum()),'covered_after':int(valid.sum()),'missing_after':int((fixed&~valid).sum()),'coverage_of_fixed':float(valid.sum()/fixed.sum()),'before_abs_relative':e1.stats(oldrel),'after_abs_relative_covered_only':e1.stats(rel),'before_disagreement_fraction':float(np.mean(oldrel>.03)),'after_disagreement_covered_only':float(np.mean(rel>.03)),'warning':'after residual excludes missing but missing counts explicitly retained; not a full fixed-mask accuracy score'})
        np.savez_compressed(s/'artifacts/diagnostics'/f'pair_{i}_to_{j}.npz',fixed_evaluation_mask=fixed,covered_after=valid,front_depth_after=z,target_initial_depth=target)
    maps=np.stack(maps);ids=np.stack(ids);support=np.isfinite(maps).sum(0)
    with np.load(source/'artifacts/diagnostics'/f'layers_target_{j}.npz') as old:fixed=old['layer_evaluation_mask'];before=old['relative_layer_spread']
    valid=fixed&(support>=2);low=np.where(np.isfinite(maps),maps,np.inf).min(0);high=np.where(np.isfinite(maps),maps,-np.inf).max(0);spread=(high-low)/depth[j]
    gid_min=np.where(ids>=0,ids,np.iinfo(np.int64).max).min(0);gid_max=ids.max(0);identical=valid&(gid_min==gid_max);independent=valid&~identical
    layers.append({'target':j,'fixed_pixels':int(fixed.sum()),'after_two_view_pixels':int(valid.sum()),'missing_after':int((fixed&~valid).sum()),'before_relative_spread':e1.stats(before[fixed]),'after_relative_spread_covered_only':e1.stats(spread[valid]),'same_shared_point_pixels':int(identical.sum()),'distinct_shared_point_pixels':int(independent.sum()),'distinct_point_spread':e1.stats(spread[independent]),'warning':'same shared point gives zero spread by construction, not independent confirmation'})
    np.savez_compressed(s/'artifacts/diagnostics'/f'layers_target_{j}.npz',fixed_evaluation_mask=fixed,covered_after=valid,relative_spread_after=spread,same_shared_point_mask=identical)
(s/'evaluation/geometry_comparison.json').write_text(json.dumps({'pairs':pairs,'layers':layers,'gt_accuracy_evaluated':False},indent=2));print('geometry comparison completed',flush=True)
def t(x):return torch.as_tensor(x,device='cuda',dtype=torch.float32)
rh,rw=c['render_hw'];aff=np.array([[rw/w,0,(rw/w-1)/2],[0,rh/h,(rh/h-1)/2],[0,0,1]],np.float32);torch.cuda.reset_peak_memory_stats();rows=[]
for i in range(3):
    with np.load(source/'artifacts/renders'/f'all_frame_{i}.npz') as old:target=old['target'];oldrgb=old['rgb']
    with np.load(source/'artifacts/renders'/f'evaluation_masks_frame_{i}.npz') as old:fixed=old['fixed_all_mask']
    outputs={};coverage={}
    for name,x,col in [('f0',obs['world_xyz_initial'],obs['rgb']/255.),('f1',xyz,shared['rgb_fixed'])]:
        x=t(x);col=t(col);torch.cuda.synchronize();start=time.perf_counter()
        with torch.no_grad():out,z,al=p2.render(x,col,t(aff@ks[i]),t(es[i]),rh,rw)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start;image=out.cpu().numpy();dep=z.cpu().numpy();alpha=al.cpu().numpy();mask=alpha>=.5
        assert np.isfinite(image).all() and np.isfinite(dep).all();outputs[name]=image;coverage[name]=mask
        np.savez_compressed(s/'artifacts/renders'/f'{name}_frame_{i}.npz',rgb=image,depth=dep,alpha=alpha,coverage=mask,target=target,initial_e1_mask=fixed)
        mse=float(((image-target)**2)[fixed].mean());rows.append({'frame':i,'method':name,'points':len(x),'fixed_pixels':int(fixed.sum()),'missing_on_fixed':int((fixed&~mask).sum()),'coverage_all':float(mask.mean()),'coverage_of_fixed':float(mask[fixed].mean()),'psnr_fixed_e1_mask':float(-10*np.log10(mse)),'psnr_all_pixels':float(-10*np.log10(((image-target)**2).mean())),'render_seconds':elapsed,'max_rgb_difference_from_archived_f0':float(np.abs(image-oldrgb).max()) if name=='f0' else None})
        del x,col,out,z,al
    common=fixed&coverage['f0']&coverage['f1']
    for row in rows[-2:]:row.update(common_pixels=int(common.sum()),psnr_common_mask=float(-10*np.log10(((outputs[row['method']]-target)**2)[common].mean())))
    panel=np.full((rh+30,rw*4,3),255,np.uint8);error=np.abs(outputs['f1']-target).mean(-1);heat=cv2.applyColorMap(np.rint(np.clip(error/.2,0,1)*255).astype('uint8'),cv2.COLORMAP_TURBO)
    for j,(name,im) in enumerate([('target',target),('F0',outputs['f0']),('F1',outputs['f1'])]):
        panel[30:,j*rw:(j+1)*rw]=np.rint(im.clip(0,1)*255).astype('uint8')[...,::-1];cv2.putText(panel,name,(j*rw+4,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
    panel[30:,3*rw:]=heat;cv2.putText(panel,'F1 err 0-.2',(3*rw+3,20),cv2.FONT_HERSHEY_SIMPLEX,.35,(0,0,0),1);cv2.imwrite(str(s/'artifacts/renders'/f'comparison_{i}.png'),panel)
(s/'evaluation/render_comparison.json').write_text(json.dumps({'frames':rows,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),'execution_context':'host GPU outside sandbox','position_optimization':False,'opacity_note':'same radius and unit contribution per representative; fewer points can reduce alpha independently of geometry'},indent=2));print(json.dumps(rows,indent=2))
