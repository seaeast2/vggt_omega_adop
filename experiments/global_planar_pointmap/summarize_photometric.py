"""Verify I12/I13 provenance and write lightweight Korean result indexes."""
from core import *

def run():
    summary={};audits={};gtrows=[];rgbrows=[];links=[]
    for dataset in ['tum-freiburg1_desk','tum-freiburg1_desk-extra']:
        evaluation=latest('I13',dataset);result=json.loads((evaluation/'evaluation/metrics.json').read_text())
        optimization=FAMILY/result['source_run']/'stages/I12';opt=json.loads((optimization/'evaluation/metrics.json').read_text())
        rows=json.loads((optimization/'evaluation/planes.json').read_text());active=[x for x in rows if x['status']=='OPTIMIZED']
        verified=[]
        for stage in [optimization,evaluation]:
            manifest=json.loads((stage/'manifest.json').read_text())
            for record in manifest['artifacts']:
                assert c.record(Path(record['path']))['sha256']==record['sha256'],record['path']
            for record in json.loads((stage/'evaluation/metrics.json').read_text())['inputs']:
                assert c.record(Path(record['path']))['sha256']==record['sha256'],record['path']
            verified.append(dict(run_id=stage.parents[1].name,manifest=c.record(stage/'manifest.json'),artifacts_verified=len(manifest['artifacts'])))
        assert not json.loads((optimization/'manifest.json').read_text())['gt_accuracy_evaluated']
        assert json.loads((evaluation/'manifest.json').read_text())['gt_accuracy_evaluated']
        assert json.loads((optimization/'manifest.json').read_text())['ended_at']<json.loads((evaluation/'manifest.json').read_text())['started_at']
        for filename in ['photometric_planes.py','core.py','export.py','named_or.py']:
            assert c.record(optimization/'artifacts/source'/filename)['sha256']==c.record(SOURCE/filename)['sha256'],filename
        assert (optimization/'artifacts/source/photometric_plan.md').read_bytes()==(ROOT/'docs/vggt_omega_plane_photometric_experiment_plan.md').read_bytes()
        with np.load(latest('I10',dataset)/'artifacts/named_or/retained/pointmap.npz') as x,np.load(optimization/'artifacts/photometric/retained/pointmap.npz') as y:
            assert all(np.array_equal(x[k],y[k]) for k in ['xyz','plane_id','rgb','observation_id','frame_id','pixel_uv','intrinsics','extrinsics'])
        rerun_equal=None
        if dataset=='tum-freiburg1_desk':
            first=FAMILY/'tum-freiburg1_desk-I12-20261114-001/stages/I12/artifacts/photometric'
            for arm in ['plane_distance','plane_distance_normal']:
                with np.load(first/arm/'pointmap.npz') as x,np.load(optimization/'artifacts/photometric'/arm/'pointmap.npz') as y:
                    assert np.array_equal(x['xyz'],y['xyz'])
            rerun_equal=True
        weights=np.array([x['initial_fit']['count'] for x in active]);base=sum(x['initial_fit']['normalized_robust_mean']*w for x,w in zip(active,weights))/weights.sum()
        fit={'plane_fixed':dict(loss=base,relative_gain=0.)};bounds={}
        for arm in ['plane_distance','plane_distance_normal']:
            loss=sum(x['arms'][arm]['fit_photo']['normalized_robust_mean']*w for x,w in zip(active,weights))/weights.sum()
            fit[arm]=dict(loss=loss,relative_gain=1-loss/base)
            bounds[arm]=sum(x['arms'][arm]['bound_hit'] for x in active)
        label=dataset.replace('tum-freiburg1_','')
        for arm in ['initial','plane_fixed','plane_distance','plane_distance_normal','retained']:
            m=result['metrics'][arm]['all']['depth'];gtrows.append(f"| {label} | {arm} | {100*m['mae_m']:.4f} | {100*m['rmse_m']:.4f} |")
        for arm in fit:
            val=opt['validation_photo'][arm];rgbrows.append(f"| {label} | {arm} | {fit[arm]['loss']:.6f} | {val['normalized_robust_mean']:.6f} |")
        summary[dataset]=dict(I12=optimization.parents[1].name,I13=evaluation.parents[1].name,decision=result['decision'],
            optimized_planes=len(active),optimized_observations=opt['optimized_observations'],optimized_GT_validation=result['optimized_GT_validation_count'],
            fit_photo=fit,validation_photo=opt['validation_photo'],bounds_hit=bounds,
            primary_validation_gain=opt['validation_relative_gain'],primary_frustum_loss=opt['arms']['plane_distance_normal']['visibility']['maximum_frustum_loss'],
            retained=opt['retained'],GT=result['metrics'],primary_comparisons=result['comparisons_primary'])
        audits[dataset]=dict(verified=verified,GT_flags_correct=True,optimizer_completed_before_GT=True,
            computation_source_matches_snapshots=True,plan_matches_snapshot=True,retained_equals_previous_I10_bitwise=True,
            first_completed_run_equals_rerun_bitwise=rerun_equal,I13_checks=result['checks'],I12_synthetic_checks=opt['checks'])
        links.append(f"- [{label}: RGB 최적화](../I12/{optimization.parents[1].name}/report.md) · [GT 보고서]({evaluation.parents[1].name}/report.md) · [오차 이미지]({evaluation.parents[1].name}/figures/gt_depth_error.png)")
    out=DOC/'I13';c.json_write(out/'summary.json',summary);c.json_write(out/'audit.json',audits)
    report='''# I12–I13 — 평면 거리·법선의 다중 시점 RGB 최적화 결과

**두 구간 모두 `NO_CONFIRMED_GAIN`이다.** 평면을 개별 정점보다 적은 자유도로 움직여도 이번 설정에서는 보류 RGB와 GT 깊이 정확도가 악화됐다. 기존 I10 retained는 그대로 유지했다.

[사전 계획](../../../vggt_omega_plane_photometric_experiment_plan.md)에 따라 I12는 GT를 읽지 않고 RGB로 최적화한 뒤 모든 출력을 저장했다. I13은 완료된 I12 출력에 I11의 GT 배열·scale·validation mask·Sim(3)를 그대로 적용했다. initial은 현재 I2 FoV 점군, plane_fixed는 기존 I10 named_OR다. 카메라·K·소속·마스크·RGB·ID·UV는 고정했다. 새 primitive와 새 평면 병합은 사용하지 않았다.

## 전체 GT 깊이 정확도

단위 cm, 낮을수록 좋다. 같은 구간의 모든 비교군에 공통 baseline scale을 적용했다.

| 구간 | 출력 | MAE ↓ | RMSE ↓ |
|---|---|---:|---:|
'''+ '\n'.join(gtrows)+'''

주 처치군은 거리·법선 3자유도다. plane_fixed 대비 전체 MAE는 주 구간 **11.3405%**, 추가 구간 **13.9953%** 늘었다. initial 대비도 각각 **14.1283%**, **21.4315%** 늘었다. 두 구간 모두 원래 성공 기준을 통과하지 못했다. 거리만 움직이는 군도 전체 정확도가 악화됐다.

## RGB 손실과 적용 범위

표의 값은 고정 photo 표본의 정규화 pseudo-Huber 평균이다. source-target 표본의 RGB 오차를 나타내며 정점 전체의 렌더링 손실은 아니다. FIT와 validation은 서로 다른 공간 표본이므로 각각 같은 열 안의 비교군을 비교한다. 목적함수에는 이 photo 손실 외에 대응점·raw-depth·법선 prior와 이탈 penalty도 포함된다.

| 구간 | 출력 | FIT photo ↓ | 보류 photo ↓ |
|---|---|---:|---:|
'''+ '\n'.join(rgbrows)+'''

주 구간 거리·법선 군의 FIT photo 손실은 **24.1859% 감소**했지만 보류 photo는 **4.9822% 증가**했다. 추가 구간 FIT photo는 **1.0555% 감소**, 보류 photo는 **5.8332% 증가**했다. 추가 구간 거리만 군은 전체 목적함수가 감소했어도 photo 단독 손실은 늘었다. RGB 학습 손실 감소와 실제 기하 개선을 구분해야 한다.

주 구간 24/94개 평면·149,990점, 추가 구간 21/94개 평면·96,860점을 최적화했다. 그 안의 GT validation은 각각 23,168개·16,087개로 지지 부족 판정은 아니다. 저텍스처·비가시·split/태그 지원 부족 평면은 그대로 유지했다. 주 구간 wall은 지원 부족으로 움직이지 않았으므로 이번 실험에서 벽 보정의 효과를 평가했다고 할 수 없다.

거리·법선 군의 최대 frustum 손실은 주 구간 **0.2926%**로 통과했지만 추가 구간 **0.5839%**로 기존 0.5% 기준을 넘었다. 두 구간 모두 보류 RGB 조건을 실패했다. 따라서 retained는 새 결과로 승격하지 않고 기존 I10 선택을 유지했다.

## 해석과 제한

현재 검증된 것은 **이번 평면 초기화·고정 소속·표본·RGB 목적함수·국소 탐색 범위에서는 자유도 축소만으로 정확도가 개선되지 않았다**는 것이다. 모든 평면 기반 광도 최적화가 불가능하다는 결론은 아니다.

대부분의 기존 평면은 한 view의 패치다. 초기 warp에서 다른 view의 같은 태그인 픽셀을 요구했지만 동일 물리 표면을 보장하지 않으며 새 공유 평면 병합을 하지 않았다. 이후 이동에서는 영상·split 이탈을 penalty로 다루고 target 태그 경계는 다시 강제하지 않았다. 영상 경계·가림·노출·반사·현재 카메라 및 초기 기하 오차도 남는다. 거리·법선 군은 24개 중 10개, 21개 중 5개 평면에서 탐색 bound에 닿았다. 이것은 국소 범위나 목적함수의 문제를 더 조사할 단서이며 원인을 확정한 증거는 아니다. bound를 늘리거나 손실 가중치를 GT 결과에 맞춰 재조정하지 않았다.

초기/FIXED의 I11 GT 지표를 정확히 재현했고, unknown과 미지원 평면의 좌표 동일성을 통과했다. 센서 depth 경계를 제외한 보조 평가 및 대응 3D 오차도 보고했다. 이번 두 구간은 이전에 GT를 본 같은 장면이므로 독립 장면·전체 SLAM·일반화 성능을 주장하지 않는다.

## 산출물과 재현

'''+ '\n'.join(links)+'''

[정확한 수치](summary.json) · [출처·해시 검증](audit.json)

각 I12 stage의 `artifacts/photometric/`에 initial/plane_fixed/plane_distance/plane_distance_normal/retained의 NPZ·PLY·평면 registry·경계와 고정 support를 저장했다. `evaluation/planes.json`에는 평면별 parameter·지원수·FIT/validation 손실·bounds·미분 검증·solver 상태가 있다. I13에는 GT 오차·영역별/per-frame 지표·입력 해시·오차 이미지를 보존했다.

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/photometric_planes.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/evaluate_photometric_planes.py
.venvs/p2a/bin/python experiments/global_planar_pointmap/summarize_photometric.py
```

합성 평면 복원·해석 미분·금지 RGB 대체의 불변성·자기 시점 깊이 미분 0을 확인했다. 실제 영상의 중앙 차분이 픽셀 경계를 넘던 첫 검증을 수정하고 두 구간을 I12.2로 재실행했다. 첫 주 구간 완료 및 추가 구간 실패는 `-001`에 보존했고 canonical optimizer는 `-002`다. GT 결과를 본 뒤 최적화 설정을 바꾸지 않았다.
'''
    (out/'index.md').write_text(report)
    rgbout=DOC/'I12'
    (rgbout/'index.md').write_text('# I12 — 평면 거리·법선의 RGB 최적화\n\n[계획](../../../vggt_omega_plane_photometric_experiment_plan.md) · [I13 GT 포함 종합 결과](../I13/index.md)\n\nI12는 GT를 읽지 않고 실행했다. canonical은 두 구간 모두 `-002`다. `-001`의 완료/실패 기록을 보존했다.\n\n'+ '\n'.join(f"- [{ds}]({v['I12']}/report.md): {v['optimized_planes']}개 평면, 보류 RGB 상대 감소 {v['primary_validation_gain']:.4%}, retained={v['retained']}" for ds,v in summary.items())+'\n')
    print(json.dumps({k:dict(decision=v['decision'],I12=v['I12'],I13=v['I13']) for k,v in summary.items()}))

if __name__=='__main__':run()
