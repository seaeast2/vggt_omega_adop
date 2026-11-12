"""Sequential projective depth averaging; no learned optimization or GT."""
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


def project_old(xyz, k, e, height, width):
    camera = xyz @ e[:, :3].T + e[:, 3]
    z = camera[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = (camera @ k.T)[:, :2]/z[:, None]
    valid = ((z > 0) & np.isfinite(uv).all(1) &
             (uv[:, 0] >= -.5) & (uv[:, 0] < width-.5) &
             (uv[:, 1] >= -.5) & (uv[:, 1] < height-.5))
    ids = np.flatnonzero(valid)
    pixels = np.rint(uv[ids]).astype(np.int64)
    return ids, pixels[:, 1]*width+pixels[:, 0], z[ids]


def unproject(flat, depth, k, e, width):
    pixels = np.column_stack([flat % width, flat // width, np.ones(len(flat))])
    camera = (pixels @ np.linalg.inv(k).T)*depth[:, None]
    return (camera-e[:, 3]) @ np.linalg.inv(e[:, :3]).T


def fuse_step(xyz, owner, uv, target_xyz, target_depth, target_id, k, e):
    height, width = target_depth.shape
    old_ids, flat, z = project_old(xyz, k, e, height, width)
    good = np.isfinite(target_depth.ravel()[flat]) & (target_depth.ravel()[flat] > 0)
    old_ids, flat, z = old_ids[good], flat[good], z[good]
    count = np.bincount(flat, minlength=height*width)
    zsum = np.bincount(flat, weights=z, minlength=height*width)
    mean_z = (target_depth.ravel()+zsum)/(1+count)
    touched = np.flatnonzero(count)
    new_xyz = target_xyz.copy()
    new_xyz[touched] = unproject(touched, mean_z[touched], k, e, width)
    keep = np.ones(len(xyz), bool)
    keep[old_ids] = False
    n_keep = int(keep.sum())
    old_to_new = np.empty(len(xyz), np.int64)
    old_to_new[keep] = np.arange(n_keep)
    old_to_new[old_ids] = n_keep+flat
    grid = np.indices((height, width))[::-1].reshape(2, -1).T.astype(np.int32)
    result = {'xyz': np.vstack([xyz[keep], new_xyz]),
              'owner': np.r_[owner[keep], np.full(height*width, target_id, np.int16)],
              'uv': np.vstack([uv[keep], grid]), 'old_to_new': old_to_new,
              'old_removed': ~keep, 'target_old_point_count': count.reshape(height, width),
              'target_mean_z': mean_z.reshape(height, width)}
    # Independently verify the actual new points project onto the specified target ray.
    camera = new_xyz[touched] @ e[:, :3].T+e[:, 3]
    projected = (camera @ k.T)[:, :2]/camera[:, 2, None]
    assert np.max(np.abs(projected-grid[touched]), initial=0) < 1e-7
    assert np.max(np.abs(camera[:, 2]-mean_z[touched]), initial=0) < 1e-9
    assert np.array_equal(result['xyz'][:n_keep], xyz[keep])
    assert np.array_equal(new_xyz[count == 0], target_xyz[count == 0])
    assert len(result['xyz']) == len(xyz)+height*width-len(old_ids)
    result['metrics'] = {'target_camera': target_id, 'old_representatives': len(xyz),
                         'removed_old_representatives': len(old_ids),
                         'kept_old_representatives': n_keep, 'touched_target_pixels': len(touched),
                         'new_target_points': height*width, 'output_points': len(result['xyz']),
                         'max_old_points_per_target_pixel': int(count.max(initial=0)),
                         'changed_target_depth_mean_abs': float(np.abs(mean_z[touched]-target_depth.ravel()[touched]).mean()) if len(touched) else 0.,
                         'target_xyz_displacement_max': float(np.linalg.norm(new_xyz-target_xyz, axis=1).max())}
    return result


def controlled_checks():
    k = np.eye(3); e = np.c_[np.eye(3), np.zeros(3)]
    grid = np.indices((2, 2))[::-1].reshape(2, -1).T
    old = np.array([[0., 0., 2.], [0., 0., 4.], [20., 0., 2.]])
    target = unproject(np.arange(4), np.full(4, 6.), k, e, 2)
    out = fuse_step(old, np.zeros(3, np.int16), np.zeros((3, 2), np.int32), target, np.full((2, 2), 6.), 1, k, e)
    assert len(out['xyz']) == 5
    assert np.array_equal(out['old_to_new'], [1, 1, 0])
    assert np.array_equal(out['xyz'][0], old[2])
    assert np.array_equal(out['xyz'][1], [0, 0, 4])  # (2+4+6)/3
    target2 = unproject(np.arange(4), np.full(4, 8.), k, e, 2)
    again = fuse_step(out['xyz'], out['owner'], out['uv'], target2, np.full((2, 2), 8.), 2, k, e)
    assert np.array_equal(again['xyz'][1], [0, 0, 6])  # (representative 4+new 8)/2
    assert np.array_equal(grid, [[0, 0], [1, 0], [0, 1], [1, 1]])
    return {'camera_z_mean_known_values': True, 'old_point_removal_mapping': True,
            'unprojected_old_point_preserved': True, 'historical_count_not_used': True}


def membership(source_to_map, fid, size, palette):
    counts = np.bincount(source_to_map, minlength=size)
    assert (counts > 0).all()
    bits = np.zeros(size, np.uint8)
    np.bitwise_or.at(bits, source_to_map, (1 << fid).astype(np.uint8))
    members = ((bits[:, None] >> np.arange(3)) & 1).astype(bool)
    mix = np.rint(members.astype(float) @ palette / members.sum(1)[:, None]).astype(np.uint8)
    return counts, bits, members.sum(1), mix


def ply_write(path, xyz, rgb, owner, uv, counts, bits):
    dtype = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'),
                      ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
                      ('frame_id', '<i2'), ('u', '<i4'), ('v', '<i4'),
                      ('n_observed', '<u4'), ('source_mask', 'u1')])
    records = np.empty(len(xyz), dtype=dtype)
    for axis, key in enumerate(['x', 'y', 'z']): records[key] = xyz[:, axis]
    for axis, key in enumerate(['red', 'green', 'blue']): records[key] = rgb[:, axis]
    records['frame_id'] = owner; records['u'], records['v'] = uv[:, 0], uv[:, 1]
    records['n_observed'], records['source_mask'] = counts, bits
    header = ('ply\nformat binary_little_endian 1.0\n'
              'comment E0b fused; frame_id is latest owner; source_mask is original-source membership\n'
              f'element vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\n'
              'property uchar red\nproperty uchar green\nproperty uchar blue\n'
              'property short frame_id\nproperty int u\nproperty int v\n'
              'property uint n_observed\nproperty uchar source_mask\nend_header\n')
    with Path(path).open('xb') as stream:
        stream.write(header.encode()); records.tofile(stream)
    with Path(path).open('rb') as stream:
        while stream.readline() != b'end_header\n': pass
        assert np.array_equal(np.fromfile(stream, dtype=dtype), records)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); args = parser.parse_args()
    source = Path('experiments/pointmap_refinement/E0b')
    config = json.loads((source/'config.json').read_text())
    stage = Path('results/pointmap_refinement')/args.run_id/'stages/E0b'
    stage.mkdir(parents=True, exist_ok=False)
    for sub in ['artifacts/maps', 'artifacts/steps', 'artifacts/projections', 'artifacts/figures', 'artifacts/source', 'logs', 'evaluation']:
        (stage/sub).mkdir(parents=True)
    for name in ['run.py', 'config.json', 'README.md']: shutil.copy2(source/name, stage/'artifacts/source'/name)
    helper = Path('experiments/pointmap_refinement/E0a/run.py')
    shutil.copy2(helper, stage/'artifacts/source/e0a_projection.py')
    spec = importlib.util.spec_from_file_location('projection', stage/'artifacts/source/e0a_projection.py')
    p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
    timer = time.perf_counter()
    manifest = {'experiment_code': 'E0b', 'run_id': args.run_id, 'status': 'running', 'started_at': p.stamp()}
    p.json_write(stage/'manifest.json', manifest)

    def log(message):
        print(message, flush=True)
        with (stage/'logs/run.log').open('a') as f: f.write(message+'\n')

    def progress(message):
        with (stage/'progress.md').open('a') as f: f.write(f'- {p.stamp()} {message}\n')

    try:
        p.json_write(stage/'config_resolved.json', config | {'run_id': args.run_id})
        parent = Path(config['parent_stage']); comparison = Path(config['comparison_stage'])
        inputs = []
        for parent_stage in [parent, comparison]:
            m = json.loads((parent_stage/'manifest.json').read_text()); assert m['status'] == 'completed'
            for item in m.get('artifacts', []): assert p.record(item['path']) == item
            inputs.append(p.record(parent_stage/'manifest.json'))
        paths = [parent/'artifacts/baseline'/name for name in ['vggt_omega_raw.npz', 'observations.npz', 'frames.json']]
        paths += [comparison/f'artifacts/projections/camera_{i:02d}_all.png' for i in range(3)]
        inputs += [p.record(path) for path in paths] + [p.record(helper)]
        with np.load(paths[0]) as data:
            depth = data['depth'][0, ..., 0].astype(float); k = data['intrinsics'][0].astype(float); e = data['extrinsics'][0].astype(float)
            reference = np.rint(data['images'][0].transpose(0, 2, 3, 1)*255).clip(0, 255).astype(np.uint8)
        with np.load(paths[1]) as data: raw_xyz = data['world_xyz_initial']; fid = data['frame_id']; raw_uv = data['pixel_uv']
        frames = json.loads(paths[2].read_text()); palette = np.asarray(config['palette_rgb'], np.uint8)
        n, height, width = depth.shape; frame_size = height*width
        assert config['frame_order'] == [0, 1, 2] and n == 3 and len(raw_xyz) == 3*frame_size
        assert np.array_equal(fid, np.repeat(np.arange(n), frame_size))
        grid = np.indices((height, width))[::-1].reshape(2, -1).T.astype(np.int32)
        for i in range(n): assert np.array_equal(raw_uv[fid == i], grid)
        controls = controlled_checks()
        progress('부모 산출물 해시·원본 관측 순서·제어 예제 검증 완료. CPU 순차 융합 시작.')
        xyz = raw_xyz[fid == 0].copy(); owner = fid[fid == 0].copy(); uv = grid.copy()
        source_to_map = np.full(len(raw_xyz), -1, np.int64)
        source_to_map[fid == 0] = np.arange(frame_size)
        step_rows = []
        for j in [1, 2]:
            out = fuse_step(xyz, owner, uv, raw_xyz[fid == j], depth[j], j, k[j], e[j])
            old_sources = fid < j
            source_to_map[old_sources] = out['old_to_new'][source_to_map[old_sources]]
            source_to_map[fid == j] = out['metrics']['kept_old_representatives']+np.arange(frame_size)
            xyz, owner, uv = out['xyz'], out['owner'], out['uv']
            seen = fid <= j
            counts, bits, distinct, mix = membership(source_to_map[seen], fid[seen], len(xyz), palette)
            assert int(counts.sum()) == (j+1)*frame_size
            payload = {key: out[key] for key in ['old_to_new', 'old_removed', 'target_old_point_count', 'target_mean_z']}
            payload.update(xyz=xyz, owner_frame_id=owner, owner_pixel_uv=uv, source_to_current=source_to_map,
                           n_observed=counts, source_frame_mask=bits, source_frame_count=distinct)
            np.savez_compressed(stage/f'artifacts/steps/after_frame_{j:02d}.npz', **payload)
            ply_write(stage/f'artifacts/steps/after_frame_{j:02d}_owner.ply', xyz, palette[owner], owner, uv, counts, bits)
            step_rows.append(out['metrics']); log(json.dumps(out['metrics']))
            progress(f'Frame {j}: 이전 대표점 {out["metrics"]["removed_old_representatives"]}개 치환, 현재 {len(xyz)}점. 관측 출처 보존.')

        counts, bits, distinct, mix = membership(source_to_map, fid, len(xyz), palette)
        order = np.argsort(source_to_map, kind='stable'); offsets = np.r_[0, np.cumsum(counts)]
        assert np.array_equal(np.sort(order), np.arange(len(raw_xyz)))
        assert np.array_equal(source_to_map[order], np.repeat(np.arange(len(xyz)), counts))
        assert np.all(np.take_along_axis(((bits[:, None] >> np.arange(3)) & 1), owner[:, None], axis=1))
        final_path = stage/'artifacts/maps/fused_map.npz'
        np.savez_compressed(final_path, xyz=xyz, owner_frame_id=owner, owner_pixel_uv=uv,
                            n_observed=counts, source_frame_mask=bits, source_frame_count=distinct,
                            source_to_fused=source_to_map, obs_offsets=offsets, obs_indices=order,
                            owner_colors_rgb=palette[owner], source_mix_rgb=mix)
        with np.load(final_path) as saved:
            for name, expected in [('xyz', xyz), ('source_to_fused', source_to_map), ('obs_offsets', offsets), ('obs_indices', order)]:
                assert np.array_equal(saved[name], expected)
        ply_write(stage/'artifacts/maps/fused_owner_colors.ply', xyz, palette[owner], owner, uv, counts, bits)
        ply_write(stage/'artifacts/maps/fused_source_mix.ply', xyz, mix, owner, uv, counts, bits)
        owner_obs_id = owner.astype(np.int64)*frame_size+uv[:, 1]*width+uv[:, 0]
        source_owner_xyz = raw_xyz[owner_obs_id]
        owner_displacement = np.linalg.norm(xyz-source_owner_xyz, axis=1)
        view_rows, cells = [], []
        for camera in range(3):
            z, win, _ = p.front(xyz, np.arange(len(xyz)), k[camera], e[camera], height, width)
            hit = win >= 0
            rgb = np.zeros((height, width, 3), np.uint8); blended = rgb.copy()
            rgb[hit] = palette[owner[win[hit]]]; blended[hit] = mix[win[hit]]
            p.image_write(stage/f'artifacts/projections/camera_{camera:02d}_owner.png', rgb)
            p.image_write(stage/f'artifacts/projections/camera_{camera:02d}_source_mix.png', blended)
            np.savez_compressed(stage/f'artifacts/projections/camera_{camera:02d}_buffers.npz',
                                front_z=z, winner_fused_point_id=win, covered=hit,
                                owner_frame_id=np.where(hit, owner[np.maximum(win, 0)], -1))
            before = cv2.imread(str(paths[3+camera]))[..., ::-1]
            cells.append([reference[camera], before, rgb, blended])
            view_rows.append({'camera': camera, 'before_covered_pixels': frame_size,
                              'after_covered_pixels': int(hit.sum()), 'total_pixels': frame_size,
                              'front_owner_counts': [int(np.sum(hit & (owner[np.maximum(win, 0)] == i))) for i in range(3)]})
        p.panel(stage/'artifacts/figures/comparison.png', cells,
                ['Reference RGB', 'E0: original source colors', 'E0b: latest owner colors', 'E0b: original source mix'], frames, height, width)
        verification = {'status': 'passed', 'controlled_checks': controls,
                        'new_points_follow_target_pixel_and_mean_z': True,
                        'unassociated_old_and_target_points_exactly_unchanged': True,
                        'removed_old_to_new_mapping': True, 'all_original_observations_in_one_CSR_group': True,
                        'ply_and_npz_reload': True, 'png_lossless_reload': True, 'parents_unchanged': True}
        for item in inputs: assert p.record(item['path']) == item
        metrics = {'input_observations': len(raw_xyz), 'final_points': len(xyz),
                   'point_reduction_fraction': 1-len(xyz)/len(raw_xyz),
                   'steps': step_rows, 'final_owner_counts': [int((owner == i).sum()) for i in range(3)],
                   'distinct_source_frame_histogram': {str(i): int((distinct == i).sum()) for i in [1, 2, 3]},
                   'original_observation_count': int(counts.sum()), 'max_observations_per_group': int(counts.max()),
                   'owner_displacement_model_units': {'mean': float(owner_displacement.mean()), 'max': float(owner_displacement.max()), 'moved_over_1e_8': int((owner_displacement > 1e-8).sum())},
                   'camera_projections': view_rows, 'wall_roi_or_gt_accuracy_evaluated': False,
                   'cpu_seconds': time.perf_counter()-timer,
                   'limitations': 'Same-pixel association can fuse different surfaces; order-dependent; fewer points/latest-owner color is by construction, not accuracy evidence.'}
        p.json_write(stage/'evaluation/metrics.json', metrics); p.json_write(stage/'evaluation/verification.json', verification)
        p.json_write(stage/'environment.json', {'python': platform.python_version(), 'numpy': np.__version__,
                     'opencv': cv2.__version__, 'platform': platform.platform(), 'execution_context': 'host CPU; GPU unused',
                     'project_commit_before_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                     'source_files': [p.record(file) for file in sorted((stage/'artifacts/source').glob('*')) if file.is_file()]})
        progress('최종 owner/출처 혼합색 PLY·CSR NPZ·카메라별 전후 투영 저장 및 재로딩 검증 완료. GT 정확도는 미평가.')
        manifest.update(status='completed', ended_at=p.stamp(), completion_criteria_met=True, inputs=inputs)
        manifest['artifacts'] = [p.record(file) for file in sorted(stage.rglob('*'))
                                 if file.is_file() and file.name != 'manifest.json' and '__pycache__' not in file.parts]
        p.json_write(stage/'manifest.json', manifest)
        print(json.dumps({'stage': str(stage), 'metrics': metrics}, ensure_ascii=False))
    except Exception:
        log(traceback.format_exc()); manifest.update(status='failed', error=traceback.format_exc(), ended_at=p.stamp())
        p.json_write(stage/'manifest.json', manifest); raise


if __name__ == '__main__':
    main()
