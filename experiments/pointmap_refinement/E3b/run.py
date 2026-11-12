"""Evaluate frozen E0b and E3 outputs with one inherited depth scale and mask."""
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


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def errors(prediction, gt, mask, scale):
    err = prediction[mask]*scale-gt[mask]
    rel = np.abs(err)/gt[mask]
    return {'pixels': int(mask.sum()), 'squared_error_sum_m2': float(np.sum(err**2)),
            'absrel_sum': float(rel.sum()), 'rmse_m': float(np.sqrt(np.mean(err**2))),
            'absrel': float(rel.mean()), 'median_abs_error_m': float(np.median(np.abs(err)))}


def pooled(rows):
    total = sum(row['pixels'] for row in rows)
    return {'pixels': total,
            'rmse_m': float(np.sqrt(sum(row['squared_error_sum_m2'] for row in rows)/total)),
            'absrel': float(sum(row['absrel_sum'] for row in rows)/total)}


def export_ply(path, xyz, rgb, owner, n_observed, bits):
    dtype = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'),
                      ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
                      ('owner', '<i2'), ('n_observed', '<u4'), ('source_mask', 'u1')])
    records = np.empty(len(xyz), dtype=dtype)
    for axis, key in enumerate(['x', 'y', 'z']): records[key] = xyz[:, axis]
    for axis, key in enumerate(['red', 'green', 'blue']): records[key] = rgb[:, axis]
    records['owner'], records['n_observed'], records['source_mask'] = owner, n_observed, bits
    header = ('ply\nformat binary_little_endian 1.0\n'
              'comment E3b comparison; coordinates unchanged; owner policies differ by method\n'
              f'element vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\n'
              'property uchar red\nproperty uchar green\nproperty uchar blue\n'
              'property short owner\nproperty uint n_observed\nproperty uchar source_mask\nend_header\n')
    with Path(path).open('xb') as stream:
        stream.write(header.encode()); records.tofile(stream)
    with Path(path).open('rb') as stream:
        while stream.readline() != b'end_header\n': pass
        assert np.array_equal(np.fromfile(stream, dtype=dtype), records)


