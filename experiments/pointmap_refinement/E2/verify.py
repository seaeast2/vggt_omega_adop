"""Fusion association/CSR/representative invariants and independent saved-metric checks."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
from fuse import clusters,e1
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());parent=Path(c['parent_stage'])
for frames,edges,groups in [([0,1],[[0,1]],1),([0,0],[[0,1]],2),([0,1,2],[[0,1],[1,2]],2),([0,1,2],[[0,1],[0,2],[1,2]],1)]:
    labels,_=clusters(np.array(frames),np.array(edges),np.arange(len(edges))+1.);assert len(np.unique(labels))==groups
with np.load(s/'artifacts/shared/shared_map_initial.npz') as d:shared={key:d[key] for key in d.files}
with np.load(parent/'artifacts/f0/observations.npz') as d:obs={key:d[key] for key in d.files}
with np.load(s/'artifacts/diagnostics/association.npz') as d:weights=d['source_weights'];normal=d['source_normal'];edges=d['edges'];distance=d['distances']
labels=shared['source_to_shared'];order=shared['obs_indices'];offset=shared['obs_offsets'];count=shared['n_observed'];x=obs['world_xyz_initial'];m=len(count)
assert np.array_equal(np.sort(order),np.arange(len(x))) and offset[-1]==len(x)
assert np.array_equal(np.diff(offset),count) and np.array_equal(labels[order],np.repeat(np.arange(m),count))
assert np.all(count<=3) and np.array_equal(shared['observed_camera_mask'].sum(1),count)
assert np.array_equal(shared['xyz'],shared['xyz0'])
expected=np.column_stack([np.bincount(labels,weights*x[:,j])/np.bincount(labels,weights) for j in range(3)]);assert np.array_equal(expected,shared['xyz'])
codes=set((np.minimum(edges[:,0],edges[:,1])*len(x)+np.maximum(edges[:,0],edges[:,1])).tolist());radius=json.loads((s/'evaluation/fusion.json').read_text())['spatial_radius_model_units']
for size in [2,3]:
    selected=np.flatnonzero(count==size);members=order[offset[selected,None]+np.arange(size)];frames=obs['frame_id'][members];assert np.all(np.diff(np.sort(frames,axis=1),axis=1)>0)
    assert np.allclose(shared['rgb_fixed'][selected],np.median(obs['rgb'][members],axis=1)/255.,atol=1e-7)
    for i in range(size):
        for j in range(i+1,size):
            assert np.all(np.linalg.norm(x[members[:,i]]-x[members[:,j]],axis=1)<=radius+1e-10)
            assert all(min(a,b)*len(x)+max(a,b) in codes for a,b in zip(members[:,i],members[:,j]))
dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('n_observed','u1'),('owner','<i2')])
with (s/'artifacts/shared/shared_map_initial.ply').open('rb') as f:
    while f.readline()!=b'end_header\n':pass
    ply=np.fromfile(f,dtype=dtype)
assert len(ply)==m and np.array_equal(ply['n_observed'],count)
assert np.array_equal(np.column_stack([ply[k] for k in ['x','y','z']]),shared['xyz'])
for path in (s/'artifacts/renders').glob('*.npz'):
    with np.load(path) as d:
        assert np.isfinite(d['rgb']).all() and np.isfinite(d['depth']).all();assert np.array_equal(d['coverage'],d['alpha']>=.5)
for path in (s/'artifacts/renders').glob('*.png'):assert cv2.imread(str(path)).shape==(126,512,3)
comparison=json.loads((s/'evaluation/geometry_comparison.json').read_text())
for row in comparison['pairs']:
    with np.load(s/'artifacts/diagnostics'/f"pair_{row['source']}_to_{row['target']}.npz") as d:
        fixed=d['fixed_evaluation_mask'];covered=d['covered_after'];assert fixed.sum()==row['fixed_pixels'] and covered.sum()==row['covered_after']
        with np.load(parent/'artifacts/diagnostics'/f"pair_{row['source']}_to_{row['target']}.npz") as old:assert np.array_equal(fixed,old['evaluation_mask'])
result={'controlled_identical_cross_frame_merge':'passed','same_frame_conflict_rejected':'passed','nonclique_chain_rejected':'passed','all_observations_assigned_once':'passed','all_groups_unique_frames_and_cliques':'passed','all_pair_spatial_bounds':'passed','weighted_xyz_and_median_rgb':'passed','no_post_fusion_optimizer_update':'passed','ply_npz_and_render_reload':'passed','e1_fixed_masks_unchanged':'passed','status':'passed'}
(s/'evaluation/verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
