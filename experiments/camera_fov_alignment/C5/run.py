"""Offline raw/calibrated x no-fusion/fusion comparison; original data archived."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import diagnostics as d
import fit
import fusion
import numpy as np


def save_arm(data,beta,name,stage,do_fusion):
    output=stage.path/'artifacts/arms'/name;output.mkdir(parents=True)
    started=time.perf_counter();raw=c.points(data,beta)
    k=c.corrected_k(data['k'],np.asarray(beta).reshape(3,2))
    if do_fusion:
        result,metrics=fusion.process(data,raw,k,output/'steps',stage)
    else:
        n=len(raw);labels=np.arange(n)
        result={'xyz':raw,'owner':data['fid'],'uv':data['uv'],'rgb_min':data['raw_rgb'],
            'rgb_max':data['raw_rgb'],'source_to_fused':labels,'n_observed':np.ones(n,np.int64),
            'obs_indices':labels,'obs_offsets':np.arange(n+1),
            'source_frame_mask':(1<<data['fid']).astype(np.uint8),
            'owner_observation_id':labels,'owner_rgb':data['raw_rgb']}
        metrics={'raw_observations':n,'representative_points':n,'reduction_fraction':0.,
            'geometry_array_bytes':raw.nbytes,'all_map_array_bytes':sum(a.nbytes for a in result.values())}
    xyz,owner=result['xyz'],result['owner'];counts=result['n_observed'];bits=result['source_frame_mask']
    np.savez_compressed(output/'map.npz',**result,intrinsics=k,extrinsics=data['e'],beta=np.asarray(beta))
    with np.load(output/'map.npz') as z:
        for key,value in result.items():assert np.array_equal(z[key],value)
    c.ply_write(output/'all_source.ply',xyz,c.PALETTE[owner],owner,counts,bits)
    c.ply_write(output/'all_rgb.ply',xyz,result['owner_rgb'],owner,counts,bits)
    rows,source_rows,projections=d.render(data,xyz,k,output/'projections',owner,result['owner_observation_id'])
    metrics|={'beta':np.asarray(beta).tolist(),'intrinsics':k.tolist(),
        'projection':projections,'resident_map_core_bytes':sum(result[key].nbytes for key in
            ['xyz','owner','uv','owner_rgb','n_observed','source_frame_mask']),
        'npz_bytes':(output/'map.npz').stat().st_size,
        'total_preparation_and_export_seconds':time.perf_counter()-started,
        'source_visualization':'owner color; full multi-frame membership retained separately'}
    c.json_write(output/'metrics.json',metrics)
    return result,k,rows,metrics


def compression(data,reference,result,k):
    h,w=data['depth'].shape[1:];rows=[]
    for camera in range(3):
        original,_,_=c.front(reference['xyz'],k[camera],data['e'][camera],h,w)
        fused,_,_=c.front(result['xyz'],k[camera],data['e'][camera],h,w)
        fixed=np.isfinite(original);shared=fixed&np.isfinite(fused)
        retention=shared.sum()/max(1,fixed.sum())
        diff=np.abs(fused[shared]-original[shared])/original[shared]
        stat=c.stats(diff)
        rows.append({'camera':camera,'initial_covered_pixels':int(fixed.sum()),
            'retained_pixels':int(shared.sum()),'lost_pixels':int((fixed&~shared).sum()),
            'coverage_loss_fraction':float(1-retention),'front_z_relative_change':stat,
            'coverage_pass':bool(1-retention<=.005+1e-12),
            'depth_preservation_pass':bool(len(diff)>0 and stat['p90']<=.03+1e-12)})
    reduction=1-len(result['xyz'])/len(reference['xyz'])
    passed=reduction>=.10 and all(r['coverage_pass'] and r['depth_preservation_pass'] for r in rows)
    return {'decision':'COMPRESSION_SURFACE_PRESERVED' if passed else 'COMPRESSION_CRITERIA_NOT_MET',
        'reduction_fraction':reduction,'cameras':rows,'passed':passed,
        'gt_accuracy_improvement':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',required=True,choices=list(c.DATASETS))
    parser.add_argument('--code',choices=['C5','C5b'],default='C5')
    args=parser.parse_args();data=c.load_data(args.dataset)
    assert args.code!='C5b' or args.dataset!='tum-freiburg1_desk'
    parent_code='C4a' if args.code=='C5b' else 'C3' if args.dataset=='tum-freiburg1_desk' else 'C4'
    parent=fit.latest(parent_code,args.dataset)
    previous=json.loads((parent/'evaluation/metrics.json').read_text())
    previous=previous['per_camera_6var'] if parent_code=='C4' else previous
    available=previous['support']['passed'] and previous['rank']['identifiable'] and \
        previous['optimization_attempted'] and previous['converged']
    # A diagnostic override is never permitted to become the primary C5 calibration.
    available=bool(available and not previous.get('diagnostic_override',False))
    stage=c.Stage(args.code,args.dataset,parents=[parent],extra={
        'calibration_parent_code':parent_code,'exploratory_amendment':args.code=='C5b',
        'calibrated_arms_available':available,'calibration_decision':previous['decision'],
        'fusion_order':[0,1,2],'colors':'owner original RGB, no arithmetic color mixing',
        'depth_gate':'full original-member and current-representative Z range / target D <= .03'})
    try:
        c.json_write(stage.path/'artifacts/inputs.json',data['inputs'])
        arms={};views={};evaluations={};maps={};ks={}
        for name,beta,fused in [('A',np.ones(6),False),('B',np.ones(6),True)]:
            result,k,rows,metrics=save_arm(data,beta,name,stage,fused)
            maps[name]=result;ks[name]=k;views[name]=rows;arms[name]=metrics
        evaluations['A_to_B']=compression(data,maps['A'],maps['B'],ks['A'])
        if available:
            beta=np.asarray(previous['selected_beta'])
            for name,fused in [('C',False),('D',True)]:
                result,k,rows,metrics=save_arm(data,beta,name,stage,fused)
                maps[name]=result;ks[name]=k;views[name]=rows;arms[name]=metrics
            evaluations['C_to_D']=compression(data,maps['C'],maps['D'],ks['C'])
        rgb_rows=[];source_rows=[];fixed_k_rgb=[]
        h,w=data['depth'].shape[1:]
        for camera in range(3):
            rgb_row=[data['rgb'][camera]];source_row=[data['rgb'][camera]];fixed_row=[data['rgb'][camera]]
            for name in ['A','B','C','D']:
                if name in views:
                    rgb_row.append(views[name][camera][1]);source_row.append(views[name][camera][2])
                    z,win,_=c.front(maps[name]['xyz'],data['k'][camera],data['e'][camera],h,w)
                    image=np.zeros((h,w,3),np.uint8);hit=win>=0
                    image[hit]=maps[name]['owner_rgb'][win[hit]];fixed_row.append(image)
                else:
                    placeholder=np.full((h,w,3),235,np.uint8)
                    import cv2
                    cv2.putText(placeholder,'UNAVAILABLE: support/rank gate',(10,h//2),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1,cv2.LINE_AA)
                    rgb_row.append(placeholder);source_row.append(placeholder.copy());fixed_row.append(placeholder.copy())
            rgb_rows.append(rgb_row);source_rows.append(source_row);fixed_k_rgb.append(fixed_row)
        titles=['Input RGB native','A raw','B raw fused','C FoV','D FoV fused']
        c.panel(stage.path/'artifacts/figures/fusion_rgb_comparison.png',rgb_rows,titles)
        c.panel(stage.path/'artifacts/figures/fusion_source_comparison.png',source_rows,titles)
        c.panel(stage.path/'artifacts/figures/fusion_fixed_initial_K.png',fixed_k_rgb,titles)
        metrics={'decision':evaluations['C_to_D' if available else 'A_to_B']['decision'],
            'calibration_parent_code':parent_code,'exploratory_amendment':args.code=='C5b',
            'arms':arms,'comparisons':evaluations,'calibrated_arms_available':available,
            'calibration_decision':previous['decision'],
            'scientific_improvement':False,'point_reduction_verified':True,
            'continuous_slam_tested':False,'fov_effect_inferred_from_fusion':False,
            'per_arm_peak_memory_available':False,
            'memory_note':'array bytes per arm; process peak RSS applies to entire run, not individual arms'}
        table='\n'.join(f'| {name} | {row["representative_points"]:,} | {row["reduction_fraction"]:.3%} | {row["resident_map_core_bytes"]:,} | {row["all_map_array_bytes"]:,} |'
            for name,row in arms.items())
        comparison='\n'.join(f'- {name}: **{row["decision"]}**, 점 수 감소 {row["reduction_fraction"]:.3%}; camera coverage loss `{[round(x["coverage_loss_fraction"],6) for x in row["cameras"]]}`.'
            for name,row in evaluations.items())
        report=f'''# {args.code} 원본 RGB·깊이 근접 융합 — {args.dataset}

실행 `{stage.run_id}`. **{metrics['decision']}**.

색은 원본 8비트 RGB 그룹 범위 ≤30, 깊이는 새 카메라에서 전체 원본 구성점과 현재 대표점의 Z 범위/새 Depth ≤3%다. 후보를 추가할 때마다 전체 그룹을 확인한다. 대표점의 깊이만 산술 평균하고 표시 RGB는 새 owner의 원본 색을 사용한다.

| arm | 대표점 수 | 미융합 입력 대비 감소 | 지도 core 배열 bytes | provenance 포함 map 배열 bytes |
| --- | --- | --- | --- | --- |
{table}

{comparison}

FoV 보정 C/D 사용 가능: **{available}**; 선행 코드 `{parent_code}`, 보정 판정 `{previous['decision']}`. 지원 부족의 탐색 계수는 주 융합 입력으로 승격하지 않았다. C/D가 없으면 A/B 융합만 평가했으며 FoV 후 융합 효과는 미평가다. 보정 선택값이 초기값이면 C=A, D=B다. C5b는 C4a의 탐색적 후보 정책을 사용한 보조 비교이며 원래 C5와 구분한다.

![동일 해상도 실제 RGB](figures/fusion_rgb_comparison.png)

![대표점 owner 프레임 색](figures/fusion_source_comparison.png)

![모든 arm을 초기 K에서 투영](figures/fusion_fixed_initial_K.png)

평균 Z/광선·거절점 좌표 불변, 원본 관측의 중복·유실 없는 CSR, 단계별 색/깊이 범위를 검증했다. 다중 프레임 그룹의 출처는 NPZ membership에 보존한다. 그림 색은 최신 owner이며 유일한 관측 출처라는 뜻이 아니다.

점 수 감소와 coverage/표면 보존을 별도로 판단한다. 압축 기준은 ≥10% 점 수 감소, camera별 coverage 손실 ≤0.5%p, 공통 영역 front-Z 변화 p90 ≤3%다. raw 표면 보존 지표이며 GT 정확도가 아니다. 지도 core·provenance map·원본 보관 자료의 배열 논리 크기(중복 참조 포함)를 구분하고 실행 전체 peak RSS와 시간을 기록했다. 논리 크기는 실제 resident RAM과 다를 수 있다. arm별 peak RSS나 실제 SLAM 실시간성은 검증하지 않았다.
'''
        stage.finish(metrics,report)
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
