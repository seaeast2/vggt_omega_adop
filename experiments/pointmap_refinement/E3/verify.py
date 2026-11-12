"""Independent saved checkpoint, frozen attributes, PLY and GT scale checks."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());parent=Path(c['parent_stage'])
train=json.loads((s/'evaluation/training.json').read_text());history=json.loads((s/'evaluation/checkpoint_history.json').read_text());assert train['selected_step']==min(history,key=lambda x:x['training_charbonnier'])['step']
with np.load(parent/'artifacts/shared/shared_map_initial.npz') as d:initial={key:d[key] for key in d.files}
dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('n_observed','u1'),('owner','<i2')])
for name,step in [('selected',train['selected_step']),('last',c['steps'])]:
    with np.load(s/'artifacts/maps'/f'shared_map_{name}.npz') as d:
        xyz=d['xyz'].copy()
        for key in ['xyz0','rgb_fixed','obs_offsets','obs_indices','obs_camera','obs_pixel','source_to_shared','owner_camera','n_observed']:assert np.array_equal(d[key],initial[key])
        with np.load(s/'artifacts/checkpoints'/f'step_{step:04d}.npz') as checkpoint:assert np.array_equal(checkpoint['delta'],d['log_ray_delta'])
    with (s/'artifacts/maps'/f'shared_map_{name}.ply').open('rb') as f:
        while f.readline()!=b'end_header\n':pass
        ply=np.fromfile(f,dtype=dtype)
    assert np.array_equal(np.column_stack([ply[key] for key in ['x','y','z']]),xyz)
    for i in range(3):
        with np.load(s/'artifacts/renders'/f'{name}_frame_{i}.npz') as d:
            assert np.isfinite(d['rgb']).all() and np.isfinite(d['depth']).all()
            assert np.array_equal(d['coverage'],d['alpha']>=.5)
for path in (s/'artifacts/renders').glob('comparison_*.png'):assert cv2.imread(str(path)).shape==(126,512,3)
gtdata=json.loads((s/'evaluation/gt_depth.json').read_text());scale=gtdata['scale_gt_m_per_model_unit'];ratios=[]
for i in range(3):
    with np.load(Path(c['gt_stage'])/'artifacts/gt'/f'aligned_{i}.npz') as d:gt=d['depth_m']
    with np.load(s/'artifacts/renders'/f'native_depth_initial_{i}.npz') as d:mask=d['fixed_gt_mask'];ratios.append(gt[mask]/d['depth_model'][mask])
assert np.isclose(scale,np.median(np.concatenate(ratios)),rtol=1e-12)
for name in ['initial','selected','last']:
    errors=[]
    for i in range(3):
        with np.load(Path(c['gt_stage'])/'artifacts/gt'/f'aligned_{i}.npz') as d:gt=d['depth_m']
        with np.load(s/'artifacts/renders'/f'native_depth_{name}_{i}.npz') as d:mask=d['common_gt_mask'];errors.append(d['depth_model'][mask]*scale-gt[mask])
    rmse=float(np.sqrt(np.mean(np.concatenate(errors)**2)));row=next(r for r in gtdata['rows'] if r['method']==name and r['frame']=='pooled');assert np.isclose(rmse,row['rmse_m_common'],rtol=1e-12)
(s/'evaluation/saved_artifact_checks.json').write_text(json.dumps({'checkpoint_selection_and_export':'passed','frozen_rgb_csr_owner_and_initial_xyz':'passed','ply_positions_and_render_reload':'passed','single_initial_scale_and_pooled_gt_rmse_recalculation':'passed','status':'passed'},indent=2))
print('E3 saved artifacts and GT metric recalculation passed')
