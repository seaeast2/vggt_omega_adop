"""Post-training E0b/selected/last evaluation, palette exports and final sealing."""
import argparse
import json
from pathlib import Path
import platform

import cv2
import numpy as np
from prepare import load_module


def write_ply(path,xyz,rgb,owner,counts,bits):
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),
                    ('owner','<i2'),('n_observed','<u4'),('source_mask','u1')])
    records=np.empty(len(xyz),dtype=dtype)
    for axis,key in enumerate(['x','y','z']): records[key]=xyz[:,axis]
    for axis,key in enumerate(['red','green','blue']): records[key]=rgb[:,axis]
    records['owner'],records['n_observed'],records['source_mask']=owner,counts,bits
    header=('ply\nformat binary_little_endian 1.0\ncomment E3b E0b-initialized RGB optimization; diagnostic colors\n'
            f'element vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\n'
            'property short owner\nproperty uint n_observed\nproperty uchar source_mask\nend_header\n')
    with Path(path).open('xb') as stream: stream.write(header.encode()); records.tofile(stream)
    with Path(path).open('rb') as stream:
        while stream.readline()!=b'end_header\n': pass
        assert np.array_equal(np.fromfile(stream,dtype=dtype),records)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',type=Path,required=True); args=parser.parse_args(); s=args.stage
    p=load_module('projection',s/'artifacts/source/projection.py'); g=load_module('geometry',s/'artifacts/source/geometry.py')
    m=json.loads((s/'manifest.json').read_text()); assert m['phase']=='trained'
    c=json.loads((s/'config_resolved.json').read_text()); training=json.loads((s/'evaluation/training.json').read_text())
    with np.load(s/'artifacts/initial/shared_map_initial.npz') as data: initial={key:data[key] for key in data.files}
    with np.load(s/'artifacts/initial/cameras_and_targets.npz') as data: k=data['intrinsics']; e=data['extrinsics']
    active=np.flatnonzero(initial['active_candidate']); inactive=~initial['active_candidate']
    points={'initial':initial['xyz0']}; parameters={}; movement={}
    for label in ['selected','last']:
        with np.load(s/f'artifacts/maps/{label}_positions.npz') as data:
            xyz=data['xyz']; delta=data['delta']; assert np.array_equal(data['active_indices'],active)
        expected=initial['xyz0'][active]+initial['owner_ray_world'][active]*(initial['owner_ray_distance'][active]*np.expm1(delta))[:,None]
        assert np.array_equal(xyz[inactive],initial['xyz0'][inactive])
        assert np.allclose(xyz[active],expected,rtol=0,atol=1e-12)
        assert np.max(np.abs(delta))<=c['log_ray_delta_bound']+1e-7
        displacement=np.linalg.norm(xyz-initial['xyz0'],axis=1)
        movement[label]={'moved_active_over_1e_8':int((displacement[active]>1e-8).sum()),
                         'active_displacement':g.stats(displacement[active]),
                         'all_displacement':g.stats(displacement),
                         'bound_points':int((np.abs(delta)>=c['log_ray_delta_bound']-1e-6).sum())}
        points[label]=xyz; parameters[label]=delta
    with np.load(Path(c['parent_stage'])/'artifacts/maps/fused_map.npz') as parent:
        assert np.array_equal(points['initial'],parent['xyz'])
        assert np.array_equal(initial['source_to_shared'],parent['source_to_fused'])
        assert np.array_equal(initial['obs_offsets'],parent['obs_offsets']) and np.array_equal(initial['obs_indices'],parent['obs_indices'])
    if training['selected_step']==0: assert np.array_equal(points['selected'],points['initial'])
    assert movement['last']['moved_active_over_1e_8']>0
    n=3; height,width=384,512; native={}; source_images={}
    for label,xyz in points.items():
        payload=initial.copy(); payload.update(xyz=xyz,optimized_indices=active,log_ray_delta=parameters.get(label,np.zeros(len(active))))
        np.savez_compressed(s/f'artifacts/maps/shared_map_{label}.npz',**payload)
        with np.load(s/f'artifacts/maps/shared_map_{label}.npz') as saved:
            for key in payload: assert np.array_equal(saved[key],payload[key])
        for mode,color in [('owner',initial['owner_colors_rgb']),('source_mix',initial['source_mix_rgb'])]:
            write_ply(s/f'artifacts/maps/{label}_{mode}.ply',xyz,color,initial['owner_camera'],initial['n_observed'],initial['source_frame_mask'])
        native[label]=[]; source_images[label]=[]
        for camera in range(n):
            z,_,_=g.front_map(xyz,k[camera],e[camera],height,width); native[label].append(z)
            _,win,_=p.front(xyz,np.arange(len(xyz)),k[camera],e[camera],height,width); hit=win>=0
            rgb=np.zeros((height,width,3),np.uint8); rgb[hit]=initial['source_mix_rgb'][win[hit]]
            source_images[label].append(rgb); p.image_write(s/f'artifacts/renders/{label}_source_camera_{camera}.png',rgb)
    # First GT array access occurs only here, after the training checkpoint selection is fixed.
    gt_stage=Path(c['gt_stage']); gm=json.loads((gt_stage/'manifest.json').read_text()); assert gm['status']=='completed'
    gt=[]; gt_inputs=[p.record(gt_stage/'manifest.json')]
    for camera in range(n):
        path=gt_stage/f'artifacts/gt/aligned_{camera}.npz'
        old=next(row for row in gm['artifacts'] if row['path']==str(path)); assert p.record(path)==old; gt_inputs.append(old)
        with np.load(path) as data: gt.append(data['depth_m'].astype(float))
    fixed=[np.isfinite(native['initial'][i])&(native['initial'][i]>0)&(gt[i]>0) for i in range(n)]
    scale=float(np.median(np.concatenate([gt[i][fixed[i]]/native['initial'][i][fixed[i]] for i in range(n)])))
    common=[fixed[i]&np.isfinite(native['selected'][i])&np.isfinite(native['last'][i]) for i in range(n)]
    rows=[]; summary=[]
    for label in points:
        errors=[]; relatives=[]; total_covered=0
        for camera in range(n):
            covered=fixed[camera]&np.isfinite(native[label][camera]); mask=common[camera]
            err=native[label][camera][mask]*scale-gt[camera][mask]; rel=np.abs(err)/gt[camera][mask]
            errors.append(err); relatives.append(rel); total_covered+=int(covered.sum())
            rows.append({'state':label,'camera':camera,'fixed_pixels':int(fixed[camera].sum()),'covered_fixed_pixels':int(covered.sum()),
                         'common_pixels':int(mask.sum()),'coverage_of_fixed':float(covered.sum()/fixed[camera].sum()),
                         'rmse_m':float(np.sqrt(np.mean(err**2))),'absrel':float(rel.mean())})
            np.savez_compressed(s/f'artifacts/renders/native_depth_{label}_{camera}.npz',depth_model=native[label][camera],
                                gt_depth_m=gt[camera],fixed_gt_mask=fixed[camera],common_gt_mask=mask)
        err=np.concatenate(errors); rel=np.concatenate(relatives); fixed_total=sum(int(mask.sum()) for mask in fixed)
        summary.append({'state':label,'points':len(points[label]),'common_pixels':len(err),'rmse_m':float(np.sqrt(np.mean(err**2))),
                        'absrel':float(rel.mean()),'fixed_pixels':fixed_total,'covered_fixed_pixels':total_covered,
                        'coverage_of_fixed':total_covered/fixed_total})
    p.json_write(s/'evaluation/gt_depth.json',{'scale_m_per_model_unit':scale,'scale_fit':'median GT/initial E0b native front-Z, once after training',
                 'gt_used_in_training_or_selection':False,'summary':summary,'per_camera':rows,
                 'limitations':'same-input-view scale-aligned depth; common support is coverage-dependent; no heldout/full 3D/wall ROI claim'})
    p.json_write(s/'evaluation/displacement.json',movement)
    frames=json.loads((s/'artifacts/initial/frames.json').read_text()); rgb_cells=[]; source_cells=[]
    for camera in range(n):
        images=[]
        for label in ['initial','selected','last']:
            with np.load(s/f'artifacts/renders/{label}_frame_{camera}.npz') as data:
                image=np.rint(data['rgb'].clip(0,1)*255).astype(np.uint8); target=np.rint(data['target'].clip(0,1)*255).astype(np.uint8)
                with np.load(s/f'artifacts/renders/initial_frame_{camera}.npz') as start:
                    assert np.array_equal(data['train_mask'],start['train_mask']) and np.array_equal(data['target'],start['target'])
            images.append(cv2.resize(image,(width,height),interpolation=cv2.INTER_NEAREST))
        rgb_cells.append([cv2.resize(target,(width,height),interpolation=cv2.INTER_NEAREST)]+images)
        source_cells.append([source_images[label][camera] for label in ['initial','selected','last']])
    p.panel(s/'artifacts/figures/rgb_comparison.png',rgb_cells,['Target RGB (4x display)','E0b initial','E3b selected','E3b last'],frames,height,width)
    p.panel(s/'artifacts/figures/source_comparison.png',source_cells,['E0b initial source mix','E3b selected source mix','E3b last source mix'],frames,height,width)
    for row in m['inputs']: assert p.record(row['path'])==row
    cpu=json.loads((s/'environment_cpu.json').read_text())
    for row in cpu['source_files']: assert p.record(row['path'])==row
    verification={'status':'passed','initial_xyz_and_CSR_exact_E0b':True,'inactive_xyz_exactly_fixed':True,
                  'active_xyz_equals_ray_gradient_parameterization':True,'log_bounds':True,'last_actual_movement_nonzero':True,
                  'all_metadata_fixed':True,'point_count_fixed':True,'ply_npz_png_reload':True,'train_masks_and_targets_fixed':True,
                  'GT_after_training_and_selection_only':True,'single_initial_only_GT_scale':True,'parent_and_executed_source_hashes':True}
    p.json_write(s/'evaluation/verification.json',verification)
    p.json_write(s/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,
                 'platform':platform.platform(),'CPU':cpu,'GPU_training':training})
    events=json.loads((s/'progress.json').read_text()); events['events'].append({'time':p.stamp(),'phase':'evaluated','gt_summary':summary}); p.json_write(s/'progress.json',events)
    output={'training':training,'movement':movement,'gt_summary':summary,'scale':scale}
    (s/'logs/evaluate.log').write_text(json.dumps(output,indent=2)+'\n')
    m.update(status='completed',phase='evaluated',ended_at=p.stamp(),completion_criteria_met=True,gt_inputs=gt_inputs,
             optimization_effect='improved_training_loss' if training['selected_step']>0 else 'selected_initial_no_improvement')
    m['artifacts']=[p.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts]
    p.json_write(s/'manifest.json',m); print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__': main()
