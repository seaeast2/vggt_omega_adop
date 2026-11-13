"""Recolor both archived E3c arms with original owner-pixel RGB."""
import json
from pathlib import Path
import numpy as np
from export_e3b_pixel_rgb import ROOT,DT,record


def main():
    parent=ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E3c-20261112-001/stages/E3c'
    observations=ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E0-20261112-001/stages/E0/artifacts/baseline/observations.npz'
    seq=1
    while (ROOT/f'results/ply_visualization/E3c_pixel_rgb-{seq:03}').exists():seq+=1
    output=ROOT/f'results/ply_visualization/E3c_pixel_rgb-{seq:03}';output.mkdir(parents=True)
    with np.load(observations) as z:rgb,frame,uv=z['rgb'],z['frame_id'],z['pixel_uv']
    arms={}
    for arm in ['control_E0b','treatment_E0c']:
        source=parent/'arms'/arm/'maps';destination=output/arm;destination.mkdir()
        with np.load(source/'shared_map_initial.npz') as z:
            owner=z['owner_camera'];pixel=z['owner_pixel_uv']
            counts=z['n_observed'];bits=z['source_frame_mask']
        ids=owner.astype(np.int64)*(512*384)+pixel[:,1]*512+pixel[:,0]
        assert np.array_equal(frame[ids],owner) and np.array_equal(uv[ids],pixel)
        colors=rgb[ids].copy();files=[];positions={}
        for state in ['initial','selected','last']:
            src=source/f'shared_map_{state}.npz'
            with np.load(src) as z:
                xyz=z['xyz'].copy()
                assert np.array_equal(z['owner_camera'],owner)
                assert np.array_equal(z['owner_pixel_uv'],pixel)
            assert np.isfinite(xyz).all()
            array=np.empty(len(xyz),DT)
            for i,key in enumerate(['x','y','z']):array[key]=xyz[:,i]
            for i,key in enumerate(['red','green','blue']):array[key]=colors[:,i]
            array['owner']=owner;array['n_observed']=counts;array['source_mask']=bits
            path=destination/f'{state}_pixel_rgb.ply'
            header=('ply\nformat binary_little_endian 1.0\ncomment E3c archived XYZ; original owner-pixel RGB; no color averaging\n'
                f'element vertex {len(array)}\nproperty double x\nproperty double y\nproperty double z\n'
                'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty short owner\n'
                'property uint n_observed\nproperty uchar source_mask\nend_header\n')
            with path.open('xb') as stream:stream.write(header.encode());array.tofile(stream)
            with path.open('rb') as stream:
                while stream.readline()!=b'end_header\n':pass
                assert np.array_equal(np.fromfile(stream,DT),array)
            positions[state]=xyz
            files.append({'state':state,'vertices':len(xyz),'file':record(path),'source':record(src)})
        assert np.array_equal(positions['selected'],positions['last'])
        assert not np.array_equal(positions['initial'],positions['last'])
        arms[arm]={'selected_equals_last':True,'last_equals_initial':False,'files':files}
    metadata={'purpose':'E3c 두 arm의 기존 좌표를 원본 owner 픽셀색으로 표시',
        'color':'E0 원본 처리 RGB 중 각 대표점 owner 카메라·owner 픽셀의 색; 평균/중앙값 아님',
        'training_color_difference':'원래 학습의 rgb_fixed 그룹 중앙값과는 별도 표시 색',
        'geometry_changed':False,'optimization_performed':False,
        'original_observations':record(observations),'arms':arms}
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n')
    docs=ROOT/'docs/ply_visualization';docs.mkdir(parents=True,exist_ok=True)
    (docs/f'E3c_pixel_rgb-{seq:03}.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'output':str(output),'files':6,'arms':{k:{'vertices':v['files'][0]['vertices'],
        'selected_equals_last':v['selected_equals_last']} for k,v in arms.items()}},ensure_ascii=False))


if __name__=='__main__':main()
