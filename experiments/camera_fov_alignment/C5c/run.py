"""Independent archive/geometry/membership audit across all completed runs."""
from pathlib import Path
import json
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import numpy as np


PLY_DTYPE=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),
    ('blue','u1'),('owner','<i2'),('n_observed','<u4'),('source_mask','u1')])


def verify_map(path,data):
    with np.load(path) as z:mp={k:z[k] for k in z.files}
    labels=mp['source_to_fused'];counts=mp['n_observed'];indices=mp['obs_indices'];offsets=mp['obs_offsets']
    n=len(mp['xyz']);total=len(data['fid'])
    assert len(labels)==total and counts.sum()==total and (counts>0).all()
    assert np.array_equal(np.bincount(labels,minlength=n),counts)
    assert np.array_equal(offsets,np.r_[0,np.cumsum(counts)])
    assert np.array_equal(np.sort(indices),np.arange(total))
    assert np.array_equal(labels[indices],np.repeat(np.arange(n),counts))
    lo=np.minimum.reduceat(data['raw_rgb'][indices].astype(np.int16),offsets[:-1],axis=0)
    hi=np.maximum.reduceat(data['raw_rgb'][indices].astype(np.int16),offsets[:-1],axis=0)
    assert np.array_equal(lo,mp['rgb_min']) and np.array_equal(hi,mp['rgb_max'])
    assert np.all(hi-lo<=30)
    assert np.array_equal(mp['owner_rgb'],data['raw_rgb'][mp['owner_observation_id']])
    assert np.array_equal(mp['intrinsics'],c.corrected_k(data['k'],mp['beta'].reshape(3,2)))
    assert np.array_equal(mp['extrinsics'],data['e'])
    bits=np.zeros(n,np.uint8);np.bitwise_or.at(bits,labels,(1<<data['fid']).astype(np.uint8))
    assert np.array_equal(bits,mp['source_frame_mask'])
    for mode in ['source','rgb']:
        ply=path.parent/f'all_{mode}.ply'
        with ply.open('rb') as stream:
            header=b''
            while not header.endswith(b'end_header\n'):
                line=stream.readline();assert line;header+=line
            vertices=np.fromfile(stream,PLY_DTYPE)
        assert len(vertices)==n and f'element vertex {n}\n'.encode() in header
        xyz=np.column_stack([vertices[k] for k in ['x','y','z']])
        assert np.array_equal(xyz,mp['xyz'])
        color=np.column_stack([vertices[k] for k in ['red','green','blue']])
        assert np.array_equal(color,c.PALETTE[mp['owner']] if mode=='source' else mp['owner_rgb'])
        assert np.array_equal(vertices['n_observed'],counts)
        assert np.array_equal(vertices['source_mask'],bits)
    # Independently replay membership changes and stage-local depth/ray constraints.
    size=int(np.prod(data['depth'].shape[1:]));w=data['depth'].shape[2]
    raw=c.points(data,mp['beta']);previous_xyz=raw[:size]
    current_labels=np.arange(size)
    steps=sorted((path.parent/'steps').glob('after_frame_*.npz'))
    for j,step_file in enumerate(steps,1):
        with np.load(step_file) as z:step={k:z[k] for k in z.files}
        accepted=step['candidate_accepted'];old_ids=step['candidate_old_id'];target=step['candidate_target_flat']
        removed=step['old_removed'];kept=int((~removed).sum())
        assert np.array_equal(step['xyz'][:kept],previous_xyz[~removed])
        assert np.array_equal(np.sort(np.flatnonzero(removed)),np.sort(old_ids[accepted]))
        current_labels=np.r_[step['old_to_new'][current_labels],kept+np.arange(size)]
        assert np.array_equal(current_labels,step['source_to_current'][:(j+1)*size])
        order=np.argsort(current_labels,kind='stable');cnt=np.bincount(current_labels,minlength=len(step['xyz']))
        off=np.r_[0,np.cumsum(cnt)]
        raw_z=raw[:(j+1)*size]@data['e'][j,2,:3]+data['e'][j,2,3]
        loz=np.minimum.reduceat(raw_z[order],off[:-1]);hiz=np.maximum.reduceat(raw_z[order],off[:-1])
        new=np.flatnonzero(step['owner']==j)
        uv=step['uv'][new];anchor=data['depth'][j,uv[:,1],uv[:,0]]
        assert (loz[new]>0).all() and np.all((hiz[new]-loz[new])/anchor<=.03+1e-8)
        sumz=np.zeros(size);number=np.zeros(size,np.int64)
        accepted_z=previous_xyz[old_ids[accepted]]@data['e'][j,2,:3]+data['e'][j,2,3]
        np.add.at(sumz,target[accepted],accepted_z);np.add.at(number,target[accepted],1)
        expected=(data['depth'][j].ravel()+sumz)/(1+number)
        assert np.allclose(expected,step['target_mean_z'].ravel(),atol=1e-12,rtol=1e-12)
        camera=step['xyz'][new]@data['e'][j,:,:3].T+data['e'][j,:,3]
        projected=(camera@mp['intrinsics'][j].T)[:,:2]/camera[:,2,None]
        assert np.max(np.abs(projected-uv),initial=0)<1e-7
        assert np.max(np.abs(camera[:,2]-expected),initial=0)<1e-9
        assert np.all(step['candidate_color_range_at_test'][accepted]<=30)
        assert np.all(step['candidate_depth_range_at_test'][accepted]<=.03+1e-8)
        previous_xyz=step['xyz']
    if steps:assert np.array_equal(previous_xyz,mp['xyz']) and np.array_equal(current_labels,labels)
    else:assert np.array_equal(raw,mp['xyz']) and n==total
    return {'map':str(path.relative_to(c.ROOT)),'points':n,'observations':total,
        'ply_rgb_and_source_verified':True,'csr_colors_camera_and_steps_verified':True}


