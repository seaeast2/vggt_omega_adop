"""E0b projective depth averaging with full original-observation RGB range gates."""
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


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def fuse(base,xyz,owner,uv,rgb_min,rgb_max,target_xyz,target_depth,target_rgb,target_id,k,e,threshold):
    height,width=target_depth.shape;target=target_rgb.reshape(-1,3).astype(np.int16)
    old_ids,flat,z=base.project_old(xyz,k,e,height,width)
    valid=np.isfinite(target_depth.ravel()[flat])&(target_depth.ravel()[flat]>0)
    old_ids,flat,z=old_ids[valid],flat[valid],z[valid]
    old_min=rgb_min[old_ids].astype(np.int16);old_max=rgb_max[old_ids].astype(np.int16)
    score=np.maximum(np.abs(old_min-target[flat]),np.abs(old_max-target[flat])).max(1)
    individual=(np.maximum(old_max,target[flat])-np.minimum(old_min,target[flat])).max(1)<=threshold
    accept=np.zeros(len(old_ids),bool);new_min=target.copy();new_max=target.copy()
    order=np.lexsort((old_ids,score,flat));sorted_flat=flat[order]
    if len(order):
        starts=np.flatnonzero(np.r_[True,sorted_flat[1:]!=sorted_flat[:-1]])
        ranks=np.arange(len(order))-np.repeat(starts,np.diff(np.r_[starts,len(order)]))
        for rank in range(int(ranks.max())+1):
            candidates=order[ranks==rank];pixels=flat[candidates]
            lo=np.minimum(new_min[pixels],old_min[candidates]);hi=np.maximum(new_max[pixels],old_max[candidates])
            good=(hi-lo).max(1)<=threshold
            chosen=candidates[good];accept[chosen]=True
            new_min[flat[chosen]]=lo[good];new_max[flat[chosen]]=hi[good]
    reason=np.where(accept,0,np.where(individual,2,1)).astype(np.uint8)
    accepted_ids=old_ids[accept];accepted_flat=flat[accept]
    count=np.bincount(accepted_flat,minlength=height*width);zsum=np.bincount(accepted_flat,weights=z[accept],minlength=height*width)
    reject_count=np.bincount(flat[~accept],minlength=height*width)
    mean_z=(target_depth.ravel()+zsum)/(1+count);touched=np.flatnonzero(count)
    target_new=target_xyz.copy();target_new[touched]=base.unproject(touched,mean_z[touched],k,e,width)
    keep=np.ones(len(xyz),bool);keep[accepted_ids]=False;nkeep=int(keep.sum())
    old_to_new=np.empty(len(xyz),np.int64);old_to_new[keep]=np.arange(nkeep);old_to_new[accepted_ids]=nkeep+accepted_flat
    grid=np.indices((height,width))[::-1].reshape(2,-1).T.astype(np.int32)
    out={'xyz':np.vstack([xyz[keep],target_new]),'owner':np.r_[owner[keep],np.full(height*width,target_id,np.int16)],
         'uv':np.vstack([uv[keep],grid]),'rgb_min':np.vstack([rgb_min[keep],new_min.astype(np.uint8)]),
         'rgb_max':np.vstack([rgb_max[keep],new_max.astype(np.uint8)]),'old_to_new':old_to_new,
         'old_removed':~keep,'candidate_old_id':old_ids,'candidate_target_flat':flat,'candidate_color_score':score,
         'candidate_accepted':accept,'candidate_rejection_reason':reason,
         'target_old_point_count':count.reshape(height,width),'target_rejected_point_count':reject_count.reshape(height,width),
         'target_mean_z':mean_z.reshape(height,width)}
    assert np.array_equal(out['xyz'][:nkeep],xyz[keep])
    assert np.array_equal(target_new[count==0],target_xyz[count==0])
    assert not np.any(out['old_removed'][old_ids[~accept]])
    assert np.max(out['rgb_max'].astype(np.int16)-out['rgb_min'].astype(np.int16))<=threshold
    camera=target_new[touched]@e[:,:3].T+e[:,3]
    projected=(camera@k.T)[:,:2]/camera[:,2,None]
    assert np.max(np.abs(projected-grid[touched]),initial=0)<1e-7
    assert np.max(np.abs(camera[:,2]-mean_z[touched]),initial=0)<1e-9
    out['metrics']={'target_camera':target_id,'old_representatives':len(xyz),'projected_candidates':len(old_ids),
                    'accepted_old_points':int(accept.sum()),'color_rejected_points':int((~accept).sum()),
                    'individual_color_rejections':int((reason==1).sum()),'union_color_rejections':int((reason==2).sum()),
                    'kept_old_points':nkeep,'touched_target_pixels':len(touched),'new_target_points':height*width,
                    'output_points':len(out['xyz']),'target_xyz_displacement_max':float(np.linalg.norm(target_new-target_xyz,axis=1).max())}
    return out


