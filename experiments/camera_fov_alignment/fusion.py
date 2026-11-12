"""E0c-compatible representative averaging plus full-member RGB/Z range gates."""
import time
import numpy as np
import common as c


def step(xyz,owner,uv,rgb_min,rgb_max,labels_seen,raw_xyz_seen,target_xyz,
         target_depth,target_rgb,target_id,k,e,color_threshold=30,depth_threshold=.03):
    h,w=target_depth.shape;size=h*w;target=target_rgb.reshape(-1,3).astype(np.int16)
    projected,z,inside=c.project(xyz,k,e,h,w)
    old_ids=np.flatnonzero(inside)
    xy=np.rint(projected[old_ids]).astype(np.int64);flat=xy[:,1]*w+xy[:,0]
    good=np.isfinite(target_depth.ravel()[flat])&(target_depth.ravel()[flat]>0)
    old_ids,flat=old_ids[good],flat[good]
    candidate_z=z[old_ids]
    raw_z=raw_xyz_seen@e[2,:3]+e[2,3]
    low_z=np.full(len(xyz),np.inf);high_z=np.full(len(xyz),-np.inf)
    np.minimum.at(low_z,labels_seen,raw_z);np.maximum.at(high_z,labels_seen,raw_z)
    assert np.isfinite(low_z).all() and np.isfinite(high_z).all()
    low_z=np.minimum(low_z,z);high_z=np.maximum(high_z,z)
    old_min=rgb_min[old_ids].astype(np.int16);old_max=rgb_max[old_ids].astype(np.int16)
    score=np.maximum(np.abs(old_min-target[flat]),np.abs(old_max-target[flat])).max(1)
    order=np.lexsort((old_ids,score,flat));sorted_flat=flat[order]
    accepted=np.zeros(len(old_ids),bool);reason=np.zeros(len(old_ids),np.uint8)
    new_min=target.copy();new_max=target.copy()
    new_zmin=target_depth.ravel().copy();new_zmax=target_depth.ravel().copy()
    color_range_at_test=np.zeros(len(old_ids),np.int16)
    depth_range_at_test=np.zeros(len(old_ids),float)
    if len(order):
        starts=np.flatnonzero(np.r_[True,sorted_flat[1:]!=sorted_flat[:-1]])
        ranks=np.arange(len(order))-np.repeat(starts,np.diff(np.r_[starts,len(order)]))
        for rank in range(int(ranks.max())+1):
            candidates=order[ranks==rank];pixels=flat[candidates];old=old_ids[candidates]
            lo=np.minimum(new_min[pixels],old_min[candidates]);hi=np.maximum(new_max[pixels],old_max[candidates])
            zlo=np.minimum(new_zmin[pixels],low_z[old]);zhi=np.maximum(new_zmax[pixels],high_z[old])
            color_range=(hi-lo).max(1);depth_range=(zhi-zlo)/target_depth.ravel()[pixels]
            color_good=color_range<=color_threshold
            depth_good=np.ones(len(old),bool) if depth_threshold is None else ((zlo>0)&
                np.isfinite(depth_range)&(depth_range<=depth_threshold+1e-8))
            passed=color_good&depth_good;chosen=candidates[passed]
            accepted[chosen]=True
            reason[candidates]=(~color_good).astype(np.uint8)+2*(~depth_good).astype(np.uint8)
            color_range_at_test[candidates]=color_range;depth_range_at_test[candidates]=depth_range
            new_min[flat[chosen]]=lo[passed];new_max[flat[chosen]]=hi[passed]
            new_zmin[flat[chosen]]=zlo[passed];new_zmax[flat[chosen]]=zhi[passed]
    accepted_ids=old_ids[accepted];accepted_flat=flat[accepted]
    count=np.bincount(accepted_flat,minlength=size)
    zsum=np.bincount(accepted_flat,weights=candidate_z[accepted],minlength=size)
    mean_z=(target_depth.ravel()+zsum)/(1+count)
    grid=np.indices((h,w))[::-1].reshape(2,-1).T.astype(np.int32)
    new_xyz=target_xyz.copy();touched=np.flatnonzero(count)
    new_xyz[touched]=c.unproject(grid[touched],mean_z[touched],k,e)
    keep=np.ones(len(xyz),bool);keep[accepted_ids]=False;nkeep=int(keep.sum())
    mapping=np.empty(len(xyz),np.int64);mapping[keep]=np.arange(nkeep)
    mapping[accepted_ids]=nkeep+accepted_flat
    result={'xyz':np.vstack([xyz[keep],new_xyz]),
        'owner':np.r_[owner[keep],np.full(size,target_id,np.int16)],
        'uv':np.vstack([uv[keep],grid]),'rgb_min':np.vstack([rgb_min[keep],new_min.astype(np.uint8)]),
        'rgb_max':np.vstack([rgb_max[keep],new_max.astype(np.uint8)]),
        'old_to_new':mapping,'old_removed':~keep,'candidate_old_id':old_ids,
        'candidate_target_flat':flat,'candidate_accepted':accepted,
        'candidate_rejection_reason':reason,'candidate_color_range_at_test':color_range_at_test,
        'candidate_depth_range_at_test':depth_range_at_test,
        'target_accepted_count':count.reshape(h,w),'target_mean_z':mean_z.reshape(h,w),
        'target_union_depth_min':new_zmin.reshape(h,w),'target_union_depth_max':new_zmax.reshape(h,w)}
    assert np.array_equal(result['xyz'][:nkeep],xyz[keep])
    assert np.array_equal(new_xyz[count==0],target_xyz[count==0])
    assert not np.any(result['old_removed'][old_ids[~accepted]])
    assert np.all(color_range_at_test[accepted]<=color_threshold)
    if depth_threshold is not None:
        assert np.all(depth_range_at_test[accepted]<=depth_threshold+1e-8)
    cam=new_xyz[touched]@e[:,:3].T+e[:,3]
    projected_new=(cam@k.T)[:,:2]/cam[:,2,None]
    assert np.max(np.abs(projected_new-grid[touched]),initial=0)<1e-7
    assert np.max(np.abs(cam[:,2]-mean_z[touched]),initial=0)<1e-9
    # Independent scatter-add reproduces the actual representative average.
    independent_sum=np.zeros(size);np.add.at(independent_sum,accepted_flat,candidate_z[accepted])
    assert np.allclose(mean_z,(target_depth.ravel()+independent_sum)/(1+count),atol=1e-12,rtol=1e-12)
    result['metrics']={'target_camera':target_id,'old_representatives':len(xyz),
        'projected_candidates':len(old_ids),'accepted_old_points':int(accepted.sum()),
        'color_rejected_only':int((reason==1).sum()),'depth_rejected_only':int((reason==2).sum()),
        'both_rejected':int((reason==3).sum()),'kept_old_points':nkeep,
        'new_target_points':size,'output_points':len(result['xyz']),
        'touched_target_pixels':len(touched),'maximum_group_depth_range_at_acceptance':
            float(np.max(depth_range_at_test[accepted],initial=0)),
        'maximum_color_range_at_acceptance':int(np.max(color_range_at_test[accepted],initial=0))}
    return result


