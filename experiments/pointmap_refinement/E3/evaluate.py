"""Post-training geometry/GT evaluation and exports; GT cannot select a checkpoint."""
import argparse,json,shutil
from pathlib import Path
import cv2,numpy as np
from train import rec
import importlib.util
spec=importlib.util.spec_from_file_location('e1','experiments/pointmap_refinement/E1/geometry.py');e1=importlib.util.module_from_spec(spec);spec.loader.exec_module(e1)
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());parent=Path(c['parent_stage']);e1stage=Path(json.loads((parent/'config_resolved.json').read_text())['parent_stage'])
with np.load(parent/'artifacts/shared/shared_map_initial.npz') as d:shared={key:d[key] for key in d.files}
with np.load(parent/'artifacts/shared/ray_initialization.npz') as d:ray=d['owner_ray_world'];distance=d['owner_ray_distance'];active=np.flatnonzero(d['active_candidate'])
with np.load(e1stage/'artifacts/f0/vggt_omega_raw.npz') as d:ks=d['intrinsics'][0].astype('float64');es=d['extrinsics'][0].astype('float64');initial_depth=d['depth'][0,...,0].astype('float64');confidence=d['depth_conf'][0]
points={'initial':shared['xyz0']};params={}
for name in ['selected','last']:
    with np.load(s/'artifacts/maps'/f'{name}_positions.npz') as d:points[name]=d['xyz'];params[name]=d['delta']
    assert np.array_equal(points[name][np.setdiff1d(np.arange(len(points[name])),active)],points['initial'][np.setdiff1d(np.arange(len(points[name])),active)])
    assert np.allclose(points[name][active],points['initial'][active]+ray[active]*(distance[active]*np.expm1(params[name]))[:,None],atol=1e-12)
    assert np.max(np.abs(params[name]))<=c['log_ray_delta_bound']+1e-7
shutil.copy2(parent/'artifacts/shared/shared_map_initial.ply',s/'artifacts/maps/shared_map_initial.ply')
n,h,w=initial_depth.shape;centres=np.stack([-e[:,:3].T@e[:,3] for e in es]);current_vis={};native={};movement={}
for name,xyz in points.items():
    native[name]=[];visibility=[]
    for i in range(3):
        zmap,_,_=e1.front_map(xyz,ks[i],es[i],h,w);native[name].append(zmap)
        cam=xyz@es[i,:,:3].T+es[i,:,3];z=cam[:,2];q=(cam@ks[i].T)[:,:2]/z[:,None];inside=(z>0)&(q[:,0]>=0)&(q[:,0]<=w-1)&(q[:,1]>=0)&(q[:,1]<=h-1);ids=np.flatnonzero(inside);uv=np.rint(q[ids]).astype(int);target=initial_depth[i,uv[:,1],uv[:,0]];front=zmap[uv[:,1],uv[:,0]];safe=e1.edge_safe(initial_depth[i],.03)
        v=np.zeros(len(xyz),bool);v[ids]=safe[uv[:,1],uv[:,0]]&(confidence[i,uv[:,1],uv[:,0]]>=np.percentile(confidence[i],10))&(z[ids]<=front*1.03)&(np.abs(z[ids]-target)<=np.median(initial_depth)*.002+.03*target);visibility.append(v)
    current_vis[name]=np.stack(visibility,1)
    if name=='initial':continue
    disp=np.linalg.norm(xyz-points['initial'],axis=1);movement[name]={'all_points':e1.stats(disp),'active_points':e1.stats(disp[active]),'active_relative_ray_distance':e1.stats(np.abs(np.expm1(params[name]))),'moved_active_over_1e_8':int((disp[active]>1e-8).sum()),'active_at_log_bound':int((np.abs(params[name])>=c['log_ray_delta_bound']-1e-6).sum()),'visible_in_at_least_two':int((current_vis[name].sum(1)>=2).sum())}
    payload=shared.copy();payload['xyz']=xyz;payload['visibility_initial']=shared['visibility_estimated'];payload['visibility_estimated']=current_vis[name];payload['optimized_indices']=active;payload['log_ray_delta']=params[name]
    np.savez_compressed(s/'artifacts/maps'/f'shared_map_{name}.npz',**payload)
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('n_observed','u1'),('owner','<i2')]);data=np.empty(len(xyz),dtype)
    for j,key in enumerate(['x','y','z']):data[key]=xyz[:,j]
    color=np.rint(shared['rgb_fixed']*255).clip(0,255).astype('uint8')
    for j,key in enumerate(['red','green','blue']):data[key]=color[:,j]
    data['n_observed']=shared['n_observed'];data['owner']=shared['owner_camera']
    header=f'ply\nformat binary_little_endian 1.0\ncomment E3 {name}; model world scale; fixed RGB and topology\nelement vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar n_observed\nproperty short owner\nend_header\n'
    with (s/'artifacts/maps'/f'shared_map_{name}.ply').open('wb') as f:f.write(header.encode());data.tofile(f)
    with (s/'artifacts/maps'/f'shared_map_{name}.ply').open('rb') as f:
        while f.readline()!=b'end_header\n':pass
        loaded=np.fromfile(f,dtype=dtype)
    assert np.array_equal(data,loaded)
    with np.load(s/'artifacts/maps'/f'shared_map_{name}.npz') as d:
        for key in payload:assert np.array_equal(d[key],payload[key])
