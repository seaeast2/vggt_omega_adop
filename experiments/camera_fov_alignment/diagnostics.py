"""Geometry metrics, source palette images, PLY, fixed-coverage checks."""
import itertools
import cv2
import numpy as np
import common as c


def weighted_stats(values,weights):
    if not len(values):return {'count':0}
    order=np.argsort(values,kind='stable');x=np.asarray(values)[order];w=np.asarray(weights)[order]
    cumulative=(np.cumsum(w)-w/2)/w.sum()
    return {'count':len(x),'mean':float(w@x/w.sum()),
        'median':float(np.interp(.5,cumulative,x)),
        'p90':float(np.interp(.9,cumulative,x)),'max':float(x.max())}


def geometry(data,matches,beta):
    k=c.corrected_k(data['k'],np.asarray(beta).reshape(3,2))
    result={}
    for fold in ['fit','validation','all']:
        select=(~matches['validation'] if fold=='fit' else matches['validation']) if fold!='all' else np.ones(len(matches['pair']),bool)
        rows=[];all3=[];allz=[];allw=[];loss=[]
        for i,j in itertools.combinations(range(3),2):
            mask=select&(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j)
            if not mask.any():continue
            pi=c.unproject(matches['uv_i'][mask],matches['di'][mask],k[i],data['e'][i])
            pj=c.unproject(matches['uv_j'][mask],matches['dj'][mask],k[j],data['e'][j])
            r=pi-pj;distances=[];zs=[];huber=[]
            for camera,depth in [(i,matches['di'][mask]),(j,matches['dj'][mask])]:
                camera_r=r@data['e'][camera,:,:3].T/depth[:,None]
                distances.append(np.linalg.norm(camera_r,axis=1));zs.append(np.abs(camera_r[:,2]))
                camera_r[:,2]*=2;huber.append(c.huber(np.linalg.norm(camera_r,axis=1)))
            d=np.concatenate(distances);z=np.concatenate(zs)
            rows.append({'pair':[i,j],'observations':int(mask.sum()),'relative_3d':c.stats(d),
                'relative_z':c.stats(z),'z_inlier_1pct':float(np.mean(z<.01)),
                'z_inlier_3pct':float(np.mean(z<.03)),'huber_data_loss':float(np.mean(huber))})
            all3.append(d);allz.append(z);allw.append(np.full(len(d),1/(3*len(d))))
            loss.append(float(np.mean(huber)))
        if all3:
            all3=np.concatenate(all3);allz=np.concatenate(allz);allw=np.concatenate(allw)
            result[fold]={'relative_3d':weighted_stats(all3,allw),
                'relative_z':weighted_stats(allz,allw),
                'z_inlier_1pct':float(allw@(allz<.01)/allw.sum()),
                'z_inlier_3pct':float(allw@(allz<.03)/allw.sum()),
                'huber_data_loss':float(np.mean(loss)),'pairs':rows,
                'aggregation':'equal weight per camera pair and each direction'}
        else:result[fold]={'relative_3d':{'count':0},'relative_z':{'count':0},'pairs':[]}
    return result


def parameter_table(data,beta):
    k=c.corrected_k(data['k'],np.asarray(beta).reshape(3,2));h,w=data['depth'].shape[1:]
    return [{'camera':i,'beta_xy':np.asarray(beta).reshape(3,2)[i].tolist(),
        'fx_fy_before':[data['k'][i,0,0],data['k'][i,1,1]],
        'fx_fy_after':[k[i,0,0],k[i,1,1]],
        'fov_wh_before_degree':np.degrees(2*np.arctan(np.array([w,h])/(2*np.array([data['k'][i,0,0],data['k'][i,1,1]])))).tolist(),
        'fov_wh_after_degree':np.degrees(2*np.arctan(np.array([w,h])/(2*np.array([k[i,0,0],k[i,1,1]])))).tolist(),
        'intrinsics_after':k[i].tolist(),'extrinsics_unchanged':data['e'][i].tolist(),
        'center_unchanged':data['centers'][i].tolist()} for i in range(3)]