def colorize(values, valid, low, high):
    normalized = np.zeros(values.shape, np.uint8)
    normalized[valid] = np.rint(((values[valid]-low)/max(high-low, 1e-12)).clip(0, 1)*255).astype(np.uint8)
    rgb = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)[..., ::-1]
    rgb[~valid] = 0
    return rgb


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); args = parser.parse_args()
    source = Path('experiments/pointmap_refinement/E3b')
    config = json.loads((source/'config.json').read_text())
    stage = Path('results/pointmap_refinement')/args.run_id/'stages/E3b'
    stage.mkdir(parents=True, exist_ok=False)
    for directory in ['artifacts/maps', 'artifacts/native_depth', 'artifacts/projections', 'artifacts/figures',
                      'artifacts/source', 'evaluation', 'logs']:
        (stage/directory).mkdir(parents=True)
    for name in ['run.py', 'config.json', 'README.md']: shutil.copy2(source/name, stage/'artifacts/source'/name)
    helpers = [('projection', 'experiments/pointmap_refinement/E0a/run.py'),
               ('geometry', 'experiments/pointmap_refinement/E1/geometry.py')]
    for name, path in helpers: shutil.copy2(path, stage/f'artifacts/source/{name}.py')
    p = load_module('projection', stage/'artifacts/source/projection.py')
    g = load_module('geometry', stage/'artifacts/source/geometry.py')
    timer = time.perf_counter()
    manifest = {'experiment_code': 'E3b', 'run_id': args.run_id, 'status': 'running', 'started_at': p.stamp()}
    p.json_write(stage/'manifest.json', manifest)

    def log(message):
        print(message, flush=True)
        with (stage/'logs/run.log').open('a') as stream: stream.write(message+'\n')

    def progress(message):
        with (stage/'progress.md').open('a') as stream: stream.write(f'- {p.stamp()} {message}\n')
        log(message)

    try:
        p.json_write(stage/'config_resolved.json', config | {'run_id': args.run_id})
        parents = {key: Path(config[key+'_stage']) for key in ['e0', 'e0b', 'e3', 'gt']}
        inputs = []
        for parent in parents.values():
            m = json.loads((parent/'manifest.json').read_text()); assert m['status'] == 'completed'
            for item in m.get('artifacts', []): assert p.record(item['path']) == item
            inputs.append(p.record(parent/'manifest.json'))

        def tracked(path):
            path = Path(path); inputs.append(p.record(path)); return path

        for _, path in helpers: tracked(path)
        with np.load(tracked(parents['e0']/'artifacts/baseline/vggt_omega_raw.npz')) as data:
            k = data['intrinsics'][0].astype(float); e = data['extrinsics'][0].astype(float)
            original_depth = data['depth'][0, ..., 0].astype(float)
        with np.load(tracked(parents['e0']/'artifacts/baseline/observations.npz')) as data:
            raw_xyz = data['world_xyz_initial']; fid = data['frame_id']
        frames = json.loads(tracked(parents['e0']/'artifacts/baseline/frames.json').read_text())
        methods = {'E0': {'xyz': raw_xyz, 'owner': fid, 'source_to_map': np.arange(len(fid))}}
        with np.load(tracked(parents['e0b']/'artifacts/maps/fused_map.npz')) as data:
            methods['E0b'] = {'xyz': data['xyz'], 'owner': data['owner_frame_id'],
                              'source_to_map': data['source_to_fused'], 'saved_bits': data['source_frame_mask'],
                              'saved_counts': data['n_observed']}
        for label, filename in [('E3_selected', 'selected'), ('E3_last', 'last')]:
            with np.load(tracked(parents['e3']/f'artifacts/maps/shared_map_{filename}.npz')) as data:
                methods[label] = {'xyz': data['xyz'], 'owner': data['owner_camera'],
                                  'source_to_map': data['source_to_shared'], 'saved_counts': data['n_observed'],
                                  'saved_observed': data['observed_camera_mask']}
                if label == 'E3_selected': assert np.array_equal(data['xyz'], data['xyz0'])
        training = json.loads(tracked(parents['e3']/'evaluation/training.json').read_text())
        assert training['selected_step'] == 0 and training['steps'] == 200
        assert np.array_equal(methods['E3_selected']['source_to_map'], methods['E3_last']['source_to_map'])
        assert list(methods) == config['methods']
        palette = np.asarray(config['palette_rgb'], np.uint8)
        structural = []
        for label, method in methods.items():
            xyz, owner, source_to_map = method['xyz'], method['owner'], method['source_to_map']
            size = len(xyz)
            assert np.isfinite(xyz).all() and source_to_map.shape == fid.shape
            assert source_to_map.min() >= 0 and source_to_map.max() < size
            counts = np.bincount(source_to_map, minlength=size); assert (counts > 0).all()
            bits = np.zeros(size, np.uint8); np.bitwise_or.at(bits, source_to_map, (1 << fid).astype(np.uint8))
            observed = ((bits[:, None] >> np.arange(3)) & 1).astype(bool)
            assert observed[np.arange(size), owner].all()
            if 'saved_counts' in method: assert np.array_equal(counts, method['saved_counts'])
            if 'saved_bits' in method: assert np.array_equal(bits, method['saved_bits'])
            if 'saved_observed' in method: assert np.array_equal(observed, method['saved_observed'])
            mix = np.rint(observed.astype(float) @ palette/observed.sum(1)[:, None]).astype(np.uint8)
            method.update(counts=counts, bits=bits, observed=observed, mix=mix)
            structural.append({'method': label, 'points': size, 'original_observations': int(counts.sum()),
                               'distinct_source_histogram': {str(i): int((observed.sum(1) == i).sum()) for i in [1, 2, 3]}})
            if label != 'E0':
                for mode, colors in [('source_mix', mix), ('owner', palette[owner])]:
                    export_ply(stage/f'artifacts/maps/{label}_{mode}.ply', xyz, colors, owner, counts, bits)
        moved_last = int((np.linalg.norm(methods['E3_last']['xyz']-methods['E3_selected']['xyz'], axis=1) > 1e-8).sum())
        progress(f'부모 해시·출처 매핑 검증 완료. E3 selected=step 0, last 이동점 {moved_last}개 확인.')

        scale_record = json.loads(tracked(parents['e3']/'evaluation/gt_depth.json').read_text())
        scale = scale_record['scale_gt_m_per_model_unit']
        gt, fixed, historical_common = [], [], []
        for camera in range(3):
            with np.load(tracked(parents['gt']/f'artifacts/gt/aligned_{camera}.npz')) as data: gt.append(data['depth_m'].astype(float))
            with np.load(tracked(parents['e3']/f'artifacts/renders/native_depth_initial_{camera}.npz')) as data:
                fixed.append(data['fixed_gt_mask']); historical_common.append(data['common_gt_mask'])
        n, height, width = original_depth.shape
        assert n == 3 and all(d.shape == (height, width) for d in gt)
        native = {}; visual = {}; owner_visual = {}
        for label, method in methods.items():
            maps, mix_images, owner_images = [], [], []
            for camera in range(3):
                z, _, _ = g.front_map(method['xyz'], k[camera], e[camera], height, width)
                maps.append(z)
                if label.startswith('E3_'):
                    suffix = 'selected' if label == 'E3_selected' else 'last'
                    with np.load(tracked(parents['e3']/f'artifacts/renders/native_depth_{suffix}_{camera}.npz')) as cached:
                        assert np.array_equal(z, cached['depth_model'], equal_nan=True)
                        assert np.array_equal(fixed[camera], cached['fixed_gt_mask'])
                _, win, _ = p.front(method['xyz'], np.arange(len(method['xyz'])), k[camera], e[camera], height, width)
                hit = win >= 0
                mix_rgb = np.zeros((height, width, 3), np.uint8); own_rgb = mix_rgb.copy()
                mix_rgb[hit] = method['mix'][win[hit]]; own_rgb[hit] = palette[method['owner'][win[hit]]]
                mix_images.append(mix_rgb); owner_images.append(own_rgb)
                p.image_write(stage/f'artifacts/projections/{label}_camera_{camera:02d}_source_mix.png', mix_rgb)
                p.image_write(stage/f'artifacts/projections/{label}_camera_{camera:02d}_owner.png', own_rgb)
                np.savez_compressed(stage/f'artifacts/projections/{label}_camera_{camera:02d}_color_buffer.npz',
                                    winner_point_id=win, covered=hit, source_bits=np.where(hit, method['bits'][np.maximum(win, 0)], 0))
            native[label] = np.stack(maps); visual[label] = mix_images; owner_visual[label] = owner_images
            progress(f'{label}: 동일 카메라 native front-Z 및 출처/owner 투영·PLY 저장 완료.')

        # Reproduce the previously published E3 scores before changing the common support.
        reproduced = []
        for label, old_label in [('E3_selected', 'selected'), ('E3_last', 'last')]:
            rows = [errors(native[label][i], gt[i], historical_common[i], scale) for i in range(3)]
            score = pooled(rows)
            old = next(row for row in scale_record['rows'] if row['method'] == old_label and row['frame'] == 'pooled')
            assert score['pixels'] == old['common_pixels']
            assert abs(score['rmse_m']-old['rmse_m_common']) < 1e-12
            assert abs(score['absrel']-old['absrel_common']) < 1e-12
            reproduced.append({'method': label, **score})
        control = errors(np.array([3., 2.]), np.array([2., 2.]), np.array([True, False]), 1.)
        assert control['rmse_m'] == 1 and control['absrel'] == .5
        valid = {label: np.isfinite(z) & (z > 0) for label, z in native.items()}
        fixed = np.stack(fixed); gt = np.stack(gt)
        common = fixed.copy()
        for label in methods: common &= valid[label]
        assert common.sum() > 0 and np.all(~common | fixed)
        rows, summaries = [], []
        for label in methods:
            stats = []
            for camera in range(3):
                covered = fixed[camera] & valid[label][camera]
                score = errors(native[label][camera], gt[camera], common[camera], scale); stats.append(score)
                available = errors(native[label][camera], gt[camera], covered, scale)
                row = {'method': label, 'camera': camera, 'fixed_gt_pixels': int(fixed[camera].sum()),
                       'covered_fixed_pixels': int(covered.sum()), 'missing_fixed_pixels': int((fixed[camera] & ~covered).sum()),
                       'coverage_of_fixed': float(covered.sum()/fixed[camera].sum()),
                       'common': score, 'covered_only_not_same_support': available}
                rows.append(row)
                np.savez_compressed(stage/f'artifacts/native_depth/{label}_camera_{camera:02d}.npz',
                                    depth_model=native[label][camera], depth_m=native[label][camera]*scale,
                                    gt_depth_m=gt[camera], fixed_gt_mask=fixed[camera], common_gt_mask=common[camera])
            fixed_covered = fixed & valid[label]
            summaries.append({'method': label, 'points': len(methods[label]['xyz']), **pooled(stats),
                              'fixed_gt_pixels': int(fixed.sum()), 'covered_fixed_pixels': int(fixed_covered.sum()),
                              'missing_fixed_pixels': int((fixed & ~valid[label]).sum()),
                              'coverage_of_fixed': float(fixed_covered.sum()/fixed.sum())})

        display_low, display_high = np.percentile(gt[gt > 0], config['depth_display_gt_percentiles'])
        depth_cells, error_cells, source_cells = [], [], []
        for camera in range(3):
            gt_valid = gt[camera] > 0
            depth_images = [colorize(gt[camera], gt_valid, display_low, display_high)]
            err_images = []
            for label in ['E0b', 'E3_selected', 'E3_last']:
                zz = native[label][camera]*scale
                depth_images.append(colorize(zz, valid[label][camera], display_low, display_high))
                err_images.append(colorize(np.abs(zz-gt[camera]), gt_valid & valid[label][camera], 0., config['error_display_max_m']))
            depth_cells.append(depth_images); error_cells.append(err_images)
            source_cells.append([visual[label][camera] for label in config['methods']])
        p.panel(stage/'artifacts/figures/source_comparison.png', source_cells, config['methods'], frames, height, width)
        p.panel(stage/'artifacts/figures/depth_comparison.png', depth_cells,
                ['GT depth (m)', 'E0b depth', 'E3 selected = step 0', 'E3 last = step 200'], frames, height, width)
        p.panel(stage/'artifacts/figures/error_comparison.png', error_cells,
                ['E0b abs error: 0..0.25m', 'E3 selected abs error', 'E3 last abs error'], frames, height, width)
        p.json_write(stage/'evaluation/gt_depth.json', {'scale_m_per_model_unit': scale,
                     'scale_source': str(parents['e3']/'evaluation/gt_depth.json'), 'refit_per_method': False,
                     'fixed_gt_pixels': int(fixed.sum()), 'common_pixels': int(common.sum()),
                     'common_pixels_by_camera': common.sum((1, 2)).astype(int).tolist(),
                     'summary': summaries, 'per_camera': rows, 'historical_E3_reproduction': reproduced,
                     'limitations': 'Same input-view scale-aligned image depth; intersection support depends on coverage; missing pixels reported separately; no heldout/full 3D/wall ROI claim.'})
        p.json_write(stage/'evaluation/structure.json', {'methods': structural, 'E3_last_moved_over_1e_8': moved_last,
                     'E3_selected_equals_initial': True, 'E3_selected_step': 0, 'E3_last_step': 200,
                     'owner_policy_note': 'E0b latest camera; E3 inherited E2 owner. Source-mix palette, not owner colors, is the common display.'})
        for item in inputs: assert p.record(item['path']) == item
        verification = {'status': 'passed', 'parent_hashes_unchanged': True,
                        'all_source_assignments_counts_and_bits': True, 'E3_selected_is_initial': True,
                        'E3_native_depth_exact_cached_match': True, 'E3_old_GT_scores_reproduced_to_1e_12': True,
                        'known_depth_error_metric_check': True, 'single_inherited_scale_no_refit': True,
                        'one_common_support_all_methods': True, 'all_method_coverage_reported': True,
                        'ply_xyz_rgb_metadata_reload': True, 'png_lossless_reload': True}
        for label in methods:
            for camera in range(3):
                with np.load(stage/f'artifacts/native_depth/{label}_camera_{camera:02d}.npz') as saved:
                    assert np.array_equal(saved['depth_model'], native[label][camera], equal_nan=True)
                    assert np.array_equal(saved['common_gt_mask'], common[camera])
        verification['native_depth_npz_reload'] = True
        p.json_write(stage/'evaluation/verification.json', verification)
        p.json_write(stage/'environment.json', {'python': platform.python_version(), 'numpy': np.__version__,
                     'opencv': cv2.__version__, 'platform': platform.platform(), 'execution_context': 'host CPU; GPU unused',
                     'project_commit_before_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                     'cpu_seconds': time.perf_counter()-timer,
                     'source_files': [p.record(path) for path in sorted((stage/'artifacts/source').glob('*')) if path.is_file()]})
        progress('기존 E3 평가 재현·새 공통 GT 비교·coverage·카메라별 그림·저장 검증 완료. 새 학습은 수행하지 않음.')
        log(json.dumps({'scale': scale, 'common_pixels': int(common.sum()), 'summary': summaries}, ensure_ascii=False))
        manifest.update(status='completed', ended_at=p.stamp(), completion_criteria_met=True, inputs=inputs)
        manifest['artifacts'] = [p.record(path) for path in sorted(stage.rglob('*'))
                                 if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts]
        p.json_write(stage/'manifest.json', manifest)
        log_output = {'stage': str(stage), 'scale': scale, 'common_pixels': int(common.sum()), 'summary': summaries}
        print(json.dumps(log_output, ensure_ascii=False))
    except Exception:
        log(traceback.format_exc()); manifest.update(status='failed', error=traceback.format_exc(), ended_at=p.stamp())
        p.json_write(stage/'manifest.json', manifest); raise


if __name__ == '__main__':
    main()