# GT loaded only after fixed training selection. One initial-only scale, all methods unchanged.
gtstage=Path(c['gt_stage']);gtmanifest=json.loads((gtstage/'manifest.json').read_text());assert gtmanifest['status']=='completed';gt=[];gt_records=[]
for i in range(3):
    path=gtstage/'artifacts/gt'/f'aligned_{i}.npz';row=next(x for x in gtmanifest['artifacts'] if x['path']==str(path));assert rec(path)==row;gt_records.append(row)
    with np.load(path) as d:gt.append(d['depth_m'])
fixed=[np.isfinite(native['initial'][i])&(native['initial'][i]>0)&(gt[i]>0) for i in range(3)]
scale=float(np.median(np.concatenate([gt[i][fixed[i]]/native['initial'][i][fixed[i]] for i in range(3)])))
common=[fixed[i]&np.isfinite(native['selected'][i])&np.isfinite(native['last'][i]) for i in range(3)]
gtrows=[]
for name in points:
    errors=[];relative=[]
    for i in range(3):
        valid=fixed[i]&np.isfinite(native[name][i]);mask=common[i];err=native[name][i][mask]*scale-gt[i][mask];rel=np.abs(err)/gt[i][mask];errors.append(err);relative.append(rel)
        gtrows.append({'method':name,'frame':i,'fixed_initial_gt_pixels':int(fixed[i].sum()),'covered_fixed_pixels':int(valid.sum()),'coverage_of_fixed':float(valid.sum()/fixed[i].sum()),'common_pixels':int(mask.sum()),'rmse_m_common':float(np.sqrt(np.mean(err**2))),'absrel_common':float(rel.mean())})
        np.savez_compressed(s/'artifacts/renders'/f'native_depth_{name}_{i}.npz',depth_model=native[name][i],fixed_gt_mask=fixed[i],common_gt_mask=mask)
    errors=np.concatenate(errors);relative=np.concatenate(relative);gtrows.append({'method':name,'frame':'pooled','common_pixels':len(errors),'rmse_m_common':float(np.sqrt(np.mean(errors**2))),'absrel_common':float(relative.mean())})
(s/'evaluation/gt_depth.json').write_text(json.dumps({'scale_gt_m_per_model_unit':scale,'scale_fit':'median GT/initial E2 native nearest-pixel front depth; one global factor across three cameras; never refit','gt_files':gt_records,'gt_used_in_training_or_selection':False,'rows':gtrows,'limitations':'same-input-view, scale-aligned image depth only; common mask depends on all output coverages; all fixed-mask coverage also reported; no heldout or full 3D accuracy claim'},indent=2))
# E1 fixed source/target-pixel probes, using the unchanged observation groups.
pairs=[];observed=shared['observed_camera_mask']
for name,xyz in points.items():
    for j in range(3):
        for i in range(3):
            if i==j:continue
            z,_,_=e1.front_map(xyz[observed[:,i]],ks[j],es[j],h,w)
            with np.load(e1stage/'artifacts/diagnostics'/f'pair_{i}_to_{j}.npz') as d:mask=d['evaluation_mask'];target=d['target_initial_depth']
            covered=mask&np.isfinite(z);rel=np.abs(z[covered]-target[covered])/target[covered]
            pairs.append({'method':name,'source':i,'target':j,'fixed_pixels':int(mask.sum()),'covered_pixels':int(covered.sum()),'relative_depth_error_covered_only':e1.stats(rel)})
(s/'evaluation/predicted_consistency.json').write_text(json.dumps(pairs,indent=2));(s/'evaluation/displacement.json').write_text(json.dumps(movement,indent=2))
for i in range(3):
    with np.load(parent/'artifacts/renders'/f'f1_frame_{i}.npz') as d:initial=d['rgb'];target=d['target']
    with np.load(s/'artifacts/renders'/f'last_frame_{i}.npz') as d:last=d['rgb']
    with np.load(s/'artifacts/renders'/f'selected_frame_{i}.npz') as d:selected=d['rgb']
    rh,rw=target.shape[:2];panel=np.full((rh+30,rw*4,3),255,np.uint8)
    for col,(label,image) in enumerate([('target',target),('initial',initial),('selected',selected),('last',last)]):
        panel[30:,col*rw:(col+1)*rw]=np.rint(image.clip(0,1)*255).astype('uint8')[...,::-1];cv2.putText(panel,label,(col*rw+3,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
    assert cv2.imwrite(str(s/'artifacts/renders'/f'comparison_{i}.png'),panel)
(s/'evaluation/verification.json').write_text(json.dumps({'ray_parameterization':'passed','log_bounds_and_positive_distance':'passed','inactive_xyz_unchanged':'passed','all_other_shared_fields_frozen_except_current_visibility_and_optimizer_metadata':'passed','ply_npz_reload':'passed','gt_hash_and_initial_only_global_scale':'passed','status':'passed'},indent=2))
print(json.dumps({'scale':scale,'displacement':movement,'pooled_gt':[r for r in gtrows if r['frame']=='pooled']},indent=2))