def verify_groups(xyz,owner,uv,labels,raw_xyz,raw_rgb,e,depth,target_id,threshold):
    size=len(xyz);counts=np.bincount(labels,minlength=size)
    assert (counts>0).all() and counts.sum()==len(labels)
    order=np.argsort(labels,kind='stable');offsets=np.r_[0,np.cumsum(counts)]
    assert np.array_equal(np.sort(order),np.arange(len(labels)))
    low=np.minimum.reduceat(raw_rgb[order].astype(np.int16),offsets[:-1],axis=0)
    high=np.maximum.reduceat(raw_rgb[order].astype(np.int16),offsets[:-1],axis=0)
    assert np.all(high-low<=30)
    raw_z=raw_xyz@e[2,:3]+e[2,3]
    zlo=np.minimum.reduceat(raw_z[order],offsets[:-1])
    zhi=np.maximum.reduceat(raw_z[order],offsets[:-1])
    new=np.flatnonzero(owner==target_id)
    anchor_depth=depth[uv[new,1],uv[new,0]]
    if threshold is not None:
        assert (zlo[new]>0).all()
        assert np.all((zhi[new]-zlo[new])/anchor_depth<=threshold+1e-8)
    return counts,order,offsets,low.astype(np.uint8),high.astype(np.uint8)


