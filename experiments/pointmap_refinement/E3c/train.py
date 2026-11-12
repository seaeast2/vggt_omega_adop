"""Host-GPU matched photometric optimization; never loads GT or fits scale."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import traceback

import numpy as np
import torch
from prepare import load_module


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--stage', type=Path, required=True); args = parser.parse_args(); s = args.stage
    c = json.loads((s/'config_resolved.json').read_text())
    p = load_module('projection', s/'artifacts/source/projection.py')
    renderer = load_module('renderer', s/'artifacts/source/renderer.py')
    m = json.loads((s/'manifest.json').read_text()); assert m['status'] == 'running' and m['phase'] == 'prepared'
    m.update(phase='training'); p.json_write(s/'manifest.json', m)
    def log(value):
        message = json.dumps(value, ensure_ascii=False); print(message, flush=True)
        with (s/'logs/train.log').open('a') as stream: stream.write(message+'\n')
    def event(phase, value):
        progress = json.loads((s/'progress.json').read_text())
        progress['events'].append({'time': p.stamp(), 'phase': phase, **value}); p.json_write(s/'progress.json', progress)
    try:
        torch.manual_seed(c['seed']); torch.cuda.init(); torch.cuda.reset_peak_memory_stats(); start = time.perf_counter()
        with np.load(s/'artifacts/common/cameras_targets.npz') as data:
            ks = data['intrinsics']; es = data['extrinsics']; targets_cpu = data['targets']; e1_masks = data['e1_masks']; taus = data['temperatures']
        shared = {}
        for arm in c['arms']:
            with np.load(s/'arms'/arm/'initial/shared_map.npz') as data: shared[arm] = {key: data[key] for key in data.files}
        height, width = c['render_hw']; sx = width/512; sy = height/384
        affine = np.array([[sx, 0, (sx-1)/2], [0, sy, (sy-1)/2], [0, 0, 1.]])
        def t(value, dtype=torch.float32): return torch.as_tensor(value, device='cuda', dtype=dtype)
        def render(xyz, colors, cameras, camera):
            return renderer.render(xyz, colors, *cameras[camera], height, width, mode='compact_soft',
                                   sigma=c['sigma_pixels'], radius=c['support_radius_pixels'], tau=float(taus[camera]))
        buffers = {}; cameras32 = [(t(affine@k), t(e)) for k, e in zip(ks, es)]
        for arm, data in shared.items():
            buffers[arm] = []
            with torch.no_grad():
                for camera in range(3):
                    rgb, z, alpha = render(t(data['xyz0']), t(data['rgb_fixed']), cameras32, camera)
                    buffers[arm].append({'rgb': rgb.cpu().numpy(), 'depth': z.cpu().numpy(), 'alpha': alpha.cpu().numpy()})
        masks_cpu = e1_masks.copy()
        for arm in c['arms']:
            masks_cpu &= np.stack([row['alpha'] >= .5 for row in buffers[arm]])
        assert masks_cpu.reshape(3, -1).any(1).all()
        np.savez_compressed(s/'artifacts/common/training_contract.npz', train_masks=masks_cpu, e1_masks=e1_masks, temperatures=taus)
        for arm in c['arms']:
            for camera, row in enumerate(buffers[arm]):
                np.savez_compressed(s/'arms'/arm/f'renders/initial_frame_{camera}.npz', **row,
                                    target=targets_cpu[camera], train_mask=masks_cpu[camera], e1_mask=e1_masks[camera])
        def setup(arm, dtype):
            data = shared[arm]; active = np.flatnonzero(data['active_candidate'])
            base = t(data['xyz0'], dtype); colors = t(data['rgb_fixed'], dtype); idx = torch.as_tensor(active, device='cuda')
            rays = t(data['owner_ray_world'][active], dtype); distance = t(data['owner_ray_distance'][active], dtype)
            cameras = [(t(affine@k, dtype), t(e, dtype)) for k, e in zip(ks, es)]
            targets = [t(image, dtype) for image in targets_cpu]; masks = [torch.as_tensor(mask, device='cuda') for mask in masks_cpu]
            def positions(delta): return base.index_copy(0, idx, base[idx] + rays*(distance*torch.expm1(delta))[:, None])
            def image(delta, camera): return render(positions(delta), colors, cameras, camera)
            def loss(delta, camera):
                return torch.sqrt((image(delta, camera)[0]-targets[camera]).square()+c['charbonnier_epsilon']**2)[masks[camera]].mean()/3
            return active, positions, image, loss
        def direction_probe(arm, dtype, epsilons):
            active, _, _, loss = setup(arm, dtype)
            delta = torch.zeros(len(active), device='cuda', dtype=dtype, requires_grad=True); initial = 0.
            for camera in range(3):
                value = loss(delta, camera); value.backward(); initial += float(value.detach())
            gradient = delta.grad.detach(); assert torch.isfinite(gradient).all() and float(gradient.norm()) > 0
            direction = -gradient/(gradient.abs()+1e-8); analytic = float((gradient*direction).sum()); rows = []
            with torch.no_grad():
                for epsilon in epsilons:
                    plus = sum(float(loss(direction*epsilon, i)) for i in range(3))
                    minus = sum(float(loss(-direction*epsilon, i)) for i in range(3)); numeric = (plus-minus)/(2*epsilon)
                    rows.append({'epsilon': epsilon, 'plus_loss': plus, 'minus_loss': minus, 'finite_difference': numeric,
                                 'autograd': analytic, 'relative_error': abs(numeric-analytic)/max(abs(analytic), 1e-12),
                                 'actual_plus_decreases': plus < initial})
            return {'dtype': str(dtype), 'initial_loss': initial, 'gradient_norm': float(gradient.norm()), 'probes': rows}
        def measure(delta, image, loss, step):
            with torch.no_grad():
                total = sum(float(loss(delta, i)) for i in range(3)); frames = []
                for camera in range(3):
                    rgb, _, alpha = image(delta, camera); out = rgb.cpu().numpy(); support = alpha.cpu().numpy() >= .5
                    mse = float(((out-targets_cpu[camera])**2)[e1_masks[camera]].mean())
                    frames.append({'camera': camera, 'psnr_fixed_e1_mask': float(-10*np.log10(max(mse, 1e-20))),
                                   'support_coverage_fixed_train_mask': float(support[masks_cpu[camera]].mean()),
                                   'support_coverage_all': float(support.mean()), 'missing_e1_pixels': int((e1_masks[camera] & ~support).sum())})
                assert np.isfinite(total)
                return {'step': step, 'training_charbonnier': total, 'frames': frames,
                        'delta_abs_max': float(delta.abs().max()), 'points_at_bound': int((delta.abs() >= c['log_ray_delta_bound']-1e-6).sum())}
        def update(delta, optimizer, loss):
            optimizer.zero_grad(set_to_none=True); total = 0.
            for camera in range(3):
                value = loss(delta, camera); value.backward(); total += float(value.detach())
            assert torch.isfinite(delta.grad).all()
            norm = float(delta.grad.norm()); torch.nn.utils.clip_grad_norm_([delta], c['gradient_clip_norm']); optimizer.step()
            with torch.no_grad(): delta.clamp_(-c['log_ray_delta_bound'], c['log_ray_delta_bound'])
            return {'pre_update_photo_loss': total, 'gradient_norm': norm}
        gates = {}
        for arm in c['arms']:
            double = direction_probe(arm, torch.float64, c['fp64_check_epsilons'])
            single = direction_probe(arm, torch.float32, c['fp32_check_epsilons'])
            active, _, image, loss = setup(arm, torch.float32)
            delta = torch.nn.Parameter(torch.zeros(len(active), device='cuda')); optimizer = torch.optim.Adam([delta], lr=c['learning_rate'])
            history = [measure(delta, image, loss, 0)]
            for step in range(1, c['preflight_steps']+1):
                update(delta, optimizer, loss); history.append(measure(delta, image, loss, step))
            np.savez_compressed(s/'arms'/arm/'checkpoints/preflight_last.npz', delta=delta.detach().cpu().numpy(), active_indices=active)
            fp64 = all(abs(row['finite_difference']-row['autograd']) <= c['fp64_direction_absolute_tolerance']+c['fp64_direction_relative_tolerance']*abs(row['autograd']) for row in double['probes'])
            fp32 = all(row['actual_plus_decreases'] for row in single['probes'])
            drop = max(history[0]['frames'][i]['support_coverage_fixed_train_mask']-history[-1]['frames'][i]['support_coverage_fixed_train_mask'] for i in range(3))
            ready = fp64 and fp32 and history[-1]['training_charbonnier'] < history[0]['training_charbonnier'] and drop <= c['max_fixed_mask_support_coverage_drop']
            gate = {'ready_for_full_training': ready, 'float64_direction': double, 'float32_direction': single, 'short_history': history,
                    'fp64_passed': fp64, 'fp32_descent_passed': fp32, 'short_support_drop': drop, 'GT_read': False}
            gates[arm] = gate; p.json_write(s/'arms'/arm/'evaluation/preflight.json', gate)
            log({'arm': arm, 'preflight_passed': ready, 'initial_loss': history[0]['training_charbonnier'], 'short_last_loss': history[-1]['training_charbonnier'], 'support_drop': drop})
            event('preflight', {'arm': arm, 'passed': ready})
        p.json_write(s/'evaluation/preflight.json', gates)
        assert all(row['ready_for_full_training'] for row in gates.values()), 'Preflight gate failed; no formal 200-step training authorized by preregistration'
        results = {}
        for arm, data in shared.items():
            root = s/'arms'/arm; active, positions, image, loss = setup(arm, torch.float32)
            delta = torch.nn.Parameter(torch.zeros(len(active), device='cuda')); optimizer = torch.optim.Adam([delta], lr=c['learning_rate'])
            history = []; steps = []; best = float('inf'); beststep = 0
            def checkpoint(step):
                nonlocal best, beststep
                row = measure(delta, image, loss, step); history.append(row)
                state = optimizer.state_dict()
                cpu_state = {key: {name: value.detach().cpu() if torch.is_tensor(value) else value for name, value in values.items()} for key, values in state['state'].items()}
                torch.save({'step': step, 'delta': delta.detach().cpu(), 'active_indices': torch.as_tensor(active),
                            'optimizer': {'state': cpu_state, 'param_groups': state['param_groups']},
                            'torch_rng': torch.get_rng_state(), 'cuda_rng': torch.cuda.get_rng_state().cpu()}, root/f'checkpoints/step_{step:04d}.pt')
                np.savez_compressed(root/f'checkpoints/step_{step:04d}.npz', delta=delta.detach().cpu().numpy(), active_indices=active)
                if row['training_charbonnier'] < best: best = row['training_charbonnier']; beststep = step
                p.json_write(root/'evaluation/checkpoint_history.json', history); log({'arm': arm, **row})
            checkpoint(0)
            assert abs(history[0]['training_charbonnier']-gates[arm]['short_history'][0]['training_charbonnier']) < 2e-6
            torch.cuda.synchronize(); training_start = time.perf_counter()
            for step in range(1, c['steps']+1):
                steps.append({'step': step, **update(delta, optimizer, loss)})
                if step in c['checkpoint_steps']: checkpoint(step)
            torch.cuda.synchronize(); elapsed = time.perf_counter()-training_start
            assert any(row['gradient_norm'] > 0 for row in steps)
            for label, step in [('selected', beststep), ('last', c['steps'])]:
                with np.load(root/f'checkpoints/step_{step:04d}.npz') as saved: parameter = saved['delta'].astype(float)
                xyz = data['xyz0'].copy()
                xyz[active] += data['owner_ray_world'][active]*(data['owner_ray_distance'][active]*np.expm1(parameter))[:, None]
                np.savez_compressed(root/f'maps/{label}_positions.npz', xyz=xyz, delta=parameter, active_indices=active)
                with torch.no_grad():
                    delta.copy_(t(parameter)); current = positions(delta).cpu().numpy()
                    assert np.isfinite(current).all()
                    for camera in range(3):
                        rgb, z, alpha = image(delta, camera)
                        np.savez_compressed(root/f'renders/{label}_frame_{camera}.npz', rgb=rgb.cpu().numpy(), depth=z.cpu().numpy(), alpha=alpha.cpu().numpy(),
                                            target=targets_cpu[camera], train_mask=masks_cpu[camera], e1_mask=e1_masks[camera])
            result = {'initial_points': len(data['xyz0']), 'active_points': len(active), 'steps': c['steps'], 'selected_step': beststep,
                      'initial_photo_loss': history[0]['training_charbonnier'], 'selected_photo_loss': best,
                      'last_photo_loss': history[-1]['training_charbonnier'], 'optimization_seconds': elapsed,
                      'max_checkpoint_fixed_mask_support_drop': max(1-row['frames'][i]['support_coverage_fixed_train_mask'] for row in history for i in range(3)),
                      'selected_by': 'minimum checkpoint training Charbonnier only', 'GT_read': False}
            results[arm] = result; p.json_write(root/'evaluation/step_log.json', steps); p.json_write(root/'evaluation/training.json', result)
            event('trained_arm', {'arm': arm, **result}); log({'arm_completed': arm, **result})
        p.json_write(s/'evaluation/training.json', results)
        p.json_write(s/'environment_gpu.json', {'torch': torch.__version__, 'cuda_runtime': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0),
                     'driver_snapshot': subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version', '--format=csv,noheader'], text=True).strip(),
                     'execution_context': 'host GPU outside sandbox', 'wall_seconds': time.perf_counter()-start,
                     'peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                     'train_pixels_by_camera': masks_cpu.reshape(3, -1).sum(1).tolist(), 'temperatures': taus.tolist(), 'GT_loaded': False})
        m.update(phase='trained'); p.json_write(s/'manifest.json', m)
    except Exception:
        log({'error': traceback.format_exc()}); m.update(status='failed', error=traceback.format_exc(), ended_at=p.stamp())
        p.json_write(s/'manifest.json', m); raise


if __name__ == '__main__': main()
