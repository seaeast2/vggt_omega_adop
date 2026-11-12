"""CPU frame-color diagnostics: preserve E0 geometry and predicted cameras."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import traceback

import cv2
import numpy as np


DT = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'),
               ('red', 'u1'), ('green', 'u1'), ('blue', 'u1'),
               ('frame_id', '<i2'), ('u', '<i4'), ('v', '<i4')])


def stamp():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def record(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def ply_read(path):
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'end_header\n'):
            line = stream.readline()
            if not line:
                raise ValueError('Missing PLY header terminator')
            header += line
        count = int(next(line.split()[2] for line in header.decode().splitlines()
                         if line.startswith('element vertex ')))
        data = np.fromfile(stream, dtype=DT)
        assert len(data) == count
        return data


def ply_write(path, records):
    header = ('ply\nformat binary_little_endian 1.0\n'
              'comment E0a frame colors only; XYZ unchanged; arbitrary model scale\n'
              f'element vertex {len(records)}\n'
              'property double x\nproperty double y\nproperty double z\n'
              'property uchar red\nproperty uchar green\nproperty uchar blue\n'
              'property short frame_id\nproperty int u\nproperty int v\nend_header\n')
    with Path(path).open('xb') as stream:
        stream.write(header.encode())
        records.tofile(stream)
    assert np.array_equal(ply_read(path), records)


def front(xyz, ids, k, e, height, width):
    camera = xyz @ e[:, :3].T + e[:, 3]
    z = camera[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = (camera @ k.T)[:, :2] / z[:, None]
    valid = ((z > 0) & np.isfinite(uv).all(1) &
             (uv[:, 0] >= -.5) & (uv[:, 0] < width-.5) &
             (uv[:, 1] >= -.5) & (uv[:, 1] < height-.5))
    local = np.flatnonzero(valid)
    xy = np.rint(uv[local]).astype(np.int64)
    flat = xy[:, 1]*width + xy[:, 0]
    order = np.lexsort((ids[local], z[local], flat))
    local, flat = local[order], flat[order]
    first = np.r_[True, flat[1:] != flat[:-1]] if len(flat) else np.zeros(0, bool)
    winners = np.full(height*width, -1, np.int64)
    depths = np.full(height*width, np.inf)
    winners[flat[first]] = ids[local[first]]
    depths[flat[first]] = z[local[first]]
    return depths.reshape(height, width), winners.reshape(height, width), int(valid.sum())


def image_write(path, rgb):
    assert cv2.imwrite(str(path), rgb[..., ::-1])
    assert np.array_equal(cv2.imread(str(path))[..., ::-1], rgb)


def compose(depths, indices, sources, palette):
    local = np.argmin(depths[sources], axis=0)
    source = np.asarray(sources, dtype=np.int16)[local]
    z = np.take_along_axis(depths[sources], local[None], axis=0)[0]
    ids = np.take_along_axis(indices[sources], local[None], axis=0)[0]
    covered = np.isfinite(z)
    source[~covered], ids[~covered] = -1, -1
    rgb = np.zeros((*z.shape, 3), np.uint8)
    rgb[covered] = palette[source[covered]]
    return rgb, source, ids, z, covered


def panel(path, cells, titles, frames, height, width):
    top, label = 40, 34
    canvas = np.full((top+len(cells)*(height+label), len(titles)*width, 3), 245, np.uint8)
    for col, title in enumerate(titles):
        cv2.putText(canvas, title, (col*width+8, 26), cv2.FONT_HERSHEY_SIMPLEX, .6, (15, 15, 15), 1, cv2.LINE_AA)
    for row, images in enumerate(cells):
        y = top+row*(height+label)
        for col, image in enumerate(images):
            cv2.putText(canvas, f'camera {row} | input index {frames[row]["index"]}',
                        (col*width+8, y+23), cv2.FONT_HERSHEY_SIMPLEX, .55, (15, 15, 15), 1, cv2.LINE_AA)
            canvas[y+label:y+label+height, col*width:(col+1)*width] = image
    image_write(path, canvas)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    source_dir = Path('experiments/pointmap_refinement/E0a')
    config = json.loads((source_dir/'config.json').read_text())
    stage = Path('results/pointmap_refinement') / args.run_id / 'stages/E0a'
    stage.mkdir(parents=True, exist_ok=False)
    for directory in ['artifacts/maps', 'artifacts/projections', 'artifacts/figures',
                      'artifacts/source', 'evaluation', 'logs']:
        (stage/directory).mkdir(parents=True)
    timer = time.perf_counter()
    manifest = {'experiment_code': 'E0a', 'run_id': args.run_id, 'status': 'running', 'started_at': stamp()}
    json_write(stage/'manifest.json', manifest)

    def log(message):
        print(message, flush=True)
        with (stage/'logs/run.log').open('a') as stream:
            stream.write(message+'\n')

    def progress(message):
        with (stage/'progress.md').open('a') as stream:
            stream.write(f'- {stamp()} {message}\n')

    try:
        json_write(stage/'config_resolved.json', config | {'run_id': args.run_id})
        for name in ['run.py', 'config.json', 'README.md']:
            shutil.copy2(source_dir/name, stage/'artifacts/source'/name)
        parent = Path(config['parent_stage'])
        parent_manifest = json.loads((parent/'manifest.json').read_text())
        assert parent_manifest['status'] == 'completed'
        for item in parent_manifest.get('artifacts', []):
            assert record(item['path']) == item
        paths = [parent/'artifacts/baseline'/name for name in
                 ['vggt_omega_raw.npz', 'observations.npz', 'frames.json']]
        paths.append(parent/'artifacts/geometry/all_observations.ply')
        inputs = [record(parent/'manifest.json')] + [record(path) for path in paths]
        with np.load(paths[0]) as raw:
            k = raw['intrinsics'][0].astype(float)
            e = raw['extrinsics'][0].astype(float)
            depth = raw['depth'][0, ..., 0]
            reference = np.rint(raw['images'][0].transpose(0, 2, 3, 1)*255).clip(0, 255).astype(np.uint8)
        with np.load(paths[1]) as obs:
            xyz, fid, uv = obs['world_xyz_initial'], obs['frame_id'], obs['pixel_uv']
        frames = json.loads(paths[2].read_text())
        original = ply_read(paths[3])
        assert np.array_equal(np.column_stack([original[a] for a in ['x', 'y', 'z']]), xyz)
        assert np.array_equal(original['frame_id'], fid)
        assert np.array_equal(np.column_stack([original['u'], original['v']]), uv)
        n, height, width = depth.shape
        assert n == 3 and len(xyz) == n*height*width and np.isfinite(xyz).all()
        assert np.array_equal(np.unique(fid), np.arange(n))
        palette = np.asarray(config['palette_rgb'], np.uint8)
        colored = original.copy()
        for channel, name in enumerate(['red', 'green', 'blue']):
            colored[name] = palette[fid, channel]
        ply_write(stage/'artifacts/maps/frame_colored_all.ply', colored)
        for i in range(n):
            ply_write(stage/f'artifacts/maps/frame_{i:02d}_colored.ply', colored[fid == i])
        json_write(stage/'artifacts/cameras.json', [
            {'camera': i, 'input': frames[i], 'color_rgb': palette[i].tolist(),
             'intrinsics': k[i].tolist(), 'camera_from_world': e[i].tolist(),
             'center_world': (-e[i, :, :3].T @ e[i, :, 3]).tolist(),
             'world_forward_axis': e[i, 2, :3].tolist()} for i in range(n)])
        progress('부모 해시·원본 PLY 대조 및 프레임 색상 PLY 저장·재로딩 완료. XYZ/출처 보존.')
        log(f'{len(xyz)} observations; palette={palette.tolist()}; native={width}x{height}')
        test_z, test_id, _ = front(np.array([[0., 0., 2.], [0., 0., 1.], [0., 0., -1.]]),
                                   np.array([10, 11, 12]), np.eye(3), np.c_[np.eye(3), np.zeros(3)], 2, 2)
        assert test_z[0, 0] == 1 and test_id[0, 0] == 11 and np.isfinite(test_z).sum() == 1
        ids_all = np.arange(len(xyz), dtype=np.int64)
        rows, overview, sources_panel, self_checks = [], [], [], []
        for camera in range(n):
            ds, ids, counts = [], [], []
            for source in range(n):
                select = fid == source
                zz, ii, count = front(xyz[select], ids_all[select], k[camera], e[camera], height, width)
                ds.append(zz); ids.append(ii); counts.append(count)
            ds, ids = np.stack(ds), np.stack(ids)
            own = ids[camera]
            assert (own >= 0).all()
            assert np.array_equal(uv[own][..., 0], np.indices((height, width))[1])
            assert np.array_equal(uv[own][..., 1], np.indices((height, width))[0])
            own_error = float(np.max(np.abs(ds[camera]-depth[camera])))
            assert own_error < 1e-5
            self_checks.append({'camera': camera, 'full_own_coverage': True,
                                'own_pixel_indices_exact': True, 'max_own_depth_error': own_error})
            rgb, winner, point_id, z, covered = compose(ds, ids, list(range(n)), palette)
            crgb, cwinner, cids, cz, ccovered = compose(ds, ids, [i for i in range(n) if i != camera], palette)
            has = np.isfinite(ds)
            near = has & (ds <= z[None]*(1+config['near_front_relative_threshold']))
            bits = np.sum(near.astype(np.uint8)*(1 << np.arange(n, dtype=np.uint8))[:, None, None], axis=0).astype(np.uint8)
            support = near.sum(0)
            mix = np.einsum('shw,sc->hwc', near.astype(float), palette.astype(float))
            mix = np.rint(mix/np.maximum(support, 1)[..., None]).astype(np.uint8)
            source_rgb = np.zeros((n, height, width, 3), np.uint8)
            for source in range(n):
                source_rgb[source, has[source]] = palette[source]
                image_write(stage/f'artifacts/projections/camera_{camera:02d}_source_{source:02d}.png', source_rgb[source])
            for name, image in [('all', rgb), ('cross', crgb), ('near_front_support', mix)]:
                image_write(stage/f'artifacts/projections/camera_{camera:02d}_{name}.png', image)
            buffer_path = stage/f'artifacts/projections/camera_{camera:02d}_buffers.npz'
            np.savez_compressed(buffer_path, source_front_z=ds, source_winner_observation_id=ids,
                                winner_frame_id=winner, winner_observation_id=point_id, front_z=z,
                                covered=covered, cross_winner_frame_id=cwinner,
                                cross_winner_observation_id=cids, cross_front_z=cz,
                                cross_covered=ccovered, near_front_source_bits=bits,
                                near_front_source_count=support, intrinsics=k[camera], extrinsics=e[camera])
            assert np.array_equal(fid[point_id[covered]], winner[covered])
            front_camera = xyz[point_id[covered]] @ e[camera, :, :3].T + e[camera, :, 3]
            assert np.max(np.abs(front_camera[:, 2]-z[covered])) < 1e-10
            with np.load(buffer_path) as saved:
                assert np.array_equal(saved['winner_frame_id'], winner)
                assert np.array_equal(saved['source_front_z'], ds)
            overlap = has.sum(0) >= 2
            high = np.where(has, ds, -np.inf).max(0)
            spread = (high[overlap]-ds.min(0)[overlap])/depth[camera][overlap]
            ties = covered & ((ds == z[None]).sum(0) >= 2)
            row = {'camera': camera, 'covered_pixels': int(covered.sum()), 'total_pixels': height*width,
                   'cross_covered_pixels': int(ccovered.sum()),
                   'winner_pixels_by_source': [int((winner == i).sum()) for i in range(n)],
                   'source_in_frustum_points': counts,
                   'source_covered_pixels': has.sum((1, 2)).astype(int).tolist(),
                   'exact_front_depth_tie_pixels': int(ties.sum()),
                   'two_or_more_source_overlap_pixels': int(overlap.sum()),
                   'near_front_support_histogram': [int((support == i).sum()) for i in range(n+1)],
                   'near_front_bitmask_histogram': {str(i): int((bits == i).sum()) for i in range(8)},
                   'projected_depth_spread_relative_median': float(np.median(spread)),
                   'projected_depth_spread_relative_p95': float(np.quantile(spread, .95)),
                   'warning': 'Projected spread includes occlusion/distinct surfaces; no wall ROI/correspondence GT; not physical wall thickness.'}
            rows.append(row); overview.append([reference[camera], rgb, crgb, mix]); sources_panel.append(list(source_rgb))
            progress(f'Camera {camera}: 2D PNG·깊이/출처 NPZ 저장, 앞면·자기 투영·재로딩 검증 통과.')
            log(json.dumps(row, ensure_ascii=False))
        panel(stage/'artifacts/figures/overview.png', overview,
              ['Reference RGB', 'All: nearest source color', 'Cross only: nearest source', 'Near-front source mix (3%)'], frames, height, width)
        panel(stage/'artifacts/figures/source_projections.png', sources_panel,
              ['Source 0 = RED', 'Source 1 = GREEN', 'Source 2 = BLUE'], frames, height, width)
        for item in inputs:
            assert record(item['path']) == item
        verification = {'status': 'passed', 'parent_inputs_unchanged': True,
                        'all_and_per_source_ply_reload': True, 'xyz_and_provenance_exact': True,
                        'palette_by_frame_id_exact': True, 'png_lossless_reload': True,
                        'npz_buffers_reload': True, 'front_winner_depth_and_source': True,
                        'controlled_occlusion_and_negative_z': True, 'self_projection': self_checks}
        metrics = {'experiment_code': 'E0a', 'points': len(xyz),
                   'source_point_counts': [int((fid == i).sum()) for i in range(n)],
                   'palette_rgb': palette.tolist(), 'render_hw': [height, width], 'camera_results': rows,
                   'wall_roi_or_gt_accuracy_evaluated': False, 'coordinates_changed': False,
                   'camera_parameters_changed': False, 'cpu_seconds': time.perf_counter()-timer}
        json_write(stage/'evaluation/metrics.json', metrics)
        json_write(stage/'evaluation/verification.json', verification)
        json_write(stage/'environment.json', {'python': platform.python_version(), 'numpy': np.__version__,
                   'opencv': cv2.__version__, 'platform': platform.platform(),
                   'execution_context': 'host CPU; GPU unused',
                   'project_commit_before_run': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                   'source_files': [record(path) for path in sorted((stage/'artifacts/source').iterdir())]})
        progress('출처 색상 패널·통계·입력 불변 검증 완료. GT 정확도/융합/최적화는 미실행.')
        manifest.update(status='completed', ended_at=stamp(), completion_criteria_met=True, inputs=inputs)
        manifest['artifacts'] = [record(path) for path in sorted(stage.rglob('*'))
                                 if path.is_file() and path.name != 'manifest.json']
        json_write(stage/'manifest.json', manifest)
        print(json.dumps({'status': 'completed', 'stage': str(stage), 'cpu_seconds': metrics['cpu_seconds']}))
    except Exception:
        log(traceback.format_exc())
        manifest.update(status='failed', error=traceback.format_exc(), ended_at=stamp())
        json_write(stage/'manifest.json', manifest)
        raise


if __name__ == '__main__':
    main()
