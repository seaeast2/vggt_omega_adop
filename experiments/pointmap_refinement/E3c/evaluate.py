"""Post-selection matched depth evaluation, palette PLY export, and sealing."""
import argparse
import json
from pathlib import Path
import platform
import traceback

import cv2
import numpy as np
from prepare import load_module


def write_ply(path, xyz, rgb, owner, counts, bits):
    dtype = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
                      ('owner', '<i2'), ('n_observed', '<u4'), ('source_mask', 'u1')])
    data = np.empty(len(xyz), dtype)
    for axis, name in enumerate(['x', 'y', 'z']): data[name] = xyz[:, axis]
    for axis, name in enumerate(['red', 'green', 'blue']): data[name] = rgb[:, axis]
    data['owner'], data['n_observed'], data['source_mask'] = owner, counts, bits
    header = (f'ply\nformat binary_little_endian 1.0\ncomment E3c matched RGB optimization; diagnostic palette\nelement vertex {len(xyz)}\n'
              'property double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n'
              'property short owner\nproperty uint n_observed\nproperty uchar source_mask\nend_header\n')
    with path.open('xb') as stream: stream.write(header.encode()); data.tofile(stream)
    with path.open('rb') as stream:
        while stream.readline() != b'end_header\n': pass
        assert np.array_equal(np.fromfile(stream, dtype), data)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--stage', type=Path, required=True); args = parser.parse_args(); s = args.stage
    p = load_module('projection', s/'artifacts/source/projection.py'); g = load_module('geometry', s/'artifacts/source/geometry.py')
    c = json.loads((s/'config_resolved.json').read_text()); m = json.loads((s/'manifest.json').read_text())
    assert m['status'] == 'running' and m['phase'] == 'trained'
    try:
        training = json.loads((s/'evaluation/training.json').read_text()); cpu = json.loads((s/'environment_cpu.json').read_text())
        for row in cpu['source_files']: assert p.record(row['path']) == row
        with np.load(s/'artifacts/common/cameras_targets.npz') as data: ks = data['intrinsics']; es = data['extrinsics']
        with np.load(s/'artifacts/common/training_contract.npz') as data: train_masks = data['train_masks']
        native = {}; point_sets = {}; moves = {}; source_images = {}; shared = {}
        frames = json.loads((s/'artifacts/common/frames.json').read_text()); rgb_buffers = {}
        for arm, parent in c['arms'].items():
            root = s/'arms'/arm
            with np.load(root/'initial/shared_map.npz') as data: initial = {key: data[key] for key in data.files}
            shared[arm] = initial; xyz0 = initial['xyz0']; active = np.flatnonzero(initial['active_candidate']); inactive = ~initial['active_candidate']
            with np.load(Path(parent)/'artifacts/maps/fused_map.npz') as fused:
                assert np.array_equal(xyz0, fused['xyz'])
                assert np.array_equal(initial['source_to_shared'], fused['source_to_fused'])
                for key in ['obs_offsets', 'obs_indices', 'n_observed', 'source_frame_mask']: assert np.array_equal(initial[key], fused[key])
            moves[arm] = {}; rgb_buffers[arm] = {}; source_images[arm] = {}
            for state in ['initial', 'selected', 'last']:
                if state == 'initial': xyz = xyz0; delta = np.zeros(len(active))
                else:
                    with np.load(root/f'maps/{state}_positions.npz') as data:
                        xyz = data['xyz']; delta = data['delta']; assert np.array_equal(data['active_indices'], active)
                    expected = xyz0[active] + initial['owner_ray_world'][active]*(initial['owner_ray_distance'][active]*np.expm1(delta))[:, None]
                    assert np.array_equal(xyz[inactive], xyz0[inactive]) and np.allclose(xyz[active], expected, rtol=0, atol=1e-12)
                    assert np.max(np.abs(delta)) <= c['log_ray_delta_bound']+1e-7
                if state == 'selected' and training[arm]['selected_step'] == 0: assert np.array_equal(xyz, xyz0)
                displacement = np.linalg.norm(xyz-xyz0, axis=1)
                moves[arm][state] = {'moved_over_1e_8': int((displacement > 1e-8).sum()), 'active_displacement_model_units': g.stats(displacement[active]),
                                    'points_at_bound': int((np.abs(delta) >= c['log_ray_delta_bound']-1e-6).sum())}
                if state == 'last': assert moves[arm][state]['moved_over_1e_8'] > 0
                payload = initial | {'xyz': xyz, 'log_ray_delta': delta, 'optimized_indices': active}
                np.savez_compressed(root/f'maps/shared_map_{state}.npz', **payload)
                with np.load(root/f'maps/shared_map_{state}.npz') as saved:
                    for key in payload: assert np.array_equal(payload[key], saved[key])
                for mode, colors in [('owner', initial['owner_colors_rgb']), ('source_mix', initial['source_mix_rgb'])]:
                    write_ply(root/f'maps/{state}_{mode}.ply', xyz, colors, initial['owner_camera'], initial['n_observed'], initial['source_frame_mask'])
                key = (arm, state); point_sets[key] = xyz
                native[key] = np.stack([g.front_map(xyz, ks[i], es[i], 384, 512)[0] for i in range(3)])
                source_images[arm][state] = []; rgb_buffers[arm][state] = []
                for camera in range(3):
                    _, win, _ = p.front(xyz, np.arange(len(xyz)), ks[camera], es[camera], 384, 512); hit = win >= 0
                    rgb = np.zeros((384, 512, 3), np.uint8); rgb[hit] = initial['source_mix_rgb'][win[hit]]
                    source_images[arm][state].append(rgb); p.image_write(root/f'renders/{state}_source_camera_{camera}.png', rgb)
                    with np.load(root/f'renders/{state}_frame_{camera}.npz') as data:
                        assert np.array_equal(data['train_mask'], train_masks[camera])
                        with np.load(root/f'renders/initial_frame_{camera}.npz') as initial_render:
                            assert np.array_equal(data['target'], initial_render['target']) and np.array_equal(data['e1_mask'], initial_render['e1_mask'])
                        rgb_buffers[arm][state].append(data['rgb'])
        # First GT/scale access: all checkpoint choices and moved coordinates are already saved.
        gt_inputs = []; scale_path = Path(c['e3b_reference_stage'])/'evaluation/gt_depth.json'
        scale = json.loads(scale_path.read_text())['scale_m_per_model_unit']; gt_inputs.append(p.record(scale_path))
        gt_stage = Path(c['gt_stage']); gm = json.loads((gt_stage/'manifest.json').read_text()); assert gm['status'] == 'completed'
        gt_inputs.append(p.record(gt_stage/'manifest.json')); gt = []
        for camera in range(3):
            path = gt_stage/f'artifacts/gt/aligned_{camera}.npz'
            row = next(row for row in gm['artifacts'] if row['path'] == str(path)); assert p.record(path) == row; gt_inputs.append(row)
            with np.load(path) as data: gt.append(data['depth_m'].astype(float))
        gt = np.stack(gt)
        raw_path = Path(c['e0_stage'])/'artifacts/baseline/observations.npz'
        with np.load(raw_path) as data: raw = data['world_xyz_initial']
        raw_z = np.stack([g.front_map(raw, ks[i], es[i], 384, 512)[0] for i in range(3)])
        fixed = np.isfinite(raw_z) & (raw_z > 0) & np.isfinite(gt) & (gt > 0)
        common = fixed.copy()
        for z in native.values(): common &= np.isfinite(z) & (z > 0)
        assert common.any(); gt_rows = []; per_camera = []
        for (arm, state), z in native.items():
            covered = fixed & np.isfinite(z) & (z > 0); error = z[common]*scale-gt[common]
            row = {'arm': arm, 'state': state, 'common_pixels': int(common.sum()), 'rmse_m': float(np.sqrt(np.mean(error**2))),
                   'absrel': float((np.abs(error)/gt[common]).mean()), 'fixed_pixels': int(fixed.sum()),
                   'covered_fixed_pixels': int(covered.sum()), 'coverage_of_fixed': float(covered.sum()/fixed.sum())}
            gt_rows.append(row)
            for camera in range(3):
                err = z[camera][common[camera]]*scale-gt[camera][common[camera]]
                per_camera.append({'arm': arm, 'state': state, 'camera': camera, 'common_pixels': int(common[camera].sum()),
                                   'rmse_m': float(np.sqrt(np.mean(err**2))), 'absrel': float((np.abs(err)/gt[camera][common[camera]]).mean()),
                                   'covered_fixed_pixels': int(covered[camera].sum()), 'fixed_pixels': int(fixed[camera].sum())})
                np.savez_compressed(s/'arms'/arm/f'renders/native_depth_{state}_{camera}.npz', depth_model=z[camera], gt_depth_m=gt[camera], fixed_gt_mask=fixed[camera], common_gt_mask=common[camera])
        gt_result = {'scale_m_per_model_unit': scale, 'scale_refit': False, 'GT_used_for_training_or_selection': False,
                     'summary': gt_rows, 'per_camera': per_camera,
                     'limitations': 'same input cameras; one prior E0b scale; intersection of all six arm states plus fixed coverage; no heldout/full 3D/wall GT claim'}
        p.json_write(s/'evaluation/gt_depth.json', gt_result); p.json_write(s/'evaluation/displacement.json', moves)
        with np.load(s/'artifacts/common/cameras_targets.npz') as data: targets = data['targets']
        def upscale(rgb): return cv2.resize(np.rint(rgb.clip(0, 1)*255).astype(np.uint8), (512, 384), interpolation=cv2.INTER_NEAREST)
        for arm in c['arms']:
            rgb_cells = []; source_cells = []
            for camera in range(3):
                rgb_cells.append([upscale(targets[camera])] + [upscale(rgb_buffers[arm][state][camera]) for state in ['initial', 'selected', 'last']])
                source_cells.append([source_images[arm][state][camera] for state in ['initial', 'selected', 'last']])
            p.panel(s/'arms'/arm/'figures/rgb_comparison.png', rgb_cells, ['Target RGB (4x display)', 'Initial', f'Selected step {training[arm]["selected_step"]}', 'Last step 200'], frames, 384, 512)
            p.panel(s/'arms'/arm/'figures/source_comparison.png', source_cells, ['Initial source mix', 'Selected source mix', 'Last source mix'], frames, 384, 512)
        paired = []
        for camera in range(3):
            paired.append([upscale(targets[camera])] + [upscale(rgb_buffers[arm][state][camera]) for arm in c['arms'] for state in ['initial', 'selected']])
        p.panel(s/'artifacts/figures/paired_rgb_comparison.png', paired,
                ['Target RGB (4x display)', 'E0b initial', 'E0b optimized selected', 'E0c initial', 'E3c selected'], frames, 384, 512)
        paired_changes = {}
        for arm in c['arms']:
            first = next(row for row in gt_rows if row['arm'] == arm and row['state'] == 'initial')
            selected = next(row for row in gt_rows if row['arm'] == arm and row['state'] == 'selected')
            paired_changes[arm] = {'photo_fraction_reduction': 1-training[arm]['selected_photo_loss']/training[arm]['initial_photo_loss'],
                                   'GT_RMSE_change_m': selected['rmse_m']-first['rmse_m'], 'GT_AbsRel_change': selected['absrel']-first['absrel'],
                                   'fixed_coverage_change': selected['coverage_of_fixed']-first['coverage_of_fixed']}
        p.json_write(s/'evaluation/comparison.json', paired_changes)
        for row in m['inputs'] + gt_inputs: assert p.record(row['path']) == row
        p.json_write(s/'evaluation/verification.json', {'status': 'passed', 'both_initial_XYZ_CSR_exact_parents': True,
                     'original_observation_partition_preserved': True, 'inactive_XYZ_exactly_fixed': True, 'active_XYZ_matches_log_ray_gradient': True,
                     'point_count_colors_cameras_topology_fixed': True, 'same_frozen_train_masks_and_temperatures': True,
                     'both_preflights_passed': True, 'both_formal_200_step_runs_and_nonzero_movement': True,
                     'bounds_PLY_NPZ_PNG_reload': True, 'GT_after_training_selection_only': True, 'scale_reused_without_refit': True,
                     'parent_and_executed_source_hashes_unchanged': True})
        gpu = json.loads((s/'environment_gpu.json').read_text())
        p.json_write(s/'environment.json', {'python': platform.python_version(), 'numpy': np.__version__, 'opencv': cv2.__version__,
                     'platform': platform.platform(), 'CPU_preparation': cpu, 'GPU_training': gpu})
        progress = json.loads((s/'progress.json').read_text()); progress['events'].append({'time': p.stamp(), 'phase': 'evaluated', 'comparison': paired_changes})
        p.json_write(s/'progress.json', progress)
        output = {'training': training, 'movement': moves, 'gt_summary': gt_rows, 'comparison': paired_changes}
        (s/'logs/evaluate.log').write_text(json.dumps(output, indent=2)+'\n')
        m.update(status='completed', phase='evaluated', ended_at=p.stamp(), completion_criteria_met=True, gt_inputs=gt_inputs,
                 effect_scope='report photometric and fixed-scale depth separately; color-gate total treatment includes changed representation and active candidates')
        m['artifacts'] = [p.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts]
        p.json_write(s/'manifest.json', m); print(json.dumps(output, ensure_ascii=False))
    except Exception:
        m.update(status='failed', phase='evaluation', error=traceback.format_exc(), ended_at=p.stamp())
        p.json_write(s/'manifest.json', m); raise


if __name__ == '__main__': main()
