"""CPU preparation of E0b-initialized optimization; never reads GT arrays."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); args = parser.parse_args()
    source = Path('experiments/pointmap_refinement/E3b'); c = json.loads((source/'config.json').read_text())
    s = Path('results/pointmap_refinement')/args.run_id/'stages/E3b'; s.mkdir(parents=True, exist_ok=False)
    for name in ['logs','evaluation','artifacts/initial','artifacts/checkpoints','artifacts/maps','artifacts/renders','artifacts/figures','artifacts/source']:
        (s/name).mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file(): shutil.copy2(path, s/'artifacts/source'/path.name)
    for name,path in [('projection.py','experiments/pointmap_refinement/E0a/run.py'),
                      ('geometry.py','experiments/pointmap_refinement/E1/geometry.py'),
                      ('renderer.py','experiments/pointmap_refinement/P2/renderer.py')]:
        shutil.copy2(path,s/'artifacts/source'/name)
    p=load_module('projection',s/'artifacts/source/projection.py'); g=load_module('geometry',s/'artifacts/source/geometry.py')
    m={'status':'running','phase':'preparation','experiment_code':'E3b','run_id':args.run_id,'started_at':p.stamp()}
    p.json_write(s/'manifest.json',m); p.json_write(s/'config_resolved.json',c|{'run_id':args.run_id})
    parents=[Path(c[name]) for name in ['parent_stage','e0_stage','e1_stage']]; inputs=[]
    for parent in parents:
        pm=json.loads((parent/'manifest.json').read_text()); assert pm['status']=='completed'
        for item in pm.get('artifacts',[]): assert p.record(item['path'])==item
        inputs.append(p.record(parent/'manifest.json'))
    def tracked(path):
        inputs.append(p.record(path)); return path
    with np.load(tracked(parents[0]/'artifacts/maps/fused_map.npz')) as data: fused={key:data[key] for key in data.files}
    with np.load(tracked(parents[1]/'artifacts/baseline/observations.npz')) as data:
        original_rgb=data['rgb']; fid=data['frame_id']
    with np.load(tracked(parents[1]/'artifacts/baseline/vggt_omega_raw.npz')) as data:
        k=data['intrinsics'][0].astype(float); e=data['extrinsics'][0].astype(float)
        depth=data['depth'][0,...,0].astype(float); confidence=data['depth_conf'][0]
        image_rgb=data['images'][0].transpose(0,2,3,1)
    frame_path=tracked(parents[1]/'artifacts/baseline/frames.json'); shutil.copy2(frame_path,s/'artifacts/initial/frames.json')
    xyz=fused['xyz']; owner=fused['owner_frame_id']; counts=fused['n_observed']; n=len(xyz)
    labels=fused['source_to_fused']; offsets=fused['obs_offsets']; indices=fused['obs_indices']
    assert np.array_equal(np.bincount(labels,minlength=n),counts)
    assert np.array_equal(labels[indices],np.repeat(np.arange(n),counts))
    bits=np.zeros(n,np.uint8); np.bitwise_or.at(bits,labels,(1<<fid).astype(np.uint8))
    assert np.array_equal(bits,fused['source_frame_mask'])
    observed=((bits[:,None]>>np.arange(3))&1).astype(bool)
    color=np.empty((n,3),np.float32)
    for count in np.unique(counts):
        groups=np.flatnonzero(counts==count)
        ids=indices[offsets[groups,None]+np.arange(int(count))[None,:]]
        color[groups]=np.median(original_rgb[ids],axis=1)/255.
    centers=np.stack([-cam[:,:3].T@cam[:,3] for cam in e])
    direction=xyz-centers[owner]; distance=np.linalg.norm(direction,axis=1); direction/=distance[:,None]
    assert np.allclose(centers[owner]+direction*distance[:,None],xyz,atol=1e-12)
    vis=np.zeros((n,3),bool); height,width=depth.shape[1:]; v=c['visibility']
    for camera in range(3):
        front,_,_=g.front_map(xyz,k[camera],e[camera],height,width)
        cam=xyz@e[camera,:,:3].T+e[camera,:,3]; z=cam[:,2]
        q=(cam@k[camera].T)[:,:2]/z[:,None]
        inside=(z>0)&np.isfinite(q).all(1)&(q[:,0]>=0)&(q[:,0]<=width-1)&(q[:,1]>=0)&(q[:,1]<=height-1)
        ids=np.flatnonzero(inside); xy=np.rint(q[ids]).astype(int); u,w=xy[:,0],xy[:,1]
        target=depth[camera,w,u]; safe=g.edge_safe(depth[camera],v['depth_edge_relative'])
        vis[ids,camera]=(safe[w,u] & (confidence[camera,w,u]>=np.percentile(confidence[camera],v['confidence_quantile'])) &
                         (z[ids]<=front[w,u]*(1+v['front_relative'])) &
                         (np.abs(z[ids]-target)<=np.median(depth)*v['prior_absolute_median_fraction']+v['prior_relative']*target))
    rays=xyz[:,None,:]-centers[None,:,:]; rays/=np.linalg.norm(rays,axis=2)[...,None]
    parallax=np.zeros(n)
    for i in range(3):
        for j in range(i+1,3):
            angle=np.degrees(np.arccos(np.clip((rays[:,i]*rays[:,j]).sum(1),-1,1)))
            parallax=np.maximum(parallax,np.where(observed[:,i]&observed[:,j],angle,0))
    multi=observed.sum(1)>=2; active=multi&(parallax>1e-6)&np.all(~observed|vis,axis=1)
    assert active.any()
    shared={'xyz0':xyz,'rgb_fixed':color,'owner_camera':owner,'owner_pixel_uv':fused['owner_pixel_uv'],
            'n_observed':counts,'observed_camera_mask':observed,'source_frame_mask':bits,
            'source_to_shared':labels,'obs_offsets':offsets,'obs_indices':indices,
            'owner_ray_world':direction,'owner_ray_distance':distance,'parallax_max_degrees':parallax,
            'visibility_initial':vis,'active_candidate':active,
            'owner_colors_rgb':fused['owner_colors_rgb'],'source_mix_rgb':fused['source_mix_rgb']}
    np.savez_compressed(s/'artifacts/initial/shared_map_initial.npz',**shared)
    with np.load(s/'artifacts/initial/shared_map_initial.npz') as saved:
        for name in shared: assert np.array_equal(saved[name],shared[name])
    rh,rw=c['render_hw']; targets=[]; masks=[]
    for camera in range(3):
        targets.append(cv2.resize(image_rgb[camera],(rw,rh),interpolation=cv2.INTER_AREA))
        path=tracked(parents[2]/f'artifacts/renders/evaluation_masks_frame_{camera}.npz')
        with np.load(path) as data: masks.append(data['fixed_all_mask'])
    np.savez_compressed(s/'artifacts/initial/cameras_and_targets.npz',intrinsics=k,extrinsics=e,targets=np.stack(targets),e1_masks=np.stack(masks))
    summary={'parent_points':n,'initial_xyz_exactly_E0b':True,'multi_source_points':int(multi.sum()),
             'nonzero_parallax_multi_source_points':int((multi&(parallax>1e-6)).sum()),'active_points':int(active.sum()),
             'inactive_points':int((~active).sum()),'point_rgb':'fixed channel median of original E0 observation RGB in E0b CSR',
             'camera_and_topology_fixed':True,'gt_read':False,'inputs':inputs}
    p.json_write(s/'evaluation/preparation.json',summary)
    p.json_write(s/'progress.json',{'events':[{'time':p.stamp(),'phase':'prepared','active_points':int(active.sum())}]})
    p.json_write(s/'environment_cpu.json',{'project_commit_before_run':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 'source_files':[p.record(path) for path in sorted((s/'artifacts/source').iterdir()) if path.is_file()]})
    m.update(phase='prepared',inputs=inputs); p.json_write(s/'manifest.json',m)
    (s/'logs/prepare.log').write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
