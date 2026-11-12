"""Independent saved-artifact and RGB provenance checks (CPU)."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args()
c=json.loads((a.stage/'config_resolved.json').read_text())
with np.load(c['input']) as source, np.load(a.stage/'artifacts/geometry/observations.npz') as obs:
    rgb=source['images'][0].transpose(0,2,3,1)
    frames=json.loads((a.stage/'artifacts/geometry/frames.json').read_text())
    n,h,w,_=rgb.shape
    for i,row in enumerate(frames):
        original=Path(row['path'])
        with original.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
        prepared=np.asarray(Image.open(original).convert('RGB').resize((w,h),Image.Resampling.BICUBIC),dtype=np.float32)/255
        assert np.array_equal(rgb[i],prepared)
    frame=obs['frame_id'];u,v=obs['pixel_uv'].T
    assert np.array_equal(obs['rgb'],np.rint(rgb[frame,v,u]*255).astype('uint8'))
    assert np.array_equal(obs['depth_initial'],source['depth'][0,frame,v,u,0])
    assert np.isfinite(obs['world_xyz_initial']).all()
    assert len(set(zip(frame.tolist(),v.tolist(),u.tolist())))==len(frame)
    # Image resize affine is centre-based, separate from integer model camera grid.
    scale=np.diag([w/640,h/480,1.]);scale[0,2]=(w/640-1)/2;scale[1,2]=(h/480-1)/2
    k0=np.array([[525.,0,319.5],[0,525.,239.5],[0,0,1.]])
    k1=scale@k0
    xyz=np.array([[.1,.2,2.],[-.2,.3,3.],[0,0,1.]])
    q0=xyz@k0.T;q0/=q0[:,2:3]
    q1=xyz@k1.T;q1/=q1[:,2:3]
    assert np.allclose(q1,q0@scale.T)
result={'rgb_original_hash_and_bicubic_reproduction':'passed','observation_source_pixel_rgb_depth':'passed','unique_frame_pixel_ids':True,'all_saved_xyz_finite':True,'resize_intrinsics_affine_contract':'passed','gt_intrinsics_usage':'default K used only for transform test; not for GT metric accuracy','status':'passed'}
(a.stage/'evaluation/artifact_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
