"""Ray initialization through fused XYZ, conservative future candidates, scientific map."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text());parent=Path(c['parent_stage'])
with np.load(s/'artifacts/shared/shared_map_initial.npz') as d:shared={key:d[key] for key in d.files}
with np.load(parent/'artifacts/f0/vggt_omega_raw.npz') as d:es=d['extrinsics'][0].astype('float64');rgb=d['images'][0].transpose(0,2,3,1)
with np.load(parent/'artifacts/f0/observations.npz') as d:original=d['world_xyz_initial']
centres=np.stack([-e[:,:3].T@e[:,3] for e in es]);direction=shared['xyz0']-centres[shared['owner_camera']];distance=np.linalg.norm(direction,axis=1);direction/=distance[:,None]
assert np.allclose(centres[shared['owner_camera']]+distance[:,None]*direction,shared['xyz0'],atol=1e-12)
active=(shared['n_observed']>=2)&(shared['parallax_max_degrees']>1e-6)&np.all(~shared['observed_camera_mask']|shared['visibility_estimated'],axis=1)
np.savez_compressed(s/'artifacts/shared/ray_initialization.npz',owner_camera=shared['owner_camera'],owner_ray_world=direction,owner_ray_distance=distance,active_candidate=active)
summary={'candidate_count':int(active.sum()),'ray_contract':'unit world ray through fused xyz0 from owner camera; distance is Euclidean ray length, not camera Z','owner_pixel_note':'fused representative need not lie on the original owner observation pixel ray; use the fused-point ray to preserve initial XYZ','candidate_note':'multi-observed, nonzero parallax and estimated visible in all source cameras; not proof of photometric observability or correctness','positions_optimized':False}
(s/'evaluation/optimization_handoff.json').write_text(json.dumps(summary,indent=2))
n,h,w,_=rgb.shape;labels=shared['source_to_shared'];obs_count=shared['n_observed'][labels].reshape(n,h,w);radius=json.loads((s/'evaluation/fusion.json').read_text())['spatial_radius_model_units'];movement=np.linalg.norm(original-shared['xyz0'][labels],axis=1).reshape(n,h,w)/radius
canvas=np.full((n*(h+35),w*3,3),255,np.uint8);palette=np.array([[0,0,0],[180,180,180],[0,180,0],[0,120,255]],np.uint8)
for i in range(n):
    heat=cv2.applyColorMap(np.rint(np.clip(movement[i],0,1)*255).astype('uint8'),cv2.COLORMAP_TURBO)
    for j,(name,image) in enumerate([('source RGB',np.rint(rgb[i]*255).astype('uint8')[...,::-1]),('group count: 1 grey / 2 green / 3 orange',palette[obs_count[i]]),('source displacement / spatial radius',heat)]):
        row=i*(h+35);canvas[row+35:row+35+h,j*w:(j+1)*w]=image;cv2.putText(canvas,name,(j*w+3,row+22),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
assert cv2.imwrite(str(s/'artifacts/diagnostics/fusion_groups.png'),canvas)
print(json.dumps(summary,indent=2))
