"""Build raw/color-gated drone baselines and frozen refinement inputs, CPU only."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import traceback

import cv2
import numpy as np


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage
    c=json.loads((s/'config_resolved.json').read_text());m=json.loads((s/'manifest.json').read_text());assert m['status']=='running' and m['phase']=='inputs_ready'
    source=s/'artifacts/source';projection=module('projection',source/'projection.py');base=module('base',source/'fusion_base.py');fusion=module('fusion',source/'fusion_color.py')
    geom=module('geom',source/'geometry.py');prep=module('prep',source/'shared_preparation.py');export=module('export',source/'export.py')
    try:
        metrics=json.loads((s/'artifacts/inference/metrics.json').read_text());assert metrics['status']=='completed' and metrics['count']==3
        raw=s/'artifacts/inference/vggt_omega_raw.npz';shutil.copy2(raw,s/'artifacts/baseline/vggt_omega_raw.npz')
        with np.load(raw) as d:
            depth=d['depth'][0,...,0].astype(float);confidence=d['depth_conf'][0];ks=d['intrinsics'][0].astype(float);es=d['extrinsics'][0].astype(float);images=d['images'][0].transpose(0,2,3,1)
        n,h,w=depth.shape;size=h*w;assert n==3 and np.isfinite(depth).all() and (depth>0).all()
        grid=np.indices((h,w))[::-1].reshape(2,-1).T.astype(np.int32);uv=np.tile(grid,(n,1));fid=np.repeat(np.arange(n,dtype=np.int16),size)
        xyz0=np.vstack([base.unproject(np.arange(size),depth[i].ravel(),ks[i],es[i],w) for i in range(n)])
        rgb=np.rint(images.reshape(-1,3)*255).clip(0,255).astype(np.uint8);palette=np.asarray(c['palette_rgb'],np.uint8)
        np.savez_compressed(s/'artifacts/baseline/observations.npz',world_xyz_initial=xyz0,rgb=rgb,frame_id=fid,pixel_uv=uv,depth_initial=depth.ravel())
        frames=json.loads((s/'artifacts/data/frames.json').read_text())['frames'];projection.json_write(s/'artifacts/baseline/frames.json',frames)
        for i in range(3):
            camera=xyz0[fid==i]@es[i,:,:3].T+es[i,:,3];q=(camera@ks[i].T)[:,:2]/camera[:,2,None]
            assert np.max(np.abs(q-grid))<1e-7 and np.max(np.abs(camera[:,2]-depth[i].ravel()))<1e-9
        controls=fusion.controls(base)
        xyz=xyz0[:size].copy();owner=fid[:size].copy();pix=uv[:size].copy();low=rgb[:size].copy();high=low.copy();labels=np.full(len(xyz0),-1,np.int64);labels[:size]=np.arange(size);steps=[]
        for i in [1,2]:
            r=fusion.fuse(base,xyz,owner,pix,low,high,xyz0[fid==i],depth[i],rgb[fid==i],i,ks[i],es[i],c['color_threshold_per_channel'])
            seen=fid<i;labels[seen]=r['old_to_new'][labels[seen]];labels[fid==i]=r['metrics']['kept_old_points']+np.arange(size)
            xyz,owner,pix,low,high=[r[k] for k in ['xyz','owner','uv','rgb_min','rgb_max']];steps.append(r['metrics'])
            np.savez_compressed(s/f'artifacts/maps/after_frame_{i:02d}.npz',xyz=xyz,source_to_current=labels,old_to_new=r['old_to_new'],old_removed=r['old_removed'],candidate_accepted=r['candidate_accepted'],candidate_rejection_reason=r['candidate_rejection_reason'])
        lo,hi,median,counts,indices,offsets=fusion.rgb_groups(labels,rgb,len(xyz));assert np.array_equal(lo,low) and np.array_equal(hi,high)
        assert (hi.astype(int)-lo.astype(int)).max()<=30
        groups,bits,distinct,mix=base.membership(labels,fid,len(xyz),palette);assert np.array_equal(groups,counts)
        fused={'xyz':xyz,'owner_frame_id':owner,'owner_pixel_uv':pix,'n_observed':counts,'source_frame_mask':bits,'source_frame_count':distinct,
               'source_to_fused':labels,'obs_offsets':offsets,'obs_indices':indices,'owner_colors_rgb':palette[owner],'source_mix_rgb':mix,'rgb_min':lo,'rgb_max':hi,'rgb_fixed_median':median}
        np.savez_compressed(s/'artifacts/maps/fused_map.npz',**fused)
        with np.load(s/'artifacts/maps/fused_map.npz') as saved:
            for key in fused:assert np.array_equal(fused[key],saved[key])
        shared,summary=prep.make_shared(fused,rgb,fid,ks,es,depth,confidence,c['visibility'],geom)
        np.savez_compressed(s/'artifacts/initial/shared_map.npz',**shared)
        rh,rw=h//c['render_downsample_factor'],w//c['render_downsample_factor'];affine=np.array([[rw/w,0,(rw/w-1)/2],[0,rh/h,(rh/h-1)/2],[0,0,1.]])
        targets=np.stack([cv2.resize(x,(rw,rh),interpolation=cv2.INTER_AREA) for x in images]);masks=[]
        for i in range(3):
            front,_,_=projection.front(xyz,np.arange(len(xyz)),affine@ks[i],es[i],rh,rw)
            safe=geom.edge_safe(depth[i],c['visibility']['depth_edge_relative'])&(confidence[i]>=np.percentile(confidence[i],10))
            mask=cv2.resize(safe.astype(np.uint8),(rw,rh),interpolation=cv2.INTER_NEAREST).astype(bool)&np.isfinite(front)
            mask[:3]=False;mask[-3:]=False;mask[:,:3]=False;mask[:,-3:]=False;assert mask.any();masks.append(mask)
        np.savez_compressed(s/'artifacts/initial/cameras_targets.npz',intrinsics=ks,extrinsics=es,targets=targets,targets_native=images)
        np.savez_compressed(s/'artifacts/initial/training_contract.npz',train_masks=np.stack(masks))
        for name,points,color,own,cnt,mask in [('raw_source',xyz0,palette[fid],fid,np.ones(len(xyz0),np.int64),(1<<fid).astype(np.uint8)),
            ('fused_owner',xyz,palette[owner],owner,counts,bits),('fused_source_mix',xyz,mix,owner,counts,bits)]:
            export.ply_write(s/f'artifacts/maps/{name}.ply',points,color,own,cnt,mask,'E0d')
        cells=[];rgb_cells=[];coverage=[]
        for i in range(3):
            views=[];photos=[]
            for name,points,color,point_rgb in [('raw',xyz0,palette[fid],rgb.astype(float)/255),('fused',xyz,mix,median)]:
                z,win,_=projection.front(points,np.arange(len(points)),ks[i],es[i],h,w);hit=win>=0;view=np.zeros((h,w,3),np.uint8);photo=view.copy()
                view[hit]=color[win[hit]];photo[hit]=np.rint(point_rgb[win[hit]]*255).clip(0,255).astype(np.uint8);views.append(view);photos.append(photo)
                coverage.append({'camera':i,'map':name,'native_coverage':float(hit.mean())})
            target=np.rint(images[i]*255).clip(0,255).astype(np.uint8);cells.append([target]+views);rgb_cells.append([target]+photos)
        projection.panel(s/'artifacts/figures/source_comparison.png',cells,['Input RGB','Raw source palette','Color-gated source mix'],frames,h,w)
        projection.panel(s/'artifacts/figures/rgb_comparison.png',rgb_cells,['Input RGB','Raw nearest RGB','Fused median RGB'],frames,h,w)
        translations=np.stack([np.asarray(row['camera_metadata']['T4x4'])[:3,3] for row in frames]);motion=[]
        for i,j in [(0,1),(1,2),(0,2)]:motion.append({'pair':[i,j],'metadata_translation_difference':float(np.linalg.norm(translations[j]-translations[i])),'seconds':float(frames[j]['timestamp'])-float(frames[i]['timestamp'])})
        gt_audit={'matched_lidar_and_pose_metadata_present':True,'validated_depth_GT_available':False,'used_for_fusion_or_active_or_RGB_targets':False,
            'reason':'LiDAR XYZ frame and distortion/rectification convention of interval5 images not independently verified; metadata T4x4 pose direction unconfirmed. Do not fit GT depth scale or claim geometric accuracy.',
            'official_calibration_source_commit':c['calibration_source_commit'],'calibration_mapping':'HKairport01 -> HK_GNSS_calibration; AMtown01 -> AMtown_calibration',
            'author_issue_without_confirmation':'https://github.com/sijieaaa/UAVScenes/issues/18','metadata_motion_proxy':motion}
        projection.json_write(s/'evaluation/gt_reference_audit.json',gt_audit)
        result={'scene':c['scene'],'raw_points':len(xyz0),'fused_points':len(xyz),'point_reduction_fraction':1-len(xyz)/len(xyz0),'native_hw':[h,w],'render_hw':[rh,rw],
            'source_frame_histogram':{str(i):int((distinct==i).sum()) for i in [1,2,3]},'steps':steps,'preparation':summary,'train_pixels':[int(x.sum()) for x in masks],
            'max_RGB_group_range':int((hi.astype(int)-lo.astype(int)).max()),'camera_projections':coverage,'metadata_motion_proxy':motion,'GT_evaluated':False}
        projection.json_write(s/'evaluation/metrics.json',result);projection.json_write(s/'evaluation/verification.json',{'status':'passed','fusion_controls':controls,'all_RGB_groups_within_30':True,'CSR_complete_partition':True,'unprojection_camera_ray':True,'NPZ_PLY_PNG_reload':True,'new_joint_3frame_Omega_inference':True,'GT_not_used':True})
        for row in m['inputs']:assert projection.record(row['path'])==row
        for path in Path('experiments/pointmap_refinement/E0d').iterdir():
            if path.is_file():assert path.read_bytes()==(source/path.name).read_bytes()
        projection.json_write(s/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,'preparation':'host CPU','inference':metrics,'source_files':[projection.record(p) for p in sorted(source.iterdir()) if p.is_file()]})
        (s/'logs/finalize.log').write_text(json.dumps(result,indent=2)+'\n');m.update(status='completed',phase='baseline_ready',ended_at=projection.stamp(),completion_criteria_met=True)
        m['artifacts']=[projection.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts]
        projection.json_write(s/'manifest.json',m);print(json.dumps(result,indent=2))
    except Exception:
        m.update(status='failed',error=traceback.format_exc(),ended_at=projection.stamp());projection.json_write(s/'manifest.json',m);raise


if __name__=='__main__':main()