def overlap_reference(data):
    xyz=c.points(data,np.ones(6));h,w=data['depth'].shape[1:];size=h*w
    return {(i,j):c.project(xyz[i*size:(i+1)*size],data['k'][j],data['e'][j],h,w)[2]
            for i in range(3) for j in range(3) if i!=j}


def coverage(data,beta,reference):
    xyz=c.points(data,beta);k=c.corrected_k(data['k'],np.asarray(beta).reshape(3,2));h,w=data['depth'].shape[1:];size=h*w
    rows=[]
    for (i,j),mask in reference.items():
        valid=c.project(xyz[i*size:(i+1)*size],k[j],data['e'][j],h,w)[2]
        denominator=int(mask.sum());retained=int((valid&mask).sum())
        loss=1-retained/denominator if denominator else 1.
        rows.append({'source':i,'target':j,'initial_valid_count':denominator,
            'retained_initial_count':retained,'loss_fraction':loss,
            'passed':denominator>0 and loss<=.005+1e-12})
    return {'pairs':rows,'passed':all(r['passed'] for r in rows),
        'maximum_loss_fraction':max(r['loss_fraction'] for r in rows)}


def nearest_secondary(data,xyz):
    size=np.prod(data['depth'].shape[1:]);size=int(size)
    ids=np.linspace(0,size-1,min(512,size),dtype=np.int64)
    bf=cv2.BFMatcher(cv2.NORM_L2);out=[]
    median=float(np.median(data['depth']))
    for i,j in itertools.permutations(range(3),2):
        query=np.ascontiguousarray(xyz[i*size+ids],np.float32)
        target=np.ascontiguousarray(xyz[j*size:(j+1)*size],np.float32)
        matches=bf.match(query,target)
        distances=np.array([m.distance for m in matches])/median
        out.append({'source':i,'target':j,'fixed_query_points':len(ids),
            'full_target_points':size,'relative_distance':c.stats(distances)})
    return {'pairs':out,'normalizer_fixed_initial_median_depth':median,
        'backend':'exact float32 BF L2; deterministic 512 queries per source',
        'physical_correspondences_verified':False}


def render(data,xyz,k,out,owner=None,raw_ids=None):
    out.mkdir(parents=True,exist_ok=True)
    n,h,w=data['depth'].shape
    if owner is None:owner=data['fid']
    if raw_ids is None:raw_ids=np.arange(len(xyz))
    colors=data['raw_rgb'][raw_ids];rows=[];metrics=[];source_rows=[]
    for camera in range(3):
        z,win,valid=c.front(xyz,k[camera],data['e'][camera],h,w)
        hit=win>=0;photo=np.zeros((h,w,3),np.uint8);palette=photo.copy()
        photo[hit]=colors[win[hit]];palette[hit]=c.PALETTE[owner[win[hit]]]
        source_buffer=np.full((h,w),-1,np.int16);source_buffer[hit]=owner[win[hit]]
        c.image_write(out/f'camera_{camera}_rgb.png',photo)
        c.image_write(out/f'camera_{camera}_source.png',palette)
        np.savez_compressed(out/f'camera_{camera}_front.npz',depth=z,winner=win,
            source=source_buffer,empty=~hit,in_frustum=valid)
        rows.append([data['rgb'][camera],photo,palette]);source_cells=[]
        for source in range(3):
            select=np.flatnonzero(owner==source)
            sz,sw,sv=c.front(xyz[select],k[camera],data['e'][camera],h,w)
            display=np.zeros((h,w,3),np.uint8);display[sw>=0]=c.PALETTE[source]
            c.image_write(out/f'camera_{camera}_only_source_{source}.png',display)
            source_cells.append(display)
        other=owner!=camera
        oz,ow,ov=c.front(xyz[other],k[camera],data['e'][camera],h,w)
        other_ids=np.flatnonzero(other)
        other_palette=np.zeros((h,w,3),np.uint8)
        other_palette[ow>=0]=c.PALETTE[owner[other_ids[ow[ow>=0]]]]
        c.image_write(out/f'camera_{camera}_other_source.png',other_palette)
        source_rows.append([palette,other_palette,*source_cells])
        metrics.append({'camera':camera,'covered_pixels':int(hit.sum()),'coverage':float(hit.mean()),
            'other_source_covered_pixels':int((ow>=0).sum())})
    return rows,source_rows,metrics


