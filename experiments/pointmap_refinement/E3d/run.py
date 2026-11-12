"""Fixed-RGB ADOP-style minimal refinement, bounded to one preregistered run."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import traceback

import cv2
import numpy as np
import torch


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result); return result


def ply_write(path, xyz, rgb, owner, counts, bits, code):
    dtype = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
                      ('owner', '<i2'), ('n_observed', '<u4'), ('source_mask', 'u1')]); data = np.empty(len(xyz), dtype)
    for i, name in enumerate(['x', 'y', 'z']): data[name] = xyz[:, i]
    for i, name in enumerate(['red', 'green', 'blue']): data[name] = rgb[:, i]
    data['owner'], data['n_observed'], data['source_mask'] = owner, counts, bits
    head = (f'ply\nformat binary_little_endian 1.0\ncomment {code} fixed-RGB ADOP-style refinement; diagnostic palette\nelement vertex {len(data)}\n'
            'property double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n'
            'property short owner\nproperty uint n_observed\nproperty uchar source_mask\nend_header\n')
    with path.open('xb') as stream: stream.write(head.encode()); data.tofile(stream)
    with path.open('rb') as stream:
        while stream.readline() != b'end_header\n': pass
        assert np.array_equal(np.fromfile(stream, dtype), data)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--config', type=Path, required=True); parser.add_argument('--run-id', required=True); a = parser.parse_args()
    c = json.loads(a.config.read_text()); code = c['experiment_code']; src = Path(__file__).parent
    s = Path('results/pointmap_refinement')/a.run_id/'stages'/code; s.mkdir(parents=True, exist_ok=False)
    for name in ['artifacts/source', 'artifacts/initial', 'artifacts/checkpoints', 'artifacts/maps', 'artifacts/renders', 'artifacts/figures', 'evaluation', 'logs']:
        (s/name).mkdir(parents=True)
    for path in src.iterdir():
        if path.is_file(): shutil.copy2(path, s/'artifacts/source'/path.name)
    for name, path in [('projection.py', 'experiments/pointmap_refinement/E0a/run.py'), ('geometry.py', 'experiments/pointmap_refinement/E1/geometry.py')]:
        shutil.copy2(path, s/'artifacts/source'/name)
    p = module('projection', s/'artifacts/source/projection.py'); g = module('geometry', s/'artifacts/source/geometry.py')
    renderer = module('one_pixel', s/'artifacts/source/renderer.py')
    m = {'status': 'running', 'experiment_code': code, 'run_id': a.run_id, 'started_at': p.stamp()}
    p.json_write(s/'manifest.json', m); p.json_write(s/'config_resolved.json', c | {'run_id': a.run_id})
    def log(value):
        message = json.dumps(value, ensure_ascii=False); print(message, flush=True)
        with (s/'logs/run.log').open('a') as stream: stream.write(message+'\n')
    def event(phase, value):
        with (s/'progress.md').open('a') as stream: stream.write(f'- {p.stamp()} {phase}: {json.dumps(value, ensure_ascii=False)}\n')
    try:
        start = time.perf_counter(); inputs = []; parent = Path(c['parent_stage'])
        pm = json.loads((parent/'manifest.json').read_text()); assert pm['status'] == 'completed'
        for row in pm['artifacts']: assert p.record(row['path']) == row
        inputs.append(p.record(parent/'manifest.json'))
        def tracked(path): inputs.append(p.record(path)); return path
        with np.load(tracked(parent/c['initial_map'])) as data: initial = {key: data[key] for key in data.files}
        with np.load(tracked(parent/c['cameras_targets'])) as data:
            ks = data['intrinsics']; es = data['extrinsics']; targets_cpu = data['targets']
        with np.load(tracked(parent/c['training_contract'])) as data: masks_cpu = data['train_masks']
        with np.load(tracked(Path(c['e0_stage'])/'artifacts/baseline/vggt_omega_raw.npz')) as data:
            native_targets = data['images'][0].transpose(0, 2, 3, 1)
        frames_path = tracked(Path(c['e0_stage'])/'artifacts/baseline/frames.json'); frames = json.loads(frames_path.read_text())
        shutil.copy2(parent/c['initial_map'], s/'artifacts/initial/shared_map.npz')
        np.savez_compressed(s/'artifacts/initial/cameras_targets_masks.npz', intrinsics=ks, extrinsics=es, targets=targets_cpu, targets_native=native_targets, train_masks=masks_cpu)
        assert np.array_equal(np.sort(initial['obs_indices']), np.arange(len(initial['source_to_shared'])))
        assert np.array_equal(initial['source_to_shared'][initial['obs_indices']], np.repeat(np.arange(len(initial['xyz0'])), initial['n_observed']))
        torch.manual_seed(c['seed']); torch.cuda.init(); torch.cuda.reset_peak_memory_stats()
        checks = renderer.controlled_checks('cuda'); p.json_write(s/'evaluation/controlled_checks.json', checks)
        height, width = c['render_hw']; native_h, native_w = native_targets.shape[1:3]
        assert targets_cpu.shape[1:3] == (height, width) and masks_cpu.reshape(3, -1).any(1).all()
        affine = np.array([[width/native_w, 0, (width/native_w-1)/2], [0, height/native_h, (height/native_h-1)/2], [0, 0, 1.]])
        def t(value): return torch.as_tensor(value, device='cuda', dtype=torch.float32)
        xyz0 = initial['xyz0']; active = np.flatnonzero(initial['active_candidate']); inactive = ~initial['active_candidate']
        base = t(xyz0); colors = t(initial['rgb_fixed']); idx = torch.as_tensor(active, device='cuda')
        rays = t(initial['owner_ray_world'][active]); distances = t(initial['owner_ray_distance'][active])
        cameras = [(t(affine@k), t(e)) for k, e in zip(ks, es)]
        targets = [t(x) for x in targets_cpu]; masks = [torch.as_tensor(x, device='cuda') for x in masks_cpu]
        def positions(delta): return base.index_copy(0, idx, base[idx]+rays*(distances*torch.expm1(delta))[:, None])
        def render(delta, camera):
            return renderer.render(positions(delta), colors, *cameras[camera], height, width,
                                   tolerance=c['fuzzy_depth_relative'], border=c['backward_border_margin'])
        def loss(delta, camera):
            return torch.sqrt((render(delta, camera)[0]-targets[camera]).square()+c['charbonnier_epsilon']**2)[masks[camera]].mean()/3
        parameter = torch.zeros(len(active), device='cuda', requires_grad=True); initial_loss = 0.
        for camera in range(3):
            value = loss(parameter, camera); value.backward(); initial_loss += float(value.detach())
        gradient = parameter.grad.detach(); assert torch.isfinite(gradient).all()
        direction = -gradient/(gradient.abs()+1e-8); probes = []
        with torch.no_grad():
            for epsilon in c['real_direction_probe_log_steps']:
                plus = sum(float(loss(direction*epsilon, i)) for i in range(3)); minus = sum(float(loss(-direction*epsilon, i)) for i in range(3))
                probes.append({'epsilon': epsilon, 'plus_loss': plus, 'minus_loss': minus, 'initial_loss': initial_loss,
                               'actual_plus_decreases': plus < initial_loss, 'central_secant': (plus-minus)/(2*epsilon)})
        diagnostic = {'gradient_norm': float(gradient.norm()), 'nonzero_gradient_parameters': int((gradient != 0).sum()),
                      'surrogate_direction_inner_product': float((gradient*direction).sum()), 'probes': probes,
                      'exact_forward_derivative_claimed': False}
        p.json_write(s/'evaluation/real_direction_diagnostic.json', diagnostic); log({'controls_passed': True, 'direction': diagnostic})
        delta = torch.nn.Parameter(torch.zeros(len(active), device='cuda')); optimizer = torch.optim.Adam([delta], lr=c['learning_rate'])
        history = []; steps = []; best = float('inf'); beststep = 0
        def checkpoint(step):
            nonlocal best, beststep
            with torch.no_grad():
                total = 0.; rows = []
                for camera in range(3):
                    image, _, count = render(delta, camera); total += float(torch.sqrt((image-targets[camera]).square()+c['charbonnier_epsilon']**2)[masks[camera]].mean())/3
                    hit = count.cpu().numpy() > 0; out = image.cpu().numpy(); mse = float(((out-targets_cpu[camera])**2)[masks_cpu[camera]].mean())
                    rows.append({'camera': camera, 'psnr_fixed_train_mask': float(-10*np.log10(max(mse, 1e-20))),
                                 'coverage_fixed_train_mask': float(hit[masks_cpu[camera]].mean()), 'coverage_all': float(hit.mean())})
                row = {'step': step, 'photo_loss': total, 'frames': rows, 'delta_abs_max': float(delta.abs().max()),
                       'points_at_bound': int((delta.abs() >= c['log_ray_delta_bound']-1e-6).sum())}
                assert np.isfinite(total); history.append(row)
                np.savez_compressed(s/f'artifacts/checkpoints/step_{step:04d}.npz', delta=delta.cpu().numpy(), active_indices=active)
                state = optimizer.state_dict()
                cpu_state = {key: {name: value.detach().cpu() if torch.is_tensor(value) else value for name, value in values.items()} for key, values in state['state'].items()}
                torch.save({'step': step, 'delta': delta.detach().cpu(), 'optimizer': {'state': cpu_state, 'param_groups': state['param_groups']}, 'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state().cpu()}, s/f'artifacts/checkpoints/step_{step:04d}.pt')
                if total < best: best = total; beststep = step
                p.json_write(s/'evaluation/checkpoint_history.json', history); log(row)
        checkpoint(0); event('training_started', {'points': len(xyz0), 'active': len(active)}); torch.cuda.synchronize(); train_start = time.perf_counter()
        for step in range(1, c['steps']+1):
            optimizer.zero_grad(set_to_none=True); total = 0.
            for camera in range(3):
                value = loss(delta, camera); value.backward(); total += float(value.detach())
            assert torch.isfinite(delta.grad).all(); norm = float(delta.grad.norm())
            torch.nn.utils.clip_grad_norm_([delta], c['gradient_clip_norm']); optimizer.step()
            with torch.no_grad(): delta.clamp_(-c['log_ray_delta_bound'], c['log_ray_delta_bound'])
            steps.append({'step': step, 'pre_update_photo_loss': total, 'surrogate_gradient_norm': norm})
            if step in c['checkpoint_steps']: checkpoint(step)
        torch.cuda.synchronize(); train_seconds = time.perf_counter()-train_start
        p.json_write(s/'evaluation/step_log.json', steps)
        training = {'steps': c['steps'], 'selected_step': beststep, 'initial_photo_loss': history[0]['photo_loss'],
                    'selected_photo_loss': best, 'last_photo_loss': history[-1]['photo_loss'], 'points': len(xyz0), 'active_points': len(active),
                    'optimization_seconds': train_seconds, 'GT_used_for_training_or_selection': False}
        p.json_write(s/'evaluation/training.json', training); event('training_completed', training)
        states = {}; native_depths = {}; moves = {}; rgb_images = {}; native_images = {}; source_images = {}
        for label, step in [('initial', 0), ('selected', beststep), ('last', c['steps'])]:
            with np.load(s/f'artifacts/checkpoints/step_{step:04d}.npz') as data: d = data['delta'].astype(float)
            xyz = xyz0.copy(); xyz[active] += initial['owner_ray_world'][active]*(initial['owner_ray_distance'][active]*np.expm1(d))[:, None]
            assert np.array_equal(xyz[inactive], xyz0[inactive]) and np.max(np.abs(d)) <= c['log_ray_delta_bound']+1e-7
            states[label] = xyz; displacement = np.linalg.norm(xyz-xyz0, axis=1)
            moves[label] = {'moved_over_1e_8': int((displacement > 1e-8).sum()), 'active_displacement': g.stats(displacement[active]),
                            'points_at_bound': int((np.abs(d) >= c['log_ray_delta_bound']-1e-6).sum())}
            payload = initial | {'xyz': xyz, 'log_ray_delta': d, 'optimized_indices': active}
            np.savez_compressed(s/f'artifacts/maps/shared_map_{label}.npz', **payload)
            with np.load(s/f'artifacts/maps/shared_map_{label}.npz') as saved:
                for key in payload: assert np.array_equal(payload[key], saved[key])
            for mode, rgb in [('owner', initial['owner_colors_rgb']), ('source_mix', initial['source_mix_rgb'])]:
                ply_write(s/f'artifacts/maps/{label}_{mode}.ply', xyz, rgb, initial['owner_camera'], initial['n_observed'], initial['source_frame_mask'], code)
            native_depths[label] = []; rgb_images[label] = []; native_images[label] = []; source_images[label] = []
            with torch.no_grad():
                delta.copy_(t(d))
                for camera in range(3):
                    rgb, depth, count = render(delta, camera); out = rgb.cpu().numpy(); rgb_images[label].append(out)
                    np.savez_compressed(s/f'artifacts/renders/{label}_{camera}.npz', rgb=out, depth=depth.cpu().numpy(), count=count.cpu().numpy(), target=targets_cpu[camera], train_mask=masks_cpu[camera])
                    image, _, _ = renderer.render(t(xyz), colors, t(ks[camera]), t(es[camera]), native_h, native_w, tolerance=c['fuzzy_depth_relative'], border=c['backward_border_margin'])
                    native_images[label].append(image.cpu().numpy())
                    native_depths[label].append(g.front_map(xyz, ks[camera], es[camera], native_h, native_w)[0])
                    _, win, _ = p.front(xyz, np.arange(len(xyz)), ks[camera], es[camera], native_h, native_w); hit = win >= 0
                    pal = np.zeros((native_h, native_w, 3), np.uint8); pal[hit] = initial['source_mix_rgb'][win[hit]]; source_images[label].append(pal)
                    p.image_write(s/f'artifacts/renders/{label}_native_rgb_{camera}.png', np.rint(native_images[label][-1].clip(0, 1)*255).astype(np.uint8))
            native_depths[label] = np.stack(native_depths[label])
        p.json_write(s/'evaluation/displacement.json', moves)
        def uint8(image): return np.rint(image.clip(0, 1)*255).astype(np.uint8)
        cells = []; native_cells = []; source_cells = []
        for camera in range(3):
            cells.append([cv2.resize(uint8(image), (native_w, native_h), interpolation=cv2.INTER_NEAREST) for image in [targets_cpu[camera]]+[rgb_images[label][camera] for label in states]])
            native_cells.append([uint8(native_targets[camera])]+[uint8(native_images[label][camera]) for label in states])
            source_cells.append([source_images[label][camera] for label in states])
        titles = ['Target RGB', 'E0c initial', f'{code} selected {beststep}', f'{code} last {c["steps"]}']
        p.panel(s/'artifacts/figures/rgb_comparison.png', cells, titles, frames, native_h, native_w)
        p.panel(s/'artifacts/figures/rgb_native_comparison.png', native_cells, titles, frames, native_h, native_w)
        p.panel(s/'artifacts/figures/source_comparison.png', source_cells, ['Initial source mix', 'Selected source mix', 'Last source mix'], frames, native_h, native_w)
        # GT and metric scale are accessed numerically only after selected is fixed.
        gt_inputs = []; gt_rows = []; gate = c['indoor_improvement_gate']
        scale_path = Path(c['scale_reference_stage'])/'evaluation/gt_depth.json'; scale = json.loads(scale_path.read_text())['scale_m_per_model_unit']; gt_inputs.append(p.record(scale_path))
        gt_stage = Path(c['gt_stage']); gm = json.loads((gt_stage/'manifest.json').read_text()); gt_inputs.append(p.record(gt_stage/'manifest.json')); gt = []
        for camera in range(3):
            path = gt_stage/f'artifacts/gt/aligned_{camera}.npz'; row = next(row for row in gm['artifacts'] if row['path'] == str(path)); assert p.record(path) == row; gt_inputs.append(row)
            with np.load(path) as data: gt.append(data['depth_m'].astype(float))
        gt = np.stack(gt)
        with np.load(tracked(Path(c['e0_stage'])/'artifacts/baseline/observations.npz')) as data: raw_xyz = data['world_xyz_initial']
        raw_z = np.stack([g.front_map(raw_xyz, ks[i], es[i], native_h, native_w)[0] for i in range(3)])
        fixed = (gt > 0) & np.isfinite(gt) & np.isfinite(raw_z) & (raw_z > 0); common = fixed.copy()
        for z in native_depths.values(): common &= np.isfinite(z) & (z > 0)
        for label, z in native_depths.items():
            covered = fixed & np.isfinite(z) & (z > 0); err = z[common]*scale-gt[common]
            gt_rows.append({'state': label, 'common_pixels': int(common.sum()), 'rmse_m': float(np.sqrt(np.mean(err**2))),
                            'absrel': float((np.abs(err)/gt[common]).mean()), 'fixed_pixels': int(fixed.sum()),
                            'covered_fixed_pixels': int(covered.sum()), 'coverage_of_fixed': float(covered.sum()/fixed.sum())})
            np.savez_compressed(s/f'artifacts/renders/native_depth_{label}.npz', depth_model=z, gt_m=gt, fixed_mask=fixed, common_mask=common)
        p.json_write(s/'evaluation/gt_depth.json', {'scale_m_per_model_unit': scale, 'scale_refit': False, 'summary': gt_rows, 'scope': 'same-input native depth; common support plus fixed coverage; no full 3D accuracy claim'})
        first, selected = gt_rows[:2]; photo_gain = 1-best/history[0]['photo_loss']; rmse_gain = 1-selected['rmse_m']/first['rmse_m']
        coverage_drop = first['coverage_of_fixed']-selected['coverage_of_fixed']
        criteria = {'positive_selected_step': beststep > 0, 'photo_reduction': photo_gain >= gate['minimum_photo_fraction_reduction'],
                    'gt_rmse_reduction': rmse_gain >= gate['minimum_gt_rmse_fraction_reduction'], 'absrel_not_increased': selected['absrel'] <= first['absrel'],
                    'fixed_gt_coverage_preserved': coverage_drop <= gate['maximum_fixed_gt_coverage_drop']}
        decision = {'indoor_improved': all(criteria.values()), 'criteria': criteria, 'photo_fraction_reduction': photo_gain,
                    'gt_rmse_fraction_reduction': rmse_gain, 'fixed_gt_coverage_drop': coverage_drop,
                    'next_action': 'continue indoor method validation' if all(criteria.values()) else 'stop indoor tuning; switch to drone samples once original input paths are available',
                    'GT_used_in_checkpoint_selection': False, 'outdoor_improvement_is_hypothesis': True}
        p.json_write(s/'evaluation/decision.json', decision)
        for row in inputs+gt_inputs: assert p.record(row['path']) == row
        source_files = [p.record(path) for path in sorted((s/'artifacts/source').iterdir()) if path.is_file()]
        for path in src.iterdir():
            if path.is_file(): assert path.read_bytes() == (s/'artifacts/source'/path.name).read_bytes()
        p.json_write(s/'evaluation/verification.json', {'status': 'passed', 'controlled_forward_surrogate_and_chain_rule': True,
                     'initial_XYZ_RGB_CSR_active_masks_exact_E3c_E0c_arm': True, 'fixed_colors_cameras_groups_counts': True,
                     'inactive_XYZ_unchanged_and_log_bounds': True, 'PLY_NPZ_PNG_reload': True, 'GT_after_selection_only': True,
                     'fixed_scale_no_refit': True, 'parents_and_source_unchanged': True, 'exact_gradient_not_claimed': True})
        p.json_write(s/'environment.json', {'python': platform.python_version(), 'numpy': np.__version__, 'opencv': cv2.__version__,
                     'torch': torch.__version__, 'cuda_runtime': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0),
                     'driver_snapshot': subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version', '--format=csv,noheader'], text=True).strip(),
                     'execution_context': 'host GPU outside sandbox', 'wall_seconds': time.perf_counter()-start,
                     'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                     'project_commit_before_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), 'source_files': source_files})
        log({'training': training, 'movement': moves, 'gt_summary': gt_rows, 'decision': decision}); event('evaluated', decision)
        m.update(status='completed', ended_at=p.stamp(), completion_criteria_met=True, inputs=inputs, gt_inputs=gt_inputs, indoor_improved=decision['indoor_improved'])
        m['artifacts'] = [p.record(path) for path in sorted(s.rglob('*')) if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts]
        p.json_write(s/'manifest.json', m)
    except Exception:
        log({'error': traceback.format_exc()}); m.update(status='failed', error=traceback.format_exc(), ended_at=p.stamp()); p.json_write(s/'manifest.json', m); raise


if __name__ == '__main__': main()