def process(data,raw_xyz,k,output=None,stage=None,depth_threshold=.03):
    started=time.perf_counter();n,h,w=data['depth'].shape;size=h*w
    xyz=raw_xyz[:size].copy();owner=data['fid'][:size].copy();uv=data['uv'][:size].copy()
    lo=data['raw_rgb'][:size].copy();hi=lo.copy()
    labels=np.full(len(raw_xyz),-1,np.int64);labels[:size]=np.arange(size);steps=[]
    if output is not None:output.mkdir(parents=True,exist_ok=True)
    for j in [1,2]:
        result=step(xyz,owner,uv,lo,hi,labels[:j*size],raw_xyz[:j*size],
            raw_xyz[j*size:(j+1)*size],data['depth'][j],data['rgb'][j],j,k[j],data['e'][j],
            depth_threshold=depth_threshold)
        labels[:j*size]=result['old_to_new'][labels[:j*size]]
        labels[j*size:(j+1)*size]=result['metrics']['kept_old_points']+np.arange(size)
        xyz,owner,uv,lo,hi=[result[key] for key in ['xyz','owner','uv','rgb_min','rgb_max']]
        counts,indices,offsets,check_lo,check_hi=verify_groups(xyz,owner,uv,labels[:(j+1)*size],
            raw_xyz[:(j+1)*size],data['raw_rgb'][:(j+1)*size],data['e'][j],data['depth'][j],j,depth_threshold)
        assert np.array_equal(lo,check_lo) and np.array_equal(hi,check_hi)
        steps.append(result['metrics'])
        if output is not None:
            payload={key:value for key,value in result.items() if key!='metrics'}
            payload['source_to_current']=labels.copy()
            np.savez_compressed(output/f'after_frame_{j:02d}.npz',**payload)
        if stage:stage.log('fusion_step',depth_threshold=depth_threshold,**result['metrics'])
    bits=np.zeros(len(xyz),np.uint8)
    np.bitwise_or.at(bits,labels,(1<<data['fid']).astype(np.uint8))
    raw_ids=owner.astype(np.int64)*size+uv[:,1]*w+uv[:,0]
    result={'xyz':xyz,'owner':owner,'uv':uv,'rgb_min':lo,'rgb_max':hi,
        'source_to_fused':labels,'n_observed':counts,'obs_indices':indices,'obs_offsets':offsets,
        'source_frame_mask':bits,'owner_observation_id':raw_ids,'owner_rgb':data['raw_rgb'][raw_ids]}
    metrics={'steps':steps,'raw_observations':len(raw_xyz),'representative_points':len(xyz),
        'reduction_fraction':1-len(xyz)/len(raw_xyz),'observation_count':c.stats(counts),
        'multi_frame_group_fraction':float(np.mean((bits&(bits-1))!=0)),
        'seconds':time.perf_counter()-started,'geometry_array_bytes':xyz.nbytes,
        'all_map_array_bytes':sum(x.nbytes for x in result.values()),
        'raw_observation_arrays_bytes':raw_xyz.nbytes+data['raw_rgb'].nbytes+data['fid'].nbytes+data['uv'].nbytes,
        'full_member_color_range_verified':True,'stagewise_full_member_depth_range_verified':depth_threshold is not None,
        'all_original_observations_partitioned_once':True,'raw_colors_not_averaged':True}
    return result,metrics