def controls(base):
    k=np.eye(3);e=np.c_[np.eye(3),np.zeros(3)];depth=np.full((2,2),6.)
    target=base.unproject(np.arange(4),depth.ravel(),k,e,2);old=np.array([[0.,0,2.],[0,0,4.],[20,0,2.]])
    owner=np.zeros(3,np.int16);uv=np.zeros((3,2),np.int32)
    rgb=np.array([[100,100,100],[105,105,105],[255,0,0]],np.uint8);trgb=np.full((4,3),110,np.uint8)
    out=fuse(base,old,owner,uv,rgb,rgb,target,depth,trgb,1,k,e,30)
    assert np.array_equal(out['xyz'][0],old[2]) and np.array_equal(out['xyz'][1],[0,0,4])
    assert out['metrics']['accepted_old_points']==2
    trgb=np.full((4,3),100,np.uint8);rgb=np.array([[70,70,70],[130,130,130],[255,0,0]],np.uint8)
    out=fuse(base,old,owner,uv,rgb,rgb,target,depth,trgb,1,k,e,30)
    assert out['candidate_accepted'].tolist()==[True,False]
    assert out['candidate_rejection_reason'].tolist()==[0,2]
    assert np.array_equal(out['xyz'][0],old[1])
    single=old[:1];sowner=owner[:1];suv=uv[:1]
    for difference,expected in [(30,True),(31,False)]:
        rgb=np.full((1,3),100+difference,np.uint8)
        result=fuse(base,single,sowner,suv,rgb,rgb,target,depth,trgb,1,k,e,30)
        assert bool(result['candidate_accepted'][0])==expected
    result=fuse(base,single,sowner,suv,np.full((1,3),70,np.uint8),np.full((1,3),100,np.uint8),target,depth,np.full((4,3),115,np.uint8),1,k,e,30)
    assert not result['candidate_accepted'][0]
    red=np.array([[240,10,10]],np.uint8);blue=np.tile(np.array([10,10,240],np.uint8),(4,1))
    result=fuse(base,single,sowner,suv,red,red,target,depth,blue,1,k,e,30)
    assert result['metrics']['accepted_old_points']==0 and np.array_equal(result['xyz'][0],single[0])
    return {'similar_rgb_known_depth_mean':True,'mismatched_color_kept':True,'threshold_30_31_boundary':True,
            'mutually_different_candidates_not_jointly_fused':True,'old_group_color_bridge_rejected':True,'nonprojected_xyz_unchanged':True}


def rgb_groups(labels,raw_rgb,n):
    low=np.full((n,3),255,np.uint8);high=np.zeros((n,3),np.uint8)
    np.minimum.at(low,labels,raw_rgb);np.maximum.at(high,labels,raw_rgb)
    counts=np.bincount(labels,minlength=n);order=np.argsort(labels,kind='stable');offsets=np.r_[0,np.cumsum(counts)]
    median=np.empty((n,3),np.float32)
    for count in np.unique(counts):
        groups=np.flatnonzero(counts==count);ids=order[offsets[groups,None]+np.arange(int(count))[None,:]]
        median[groups]=np.median(raw_rgb[ids],axis=1)/255.
    return low,high,median,counts,order,offsets


