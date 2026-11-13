"""Recolor archived E3b XYZ with original owner-pixel RGB; no optimization."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DT=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),
    ('blue','u1'),('owner','<i2'),('n_observed','<u4'),('source_mask','u1')])


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest}


def main():
    parent=ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E3b-20261112-002/stages/E3b'
    source=parent/'artifacts/maps'
    observations=ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E0-20261112-001/stages/E0/artifacts/baseline/observations.npz'
    seq=1
    while (ROOT/f'results/ply_visualization/E3b_pixel_rgb-{seq:03}').exists():seq+=1
    output=ROOT/f'results/ply_visualization/E3b_pixel_rgb-{seq:03}';output.mkdir(parents=True)
    with np.load(observations) as z:
        rgb=z['rgb'];frame=z['frame_id'];uv=z['pixel_uv']
    with np.load(source/'shared_map_initial.npz') as z:
        owner=z['owner_camera'];pixel=z['owner_pixel_uv']
        ids=owner.astype(np.int64)*(512*384)+pixel[:,1]*512+pixel[:,0]
        assert np.array_equal(frame[ids],owner) and np.array_equal(uv[ids],pixel)
        colors=rgb[ids].copy();counts=z['n_observed'];bits=z['source_frame_mask']
    files=[];positions={}
    for state in ['initial','selected','last']:
        src=source/f'shared_map_{state}.npz'
        with np.load(src) as z:
            xyz=z['xyz'].copy()
            assert np.array_equal(z['owner_camera'],owner)
        assert np.isfinite(xyz).all()
        array=np.empty(len(xyz),DT)
        for i,key in enumerate(['x','y','z']):array[key]=xyz[:,i]
        for i,key in enumerate(['red','green','blue']):array[key]=colors[:,i]
        array['owner']=owner;array['n_observed']=counts;array['source_mask']=bits
        path=output/f'{state}_pixel_rgb.ply'
        header=('ply\nformat binary_little_endian 1.0\ncomment E3b archived XYZ; original owner-pixel RGB; no color averaging\n'
            f'element vertex {len(array)}\nproperty double x\nproperty double y\nproperty double z\n'
            'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty short owner\n'
            'property uint n_observed\nproperty uchar source_mask\nend_header\n')
        with path.open('xb') as stream:stream.write(header.encode());array.tofile(stream)
        with path.open('rb') as stream:
            while stream.readline()!=b'end_header\n':pass
            check=np.fromfile(stream,DT)
        assert np.array_equal(check,array)
        positions[state]=xyz
        files.append({'state':state,'vertices':len(xyz),'file':record(path),'source':record(src)})
    metadata={'purpose':'E3b 기존 좌표의 원본 픽셀색 표시 버전 추가',
        'color':'각 대표점의 최신 owner 카메라·owner 픽셀의 E0 원본 처리 RGB; 평균/중앙값 아님',
        'training_color_difference':'원래 E3b 학습은 그룹 원본 RGB 중앙값 rgb_fixed를 사용함. 이번 것은 표시 색만 owner 원본 픽셀색.',
        'geometry_changed':False,'optimization_performed':False,
        'selected_equals_initial':bool(np.array_equal(positions['initial'],positions['selected'])),
        'last_equals_initial':bool(np.array_equal(positions['initial'],positions['last'])),
        'original_observations':record(observations),'files':files}
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n')
    docs=ROOT/'docs/ply_visualization';docs.mkdir(parents=True,exist_ok=True)
    (docs/f'E3b_pixel_rgb-{seq:03}.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(metadata,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
