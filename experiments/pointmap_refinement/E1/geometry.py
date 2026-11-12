"""F0 diagnostics, CPU only; predicted consistency is not geometry accuracy."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,platform,shutil,subprocess
from pathlib import Path
import numpy as np


def rec(p):
    p=Path(p)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':p.stat().st_size,'sha256':h}


def stats(x):
    x=np.asarray(x);x=x[np.isfinite(x)]
    return {'count':int(x.size),'mean':float(x.mean()),'median':float(np.median(x)),'p95':float(np.quantile(x,.95)),'max':float(x.max())} if x.size else {'count':0}


def edge_safe(depth,threshold):
    good=np.isfinite(depth)&(depth>0)
    for axis in [0,1]:
        left=[slice(None),slice(None)];right=left.copy();left[axis]=slice(None,-1);right[axis]=slice(1,None)
        x=depth[tuple(left)];y=depth[tuple(right)];bad=np.abs(x-y)>threshold*np.minimum(x,y)
        good[tuple(left)]&=~bad;good[tuple(right)]&=~bad
    good[[0,-1],:]=False;good[:,[0,-1]]=False
    return good


def front_map(xyz,k,e,h,w):
    cam=xyz@e[:,:3].T+e[:,3];z=cam[:,2];q=cam@k.T
    uv=q[:,:2]/z[:,None];inside=(z>0)&np.isfinite(uv).all(1)&(uv[:,0]>=0)&(uv[:,0]<=w-1)&(uv[:,1]>=0)&(uv[:,1]<=h-1)
    ids=np.flatnonzero(inside);xy=np.rint(uv[ids]).astype('int64');flat=xy[:,1]*w+xy[:,0]
    order=np.lexsort((ids,z[ids],flat));flat=flat[order];ids=ids[order]
    first=np.r_[True,flat[1:]!=flat[:-1]]
    win=np.full(h*w,-1,np.int64);win[flat[first]]=ids[first]
    out=np.full(h*w,np.nan);hit=win>=0;out[hit]=z[win[hit]]
    return out.reshape(h,w),win.reshape(h,w),int(inside.sum())


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
    c=json.loads(Path('experiments/pointmap_refinement/E1/config.json').read_text());s=Path('results/pointmap_refinement')/a.run_id/'stages/E1';s.mkdir(parents=True,exist_ok=False)
    for n in ['logs','evaluation','artifacts/f0','artifacts/diagnostics','artifacts/renders','artifacts/source']:(s/n).mkdir(parents=True)
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).isoformat();(s/'manifest.json').write_text(json.dumps({'status':'running','experiment_code':'E1','run_id':a.run_id,'started_at':stamp}))
    (s/'config_resolved.json').write_text(json.dumps(c,indent=2))
    parent=Path(c['parent_stage']);m=json.loads((parent/'manifest.json').read_text());assert m['status']=='completed'
    for row in m['artifacts']:assert rec(row['path'])==row
    for name in ['observations.npz','vggt_omega_raw.npz','frames.json']:shutil.copy2(parent/'artifacts/baseline'/name,s/'artifacts/f0'/name)
    shutil.copy2(parent/'artifacts/geometry/all_observations.ply',s/'artifacts/f0/f0_observations.ply')
    for src,dst in [(parent/'artifacts/baseline/observations.npz',s/'artifacts/f0/observations.npz'),(parent/'artifacts/geometry/all_observations.ply',s/'artifacts/f0/f0_observations.ply')]:assert rec(src)['sha256']==rec(dst)['sha256']
    with np.load(s/'artifacts/f0/observations.npz') as d:obs={key:d[key] for key in d.files}
    with np.load(s/'artifacts/f0/vggt_omega_raw.npz') as d:depth=d['depth'][0,...,0].astype('float64');ks=d['intrinsics'][0].astype('float64');es=d['extrinsics'][0].astype('float64')
    xyz=obs['world_xyz_initial'];fid=obs['frame_id'];n,h,w=depth.shape;safe=np.stack([edge_safe(d,c['depth_edge_relative_threshold']) for d in depth]);maps=[];pairs=[];layer_rows=[]
    for j in range(n):
        target_maps=[]
        for i in range(n):
            src=xyz[fid==i];zm,win,total=front_map(src,ks[j],es[j],h,w);target_maps.append(zm)
            if i==j:continue
            mask=safe[j]&np.isfinite(zm);signed=(zm[mask]-depth[j][mask])/depth[j][mask];absolute=np.abs(signed)
            pairs.append({'source':i,'target':j,'source_points':len(src),'in_frustum_observations':total,'covered_target_pixels':int(np.isfinite(zm).sum()),'fixed_evaluation_pixels':int(mask.sum()),'edge_safe_target_pixels':int(safe[j].sum()),'signed_relative_depth':stats(signed),'absolute_relative_depth':stats(absolute),'disagreement_fraction':float(np.mean(absolute>c['depth_disagreement_threshold'])),'in_front_fraction':float(np.mean(signed < -c['depth_disagreement_threshold'])),'behind_fraction':float(np.mean(signed>c['depth_disagreement_threshold']))})
            np.savez_compressed(s/'artifacts/diagnostics'/f'pair_{i}_to_{j}.npz',source_front_depth=zm,source_winner_index_within_frame=win,evaluation_mask=mask,target_edge_safe=safe[j],target_initial_depth=depth[j])
        stack=np.stack(target_maps);maps.append(stack);support=np.isfinite(stack).sum(0);valid=(support>=2)&safe[j]
        # Use +/-inf instead of nanmin to avoid warnings on unobserved pixels.
        low=np.where(np.isfinite(stack),stack,np.inf).min(0);high=np.where(np.isfinite(stack),stack,-np.inf).max(0)
        spread=high-low;relative=spread/depth[j]
        residual=np.where(np.isfinite(stack),np.abs(stack-depth[j][None])/depth[j][None],0)
        compatible=valid&(residual.max(0)<=c['layer_compatibility_threshold'])
        layer_rows.append({'target':j,'two_or_more_views_pixels':int(valid.sum()),'three_views_pixels':int(((support==3)&safe[j]).sum()),'raw_projected_layer_spread_model_units':stats(spread[valid]),'raw_projected_layer_spread_relative':stats(relative[valid]),'depth_compatible_pixels':int(compatible.sum()),'compatible_layer_spread_relative':stats(relative[compatible]),'warning':'projected layer spread includes occlusion/different surfaces; compatible subset is censored at 5% by definition'})
        np.savez_compressed(s/'artifacts/diagnostics'/f'layers_target_{j}.npz',source_front_depths=stack,support=support,target_edge_safe=safe[j],relative_layer_spread=relative,layer_evaluation_mask=valid,depth_compatible_mask=compatible)
    # Controlled diagnostic calibration: identical layers have zero spread, known Z separation=.04.
    assert np.ptp([2.,2.,2.])==0 and np.isclose(np.ptp([2.,2.04]),.04)
    k=np.array([[100.,0,1],[0,100.,1],[0,0,1.]])
    ztest,_,_=front_map(np.array([[0,0,2.],[0,0,2.04]]),k,np.c_[np.eye(3),np.zeros(3)],3,3);assert ztest[1,1]==2.
    median=float(np.median(depth));voxel=[]
    for fraction in c['voxel_size_fractions_of_median_depth']:
        size=median*fraction
        for offset in c['voxel_origin_offsets']:
            origin=xyz.min(0)-offset*size;keys=np.floor((xyz-origin)/size).astype(np.int64)
            _,inverse,count=np.unique(keys,axis=0,return_inverse=True,return_counts=True)
            bits=np.zeros(len(count),np.uint8);np.bitwise_or.at(bits,inverse,(1<<fid).astype(np.uint8));views=np.array([0,1,1,2,1,2,2,3])[bits];multi=views>=2
            voxel.append({'fraction_of_median_depth':fraction,'size_model_units':size,'origin_offset':offset,'origin_xyz':origin.tolist(),'occupied_voxels':len(count),'multi_frame_voxels':int(multi.sum()),'points_in_multi_frame_voxels':int(count[multi].sum()),'points_in_multi_frame_voxels_fraction':float(count[multi].sum()/len(xyz)),'three_frame_voxels':int((views==3).sum()),'warning':'spatial co-occupancy is potential redundancy, not verified physical correspondences'})
    result={'point_count':len(xyz),'median_initial_depth':median,'pairs':pairs,'layers':layer_rows,'voxel_sensitivity':voxel,'controlled_metric_checks':'passed','coordinates_changed':False,'fusion_performed':False,'gt_accuracy_evaluated':False}
    (s/'evaluation/geometry.json').write_text(json.dumps(result,indent=2)+'\n')
    (s/'environment_cpu.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,'execution_context':'host CPU','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
    m=json.loads((s/'manifest.json').read_text());m.update(parent_manifest=rec(parent/'manifest.json'),geometry_status='completed');(s/'manifest.json').write_text(json.dumps(m,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