def main():
    stage=c.Stage('C5c',extra={'purpose':'independent final artifact and scientific protocol audit'})
    try:
        data={name:c.load_data(name) for name in c.DATASETS}
        checked=0;byte_count=0;completed=[];failures=[];map_results=[];parameter_results=[]
        root=c.ROOT/'results/camera_fov_alignment'
        for path in sorted(root.glob('*/stages/*/manifest.json')):
            if path.parent==stage.path:continue
            manifest=json.loads(path.read_text())
            if manifest['status']=='failed':
                failures.append({'run_id':manifest['run_id'],'error':manifest.get('error'),
                    'traceback_preserved':bool(manifest.get('traceback'))});continue
            assert manifest['status']=='completed',path
            completed.append(manifest['run_id'])
            for row in manifest['artifacts']+manifest.get('parents',[]):
                assert c.record(row['path'])==row,row['path']
                checked+=1;byte_count+=row['bytes']
            doc=c.ROOT/'docs/experiments/camera_fov_alignment'/manifest['experiment_code']/manifest['run_id']
            assert (doc/'report.md').is_file()
            assert (doc/'manifest.json').read_bytes()==path.read_bytes()
            metrics=json.loads((path.parent/'evaluation/metrics.json').read_text())
            assert metrics['gt_accuracy_evaluated'] is False
            name=manifest['dataset']
            if name in data:
                original=data[name]
                for parameter_path in path.parent.glob('artifacts/**/parameters.npz'):
                    with np.load(parameter_path) as z:
                        for field in ['selected_beta','proposed_beta']:
                            beta=z[field]
                            assert np.all((beta>=c.LOW-1e-12)&(beta<=c.HIGH+1e-12))
                        assert np.array_equal(z['extrinsics'],original['e'])
                        assert np.array_equal(z['centers'],original['centers'])
                        assert np.array_equal(z['selected_k'],c.corrected_k(original['k'],z['selected_beta'].reshape(3,2)))
                    parameter_results.append(str(parameter_path.relative_to(c.ROOT)))
                for mp in path.parent.glob('artifacts/arms/*/map.npz'):
                    map_results.append(verify_map(mp,original))
            if manifest['experiment_code'] in ['C2','C3']:
                assert metrics['support']['passed'] is False
                assert metrics['optimization_attempted'] is False
                assert metrics['selected_beta']==[1.]*6
            if manifest['experiment_code'] in ['C2a','C3a']:
                assert metrics['decision']=='LOW_SUPPORT_DIAGNOSTIC_ONLY'
                assert metrics['scientific_improvement'] is False
        # Reject broken repository-local report/figure links, including summary if present.
        broken=[]
        docs=c.ROOT/'docs/experiments/camera_fov_alignment'
        for md in docs.rglob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)',md.read_text()):
                if '://' in target or target.startswith('#'):continue
                if not (md.parent/target.split('#',1)[0]).exists():broken.append([str(md),target])
        assert not broken,broken
        result={'decision':'ARCHIVE_AND_PROTOCOL_PASS','completed_runs_verified':completed,
            'preserved_failed_runs':failures,'artifact_hash_records_verified':checked,
            'artifact_bytes_read_including_repeat_parent_records':byte_count,
            'camera_parameter_files_verified':parameter_results,'fusion_maps_verified':map_results,
            'original_raw_hashes_reverified':{name:rows['inputs'][0] for name,rows in data.items()},
            'report_links_passed':True,'scientific_improvement':False,
            'continuous_slam_tested':False}
        stage.finish(result,f'''# C5c 종합 검증

**ARCHIVE_AND_PROTOCOL_PASS**.

- 완료 실행 {len(completed)}개, 해시 기록 {checked:,}개를 실제 파일과 재대조했다.
- 최초 C0 실패 {len(failures)}개를 보존했으며 이후 기술 검증 통과 기록과 구분했다.
- 파라미터 파일 {len(parameter_results)}개에서 FoV 범위·고정 외부행렬/중심·보정 K를 확인했다.
- raw/융합 지도 {len(map_results)}개에서 원본 관측의 중복·유실 없는 CSR, 색 min/max·owner RGB·출처 membership, 단계별 치환·평균 Z·광선·깊이 범위, RGB/출처 PLY를 독립 재검증했다.
- 원래 실내 지원 gate와 보조 저지원 판정이 유지됐고, 모든 실행의 GT 정확도 미평가 표시를 확인했다.
- 문서/그림 링크를 검사했다. 이 검증 통과는 FoV/융합의 과학적 개선이나 SLAM 검증 통과를 뜻하지 않는다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
