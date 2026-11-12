"""Read-only audit of the sealed outdoor runs and their saved point motion."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


for scene in ['hkairport01','amtown01']:
    run=f'{scene}-E3e-20261112-001';s=Path('results/pointmap_refinement')/run/'stages/E3e'
    m=json.loads((s/'manifest.json').read_text());assert m['status']=='completed'
    for row in m['artifacts']+m['inputs']:
        p=Path(row['path']);assert p.stat().st_size==row['bytes']
        with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256'],p
    assert not m['gt_inputs']
    with np.load(s/'artifacts/initial/shared_map.npz') as a:initial={k:a[k] for k in a.files}
    with np.load(s/'artifacts/initial/cameras_targets_masks.npz') as a:
        ks=a['intrinsics'];es=a['extrinsics'];targets=a['targets'];native=a['targets_native'];masks=a['train_masks']
    active=np.flatnonzero(initial['active_candidate']);inactive=~initial['active_candidate']
    for state in ['initial','selected','last']:
        with np.load(s/f'artifacts/maps/shared_map_{state}.npz') as a:
            for key in initial:assert np.array_equal(a[key],initial[key])
            assert np.array_equal(np.sort(a['obs_indices']),np.arange(663552))
            assert np.array_equal(a['source_to_shared'][a['obs_indices']],np.repeat(np.arange(len(a['xyz'])),a['n_observed']))
            assert np.array_equal(a['xyz'][inactive],initial['xyz0'][inactive])
            if state=='selected':assert np.array_equal(a['xyz'],initial['xyz0'])
            if state=='last':xyz=a['xyz'].copy()
    owner=initial['owner_camera'][active];own=[];cross=[]
    for i in range(3):
        cam=[p[active]@es[i,:,:3].T+es[i,:,3] for p in [initial['xyz0'],xyz]]
        uv=[(q@ks[i].T)[:,:2]/q[:,2,None] for q in cam];shift=np.linalg.norm(uv[1]-uv[0],axis=1)
        own.extend(shift[owner==i]);use=(owner!=i)&initial['observed_camera_mask'][active,i]
        for q,z in zip(uv,cam):use&=(z[:,2]>0)&(q[:,0]>=0)&(q[:,0]<=511)&(q[:,1]>=0)&(q[:,1]<=431)
        cross.extend(shift[use])
    assert max(own)<1e-5 and max(cross)>0
    canvas=cv2.imread(str(s/'artifacts/figures/rgb_comparison.png'))[...,::-1]
    for i in range(3):
        y=40+i*(432+34)+34
        target=cv2.resize(np.rint(targets[i].clip(0,1)*255).astype(np.uint8),(512,432),interpolation=cv2.INTER_NEAREST)
        assert np.array_equal(canvas[y:y+432,:512],target)
        for state in ['initial','selected','last']:
            with np.load(s/f'artifacts/renders/{state}_{i}.npz') as a:assert np.array_equal(a['train_mask'],masks[i])
    result={'status':'passed','sealed_artifacts_verified':len(m['artifacts']),'inputs_verified':len(m['inputs']),'GT_inputs':0,
        'CSR_partition_all_663552_observations':True,'all_metadata_RGB_and_inactive_fixed':True,'selected_equals_initial':True,
        'last_owner_projection_shift_max_native_pixels':float(np.max(own)),
        'last_observed_nonowner_pixel_shift':{'pairs':len(cross),'mean':float(np.mean(cross)),'median':float(np.median(cross)),'p95':float(np.quantile(cross,.95)),'max':float(np.max(cross))},
        'comparison_left_column_exact_128x108_then_4x_nearest':True}
    d=Path('docs/experiments/pointmap_refinement/E3e')/run;d.mkdir(exist_ok=True);(d/'postrun_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(scene,json.dumps(result))
