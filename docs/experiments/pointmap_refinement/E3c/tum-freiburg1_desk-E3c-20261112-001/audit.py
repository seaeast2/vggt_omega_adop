"""Read-only post-run provenance and actual projected movement audit."""
import hashlib
import json
from pathlib import Path

import numpy as np


stage = Path('results/pointmap_refinement/tum-freiburg1_desk-E3c-20261112-001/stages/E3c')
manifest = json.loads((stage/'manifest.json').read_text())
assert manifest['status'] == 'completed'
records = manifest['artifacts'] + manifest['inputs'] + manifest['gt_inputs']
for row in records:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes']
    with path.open('rb') as stream: assert hashlib.file_digest(stream, 'sha256').hexdigest() == row['sha256'], path
with np.load(stage/'artifacts/common/cameras_targets.npz') as data:
    ks = data['intrinsics']; es = data['extrinsics']
result = {'sealed_artifacts_verified': len(manifest['artifacts']), 'inputs_verified': len(manifest['inputs']),
          'gt_inputs_verified': len(manifest['gt_inputs']), 'arms': {}}
for arm in ['control_E0b', 'treatment_E0c']:
    root = stage/'arms'/arm
    with np.load(root/'initial/shared_map.npz') as data:
        xyz0 = data['xyz0']; owner = data['owner_camera']; observed = data['observed_camera_mask']
        active = np.flatnonzero(data['active_candidate']); indices = data['obs_indices']; counts = data['n_observed']
        labels = data['source_to_shared']
    assert np.array_equal(np.sort(indices), np.arange(589824))
    assert np.array_equal(labels[indices], np.repeat(np.arange(len(xyz0)), counts))
    with np.load(root/'maps/selected_positions.npz') as data: xyz = data['xyz']; delta = data['delta']
    with np.load(root/'maps/last_positions.npz') as data: assert np.array_equal(xyz, data['xyz'])
    own = []; cross = []
    for camera in range(3):
        cams = [x[active]@es[camera, :, :3].T+es[camera, :, 3] for x in [xyz0, xyz]]
        pixels = [(cam@ks[camera].T)[:, :2]/cam[:, 2, None] for cam in cams]
        shift = np.linalg.norm(pixels[1]-pixels[0], axis=1)
        valid = ((cams[0][:, 2] > 0) & (cams[1][:, 2] > 0) & np.isfinite(shift))
        own.extend(shift[valid & (owner[active] == camera)].tolist())
        use = valid & (owner[active] != camera) & observed[active, camera]
        for pixel in pixels:
            use &= (pixel[:, 0] >= 0) & (pixel[:, 0] <= 511) & (pixel[:, 1] >= 0) & (pixel[:, 1] <= 383)
        cross.extend(shift[use].tolist())
    assert max(own) < 1e-5 and max(cross) > 0
    def stats(values):
        return {'count': len(values), 'mean': float(np.mean(values)), 'median': float(np.median(values)),
                'p95': float(np.quantile(values, .95)), 'max': float(np.max(values))}
    result['arms'][arm] = {'CSR_partition_verified': True, 'selected_equals_last': True,
                          'owner_projection_shift_native_pixels': stats(own),
                          'observed_nonowner_projection_shift_native_pixels_both_inside': stats(cross),
                          'log_bound_fraction_of_active': float((np.abs(delta) >= .05-1e-6).mean())}
print(json.dumps(result, indent=2))
