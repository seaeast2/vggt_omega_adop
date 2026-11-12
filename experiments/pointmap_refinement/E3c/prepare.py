"""CPU-only matched E0b/E0c preparation; no GT arrays are loaded."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import traceback

import cv2
import numpy as np


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def make_shared(fused, original_rgb, fid, k, e, depth, confidence, visibility, geometry):
    xyz = fused['xyz']; n = len(xyz); owner = fused['owner_frame_id']
    labels = fused['source_to_fused']; counts = fused['n_observed']
    offsets = fused['obs_offsets']; indices = fused['obs_indices']
    assert np.array_equal(np.bincount(labels, minlength=n), counts)
    assert np.array_equal(np.sort(indices), np.arange(len(original_rgb)))
    assert np.array_equal(labels[indices], np.repeat(np.arange(n), counts))
    bits = np.zeros(n, np.uint8)
    np.bitwise_or.at(bits, labels, (1 << fid).astype(np.uint8))
    assert np.array_equal(bits, fused['source_frame_mask'])
    observed = ((bits[:, None] >> np.arange(3)) & 1).astype(bool)
    color = np.empty((n, 3), np.float32)
    for count in np.unique(counts):
        groups = np.flatnonzero(counts == count)
        ids = indices[offsets[groups, None] + np.arange(int(count))[None, :]]
        color[groups] = np.median(original_rgb[ids], axis=1) / 255.
    if 'rgb_fixed_median' in fused:
        assert np.array_equal(color, fused['rgb_fixed_median'])
    centers = np.stack([-cam[:, :3].T @ cam[:, 3] for cam in e])
    direction = xyz - centers[owner]
    distance = np.linalg.norm(direction, axis=1); direction /= distance[:, None]
    assert np.allclose(centers[owner] + direction * distance[:, None], xyz, atol=1e-12)
    vis = np.zeros((n, 3), bool); height, width = depth.shape[1:]; v = visibility
    for camera in range(3):
        front, _, _ = geometry.front_map(xyz, k[camera], e[camera], height, width)
        cam = xyz @ e[camera, :, :3].T + e[camera, :, 3]; z = cam[:, 2]
        q = (cam @ k[camera].T)[:, :2] / z[:, None]
        inside = ((z > 0) & np.isfinite(q).all(1) & (q[:, 0] >= 0) &
                  (q[:, 0] <= width-1) & (q[:, 1] >= 0) & (q[:, 1] <= height-1))
        ids = np.flatnonzero(inside); xy = np.rint(q[ids]).astype(int); u, w = xy[:, 0], xy[:, 1]
        target = depth[camera, w, u]; safe = geometry.edge_safe(depth[camera], v['depth_edge_relative'])
        vis[ids, camera] = (safe[w, u] &
            (confidence[camera, w, u] >= np.percentile(confidence[camera], v['confidence_quantile'])) &
            (z[ids] <= front[w, u] * (1 + v['front_relative'])) &
            (np.abs(z[ids]-target) <= np.median(depth) * v['prior_absolute_median_fraction'] + v['prior_relative'] * target))
    rays = xyz[:, None, :] - centers[None, :, :]; rays /= np.linalg.norm(rays, axis=2)[..., None]
    parallax = np.zeros(n)
    for i in range(3):
        for j in range(i+1, 3):
            angle = np.degrees(np.arccos(np.clip((rays[:, i] * rays[:, j]).sum(1), -1, 1)))
            parallax = np.maximum(parallax, np.where(observed[:, i] & observed[:, j], angle, 0))
    multi = observed.sum(1) >= 2
    active = multi & (parallax > 1e-6) & np.all(~observed | vis, axis=1)
    assert active.any()
    shared = {'xyz0': xyz, 'rgb_fixed': color, 'owner_camera': owner, 'owner_pixel_uv': fused['owner_pixel_uv'],
              'n_observed': counts, 'observed_camera_mask': observed, 'source_frame_mask': bits,
              'source_to_shared': labels, 'obs_offsets': offsets, 'obs_indices': indices,
              'owner_ray_world': direction, 'owner_ray_distance': distance, 'parallax_max_degrees': parallax,
              'visibility_initial': vis, 'active_candidate': active,
              'owner_colors_rgb': fused['owner_colors_rgb'], 'source_mix_rgb': fused['source_mix_rgb']}
    summary = {'points': n, 'multi_source_points': int(multi.sum()), 'active_points': int(active.sum()),
               'inactive_points': int((~active).sum()), 'gt_loaded': False}
    return shared, summary


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); args = parser.parse_args()
    source = Path('experiments/pointmap_refinement/E3c'); c = json.loads((source/'config.json').read_text())
    s = Path('results/pointmap_refinement')/args.run_id/'stages/E3c'; s.mkdir(parents=True, exist_ok=False)
    for name in ['logs', 'evaluation', 'artifacts/source', 'artifacts/common', 'artifacts/figures']:
        (s/name).mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file(): shutil.copy2(path, s/'artifacts/source'/path.name)
    helpers = {'projection.py': 'experiments/pointmap_refinement/E0a/run.py',
               'geometry.py': 'experiments/pointmap_refinement/E1/geometry.py',
               'renderer.py': 'experiments/pointmap_refinement/P2c/renderer.py'}
    for name, path in helpers.items(): shutil.copy2(path, s/'artifacts/source'/name)
    p = load_module('projection', s/'artifacts/source/projection.py')
    g = load_module('geometry', s/'artifacts/source/geometry.py')
    m = {'status': 'running', 'phase': 'preparation', 'experiment_code': 'E3c', 'run_id': args.run_id, 'started_at': p.stamp()}
    p.json_write(s/'manifest.json', m); p.json_write(s/'config_resolved.json', c | {'run_id': args.run_id})
    try:
        inputs = []
        parents = list(c['arms'].values()) + [c[key] for key in ['e0_stage', 'e1_stage', 'e3b_reference_stage', 'renderer_validation_stage']]
        for parent in parents:
            path = Path(parent); pm = json.loads((path/'manifest.json').read_text()); assert pm['status'] == 'completed'
            for item in pm.get('artifacts', []): assert p.record(item['path']) == item
            inputs.append(p.record(path/'manifest.json'))
        def tracked(path):
            inputs.append(p.record(path)); return path
        validation = json.loads(tracked(Path(c['renderer_validation_stage'])/'evaluation/decision.json').read_text())
        assert validation['ready_for_E3b']
        for path in helpers.values(): tracked(Path(path))
        e0 = Path(c['e0_stage'])
        with np.load(tracked(e0/'artifacts/baseline/observations.npz')) as data:
            original_rgb = data['rgb']; fid = data['frame_id']
        with np.load(tracked(e0/'artifacts/baseline/vggt_omega_raw.npz')) as data:
            k = data['intrinsics'][0].astype(float); e = data['extrinsics'][0].astype(float)
            depth = data['depth'][0, ..., 0].astype(float); confidence = data['depth_conf'][0]
            images = data['images'][0].transpose(0, 2, 3, 1)
        frames_path = tracked(e0/'artifacts/baseline/frames.json'); shutil.copy2(frames_path, s/'artifacts/common/frames.json')
        summaries = {}; shared_by_arm = {}
        for arm, parent in c['arms'].items():
            root = s/'arms'/arm
            for name in ['initial', 'checkpoints', 'maps', 'renders', 'figures', 'evaluation']: (root/name).mkdir(parents=True)
            with np.load(tracked(Path(parent)/'artifacts/maps/fused_map.npz')) as data: fused = {key: data[key] for key in data.files}
            shared, summary = make_shared(fused, original_rgb, fid, k, e, depth, confidence, c['visibility'], g)
            np.savez_compressed(root/'initial/shared_map.npz', **shared)
            with np.load(root/'initial/shared_map.npz') as saved:
                for key in shared: assert np.array_equal(shared[key], saved[key])
            summaries[arm] = summary; shared_by_arm[arm] = shared
        with np.load(tracked(Path(c['e3b_reference_stage'])/'artifacts/initial/shared_map_initial.npz')) as old:
            for key in old.files: assert np.array_equal(shared_by_arm['control_E0b'][key], old[key]), key
        xyz = shared_by_arm['control_E0b']['xyz0']; taus = []
        for cam in e:
            z = (xyz @ cam[:, :3].T + cam[:, 3])[:, 2]
            taus.append(float(np.median(z[z > 0])) * c['soft_depth_temperature_fraction'])
        assert np.allclose(taus, validation['fixed_temperature_by_camera'], rtol=0, atol=1e-15)
        height, width = c['render_hw']; targets = []; masks = []
        for camera in range(3):
            targets.append(cv2.resize(images[camera], (width, height), interpolation=cv2.INTER_AREA))
            path = tracked(Path(c['e1_stage'])/f'artifacts/renders/evaluation_masks_frame_{camera}.npz')
            with np.load(path) as data: masks.append(data['fixed_all_mask'])
        np.savez_compressed(s/'artifacts/common/cameras_targets.npz', intrinsics=k, extrinsics=e,
                            targets=np.stack(targets), e1_masks=np.stack(masks), temperatures=np.asarray(taus))
        summary = {'arms': summaries, 'same_active_policy': True, 'active_indices_arm_specific': True,
                   'E0b_preparation_exactly_reproduces_E3b_initial': True,
                   'temperatures_identical_between_arms': taus, 'gt_read': False}
        p.json_write(s/'evaluation/preparation.json', summary)
        p.json_write(s/'environment_cpu.json', {'project_commit_before_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                     'source_files': [p.record(path) for path in sorted((s/'artifacts/source').iterdir()) if path.is_file()]})
        p.json_write(s/'progress.json', {'events': [{'time': p.stamp(), 'phase': 'prepared', **summary}]})
        (s/'logs/prepare.log').write_text(json.dumps(summary, indent=2)+'\n')
        m.update(phase='prepared', inputs=inputs); p.json_write(s/'manifest.json', m); print(json.dumps(summary, indent=2))
    except Exception:
        m.update(status='failed', error=traceback.format_exc(), ended_at=p.stamp())
        p.json_write(s/'manifest.json', m); raise


if __name__ == '__main__': main()