def write_ply(path,xyz,color,owner,counts,bits):
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('owner','<i2'),('n_observed','<u4'),('source_mask','u1')]);a=np.empty(len(xyz),dtype)
    for i,key in enumerate(['x','y','z']):a[key]=xyz[:,i]
    for i,key in enumerate(['red','green','blue']):a[key]=color[:,i]
    a['owner'],a['n_observed'],a['source_mask']=owner,counts,bits
    head=(f'ply\nformat binary_little_endian 1.0\ncomment E0c original-RGB gated fusion; palette colors\nelement vertex {len(a)}\n'
          'property double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n'
          'property short owner\nproperty uint n_observed\nproperty uchar source_mask\nend_header\n')
    with path.open('xb') as stream:stream.write(head.encode());a.tofile(stream)
    with path.open('rb') as stream:
        while stream.readline()!=b'end_header\n':pass
        assert np.array_equal(np.fromfile(stream,dtype),a)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);args=parser.parse_args()
    src=Path('experiments/pointmap_refinement/E0c');c=json.loads((src/'config.json').read_text());s=Path('results/pointmap_refinement')/args.run_id/'stages/E0c';s.mkdir(parents=True,exist_ok=False)
    for name in ['artifacts/source','artifacts/maps','artifacts/steps','artifacts/projections','artifacts/figures','evaluation','logs']:(s/name).mkdir(parents=True)
    for path in src.iterdir():
        if path.is_file():shutil.copy2(path,s/'artifacts/source'/path.name)
    helpers={'base.py':'experiments/pointmap_refinement/E0b/run.py','projection.py':'experiments/pointmap_refinement/E0a/run.py','geometry.py':'experiments/pointmap_refinement/E1/geometry.py'}
    for name,path in helpers.items():shutil.copy2(path,s/'artifacts/source'/name)
    base=load('base',s/'artifacts/source/base.py');p=load('projection',s/'artifacts/source/projection.py');g=load('geometry',s/'artifacts/source/geometry.py')
    start=time.perf_counter();m={'experiment_code':'E0c','run_id':args.run_id,'status':'running','started_at':p.stamp()};p.json_write(s/'manifest.json',m);p.json_write(s/'config_resolved.json',c|{'run_id':args.run_id})
    def log(value):
        message=json.dumps(value,ensure_ascii=False);print(message,flush=True)
        with (s/'logs/run.log').open('a') as stream:stream.write(message+'\n')
    try:
        e0=Path(c['e0_stage']);b=Path(c['e0b_stage']);inputs=[]
        for parent in [e0,b]:
            pm=json.loads((parent/'manifest.json').read_text());assert pm['status']=='completed'
            for row in pm.get('artifacts',[]):assert p.record(row['path'])==row
            inputs.append(p.record(parent/'manifest.json'))
        def tracked(path):inputs.append(p.record(path));return path
        for path in helpers.values():tracked(Path(path))
        with np.load(tracked(e0/'artifacts/baseline/vggt_omega_raw.npz')) as data:
            depth=data['depth'][0,...,0].astype(float);ks=data['intrinsics'][0].astype(float);es=data['extrinsics'][0].astype(float)
            reference=np.rint(data['images'][0].transpose(0,2,3,1)*255).clip(0,255).astype(np.uint8)
        with np.load(tracked(e0/'artifacts/baseline/observations.npz')) as data:raw_xyz=data['world_xyz_initial'];raw_rgb=data['rgb'];fid=data['frame_id'];raw_uv=data['pixel_uv']
        with np.load(tracked(b/'artifacts/maps/fused_map.npz')) as data:baseline={key:data[key] for key in data.files}
        frames=json.loads(tracked(e0/'artifacts/baseline/frames.json').read_text());n,height,width=depth.shape;frame_size=height*width
        assert np.array_equal(fid,np.repeat(np.arange(3),frame_size)) and c['frame_order']==[0,1,2]
        palette=np.asarray(c['palette_rgb'],np.uint8);control=controls(base)
        def process(threshold,save=False):
            xyz=raw_xyz[fid==0].copy();owner=fid[fid==0].copy();uv=raw_uv[fid==0].copy();lo=raw_rgb[fid==0].copy();hi=lo.copy()
            labels=np.full(len(raw_xyz),-1,np.int64);labels[fid==0]=np.arange(frame_size);steps=[];decisions=[np.zeros((height,width),np.uint8)]
            for j in [1,2]:
                result=fuse(base,xyz,owner,uv,lo,hi,raw_xyz[fid==j],depth[j],raw_rgb[fid==j],j,ks[j],es[j],threshold)
                seen=fid<j;labels[seen]=result['old_to_new'][labels[seen]];labels[fid==j]=result['metrics']['kept_old_points']+np.arange(frame_size)
                xyz,owner,uv,lo,hi=[result[key] for key in ['xyz','owner','uv','rgb_min','rgb_max']];steps.append(result['metrics'])
                decisions.append((result['target_old_point_count']>0).astype(np.uint8)+2*(result['target_rejected_point_count']>0).astype(np.uint8))
                if save:
                    payload={key:result[key] for key in ['old_to_new','old_removed','candidate_old_id','candidate_target_flat','candidate_color_score','candidate_accepted','candidate_rejection_reason','target_old_point_count','target_rejected_point_count','target_mean_z']}
                    payload.update(xyz=xyz,owner_frame_id=owner,owner_pixel_uv=uv,rgb_min=lo,rgb_max=hi,source_to_current=labels)
                    np.savez_compressed(s/f'artifacts/steps/after_frame_{j:02d}.npz',**payload);log(result['metrics'])
            return {'xyz':xyz,'owner_frame_id':owner,'owner_pixel_uv':uv,'rgb_min':lo,'rgb_max':hi,'source_to_fused':labels,'steps':steps,'decision_masks':decisions}
        replay=process(c['baseline_replay_threshold'])
        for key in ['xyz','owner_frame_id','owner_pixel_uv','source_to_fused']:assert np.array_equal(replay[key],baseline[key]),key
        control['threshold_255_replays_E0b_xyz_owner_uv_and_mapping_exactly']=True
        current=process(c['color_threshold_per_channel'],True);xyz=current['xyz'];labels=current['source_to_fused'];owner=current['owner_frame_id'];uv=current['owner_pixel_uv']
        low,high,median,counts,indices,offsets=rgb_groups(labels,raw_rgb,len(xyz))
        assert np.array_equal(low,current['rgb_min']) and np.array_equal(high,current['rgb_max'])
        assert np.max(high.astype(np.int16)-low.astype(np.int16))<=c['color_threshold_per_channel']
        groups,bits,distinct,mix=base.membership(labels,fid,len(xyz),palette);assert np.array_equal(groups,counts)
        payload={'xyz':xyz,'owner_frame_id':owner,'owner_pixel_uv':uv,'n_observed':counts,'source_frame_mask':bits,'source_frame_count':distinct,
                 'source_to_fused':labels,'obs_offsets':offsets,'obs_indices':indices,'owner_colors_rgb':palette[owner],'source_mix_rgb':mix,
                 'rgb_min':low,'rgb_max':high,'rgb_fixed_median':median}
        np.savez_compressed(s/'artifacts/maps/fused_map.npz',**payload)
        with np.load(s/'artifacts/maps/fused_map.npz') as saved:
            for key in payload:assert np.array_equal(saved[key],payload[key])
        for mode,color in [('owner',palette[owner]),('source_mix',mix)]:write_ply(s/f'artifacts/maps/fused_{mode}.ply',xyz,color,owner,counts,bits)
        blo,bhi,bmedian,bcounts,_,_=rgb_groups(baseline['source_to_fused'],raw_rgb,len(baseline['xyz']))
        bbits=baseline['source_frame_mask'];bmembers=((bbits[:,None]>>np.arange(3))&1).astype(bool)
        bmix=np.rint(bmembers.astype(float)@palette/bmembers.sum(1)[:,None]).astype(np.uint8)
        models={'E0':(raw_xyz,raw_rgb.astype(float)/255.,palette[fid]),'E0b':(baseline['xyz'],bmedian,bmix),'E0c':(xyz,median,mix)}
        view_rows=[];source_cells=[];rgb_cells=[];decision_colors=np.array([[0,0,0],[0,220,0],[230,0,0],[230,200,0]],np.uint8)
        for camera in range(3):
            source_images={};median_images={}
            for label,(positions,colors,source_colors) in models.items():
                z,win,_=p.front(positions,np.arange(len(positions)),ks[camera],es[camera],height,width);hit=win>=0
                source_image=np.zeros((height,width,3),np.uint8);photo=source_image.copy()
                source_image[hit]=source_colors[win[hit]];photo[hit]=np.rint(colors[win[hit]]*255).clip(0,255).astype(np.uint8)
                source_images[label]=source_image;median_images[label]=photo
                p.image_write(s/f'artifacts/projections/{label}_camera_{camera}_source.png',source_image)
                if label!='E0':p.image_write(s/f'artifacts/projections/{label}_camera_{camera}_median_rgb.png',photo)
                view_rows.append({'method':label,'camera':camera,'covered_pixels':int(hit.sum()),'total_pixels':frame_size,'coverage':float(hit.mean())})
            source_cells.append([reference[camera],source_images['E0b'],source_images['E0c'],decision_colors[current['decision_masks'][camera]]])
            rgb_cells.append([reference[camera],median_images['E0b'],median_images['E0c']])
        p.panel(s/'artifacts/figures/source_comparison.png',source_cells,['Reference RGB','E0b source mix','E0c source mix','E0c accepted / rejected'],frames,height,width)
        p.panel(s/'artifacts/figures/median_rgb_comparison.png',rgb_cells,['Reference RGB','E0b median point RGB','E0c median point RGB'],frames,height,width)
        # Evaluation only: reuse an existing scale; never choose the color threshold using GT.
        scale_record=json.loads(tracked(Path(c['scale_reference_stage'])/'evaluation/gt_depth.json').read_text());scale=scale_record['scale_m_per_model_unit']
        gt_stage=Path(c['gt_stage']);gm=json.loads(tracked(gt_stage/'manifest.json').read_text());gt=[]
        for camera in range(3):
            path=gt_stage/f'artifacts/gt/aligned_{camera}.npz';assert p.record(path)==next(row for row in gm['artifacts'] if row['path']==str(path))
            with np.load(tracked(path)) as data:gt.append(data['depth_m'].astype(float))
        gt=np.stack(gt);native={label:np.stack([g.front_map(data[0],ks[i],es[i],height,width)[0] for i in range(3)]) for label,data in models.items()}
        fixed=(gt>0)&np.isfinite(native['E0']);common=fixed.copy()
        for z in native.values():common&=np.isfinite(z)&(z>0)
        gt_rows=[]
        for label,z in native.items():
            mask=fixed&np.isfinite(z)&(z>0);err=z[common]*scale-gt[common]
            gt_rows.append({'method':label,'common_pixels':int(common.sum()),'rmse_m':float(np.sqrt(np.mean(err**2))),'absrel':float((np.abs(err)/gt[common]).mean()),
                            'fixed_pixels':int(fixed.sum()),'covered_fixed_pixels':int(mask.sum()),'coverage_of_fixed':float(mask.sum()/fixed.sum())})
            for camera in range(3):np.savez_compressed(s/f'artifacts/projections/{label}_camera_{camera}_gt.npz',depth_model=z[camera],gt_m=gt[camera],fixed_mask=fixed[camera],common_mask=common[camera])
        p.json_write(s/'evaluation/gt_depth.json',{'scale_m_per_model_unit':scale,'scale_refit_for_E0c':False,'summary':gt_rows,
                     'limitations':'same-input-view depth only; scale from prior E0b; intersection support; no independent view/full 3D/wall ROI claim'})
        owner_obs=owner.astype(np.int64)*frame_size+uv[:,1]*width+uv[:,0];movement=np.linalg.norm(xyz-raw_xyz[owner_obs],axis=1)
        spread=(high.astype(np.int16)-low.astype(np.int16)).max(1);bspread=(bhi.astype(np.int16)-blo.astype(np.int16)).max(1)
        metrics={'input_observations':len(raw_xyz),'baseline_E0b_points':len(baseline['xyz']),'final_points':len(xyz),'point_reduction_fraction':1-len(xyz)/len(raw_xyz),
                 'steps':current['steps'],'source_frame_histogram':{str(i):int((distinct==i).sum()) for i in [1,2,3]},
                 'color_threshold':c['color_threshold_per_channel'],'max_original_group_channel_range':int(spread.max()),
                 'groups_over_color_threshold':int((spread>c['color_threshold_per_channel']).sum()),'baseline_groups_over_color_threshold':int((bspread>c['color_threshold_per_channel']).sum()),
                 'owner_displacement_model_units':{'mean':float(movement.mean()),'max':float(movement.max())},'camera_projections':view_rows,'cpu_seconds':time.perf_counter()-start}
        p.json_write(s/'evaluation/metrics.json',metrics)
        p.json_write(s/'evaluation/verification.json',{'status':'passed','controlled_checks':control,'RGB_bounds_recomputed_from_original_CSR':True,
                     'all_groups_obey_color_gate':True,'all_original_observations_retained_in_one_CSR_group':True,'color_rejected_and_nonprojected_xyz_unchanged':True,
                     'accepted_depth_mean_and_target_pixel':True,'PLY_NPZ_PNG_reload':True,'parents_unchanged':True})
        for row in inputs:assert p.record(row['path'])==row
        p.json_write(s/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,'platform':platform.platform(),
                     'execution_context':'host CPU; GPU unused','project_commit_before_run':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                     'source_files':[p.record(path) for path in sorted((s/'artifacts/source').glob('*')) if path.is_file()]})
        log({'metrics':metrics,'gt_summary':gt_rows});m.update(status='completed',ended_at=p.stamp(),completion_criteria_met=True,inputs=inputs)
        m['artifacts']=[p.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts]
        p.json_write(s/'manifest.json',m)
    except Exception:
        log({'error':traceback.format_exc()});m.update(status='failed',error=traceback.format_exc(),ended_at=p.stamp());p.json_write(s/'manifest.json',m);raise


if __name__=='__main__':main()