def dense_geometry(data,xyz,k,out,reference_xyz=None,reference_k=None):
    out.mkdir(parents=True,exist_ok=True)
    _,h,w=data['depth'].shape;size=h*w
    if reference_xyz is None:reference_xyz=c.points(data,np.ones(6))
    if reference_k is None:reference_k=data['k']
    pair_rows=[];roi_rows=[]
    for j in range(3):
        layers=[];base_layers=[]
        for i in range(3):
            zm,win,_=c.front(xyz[i*size:(i+1)*size],k[j],data['e'][j],h,w)
            base,_,_=c.front(reference_xyz[i*size:(i+1)*size],reference_k[j],data['e'][j],h,w)
            layers.append(zm);base_layers.append(base)
            if i==j:continue
            fixed=np.isfinite(base)&np.isfinite(data['depth'][j])
            valid=fixed&np.isfinite(zm)
            difference=(zm[valid]-data['depth'][j][valid])/data['depth'][j][valid]
            pair_rows.append({'source':i,'target':j,'fixed_initial_pixels':int(fixed.sum()),
                'retained_pixels':int(valid.sum()),'retention':float(valid.sum()/max(1,fixed.sum())),
                'absolute_relative_z':c.stats(np.abs(difference)),
                'inlier_1pct':float(np.mean(np.abs(difference)<.01)) if len(difference) else None,
                'inlier_3pct':float(np.mean(np.abs(difference)<.03)) if len(difference) else None})
        layers=np.stack(layers);base_layers=np.stack(base_layers)
        # Spatial ROI is frozen before fitting. It is not semantically verified as a wall.
        roi=np.zeros((h,w),bool);roi[h//4:3*h//4,w//4:3*w//4]=True
        fixed=roi&(np.isfinite(base_layers).sum(0)>=2)
        valid=fixed&(np.isfinite(layers).sum(0)>=2)
        low=np.where(np.isfinite(layers),layers,np.inf).min(0)
        high=np.where(np.isfinite(layers),layers,-np.inf).max(0)
        spread=(high[valid]-low[valid])/data['depth'][j][valid]
        roi_rows.append({'camera':j,'roi':'fixed central half width/height; wall semantics unverified',
            'fixed_pixels':int(fixed.sum()),'valid_pixels':int(valid.sum()),
            'relative_layer_spread':c.stats(spread)})
        np.savez_compressed(out/f'layers_camera_{j}.npz',source_front_depths=layers,
            initial_source_front_depths=base_layers,fixed_spatial_roi=roi,
            fixed_evaluation_mask=fixed,evaluation_valid=valid)
    return {'pairs':pair_rows,'spatial_roi_layers':roi_rows,
        'wall_specific_claim_allowed':False,'occlusion_and_different_surfaces_included':True}


def export_map(data,beta,out,per_frame=True):
    out.mkdir(parents=True,exist_ok=True)
    xyz=c.points(data,beta);owner=data['fid'];k=c.corrected_k(data['k'],np.asarray(beta).reshape(3,2))
    np.savez_compressed(out/'pointmap.npz',xyz=xyz,frame_id=owner,pixel_uv=data['uv'],
        rgb=data['raw_rgb'],intrinsics=k,extrinsics=data['e'],beta=np.asarray(beta))
    c.ply_write(out/'all_source.ply',xyz,c.PALETTE[owner],owner)
    c.ply_write(out/'all_rgb.ply',xyz,data['raw_rgb'],owner)
    if per_frame:
        for i in range(3):
            mask=owner==i
            c.ply_write(out/f'frame_{i}_source.ply',xyz[mask],c.PALETTE[owner[mask]],owner[mask])
    return xyz,k
