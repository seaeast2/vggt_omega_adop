"""Audit and summarize the two new ETH3D indoor laser-GT transfers."""
from core import *
from eth3d_laser import DATASETS, PLAN

def run():
    output=DOC/'I20';summary={};audit={};rows=[];rgb=[];stage_rows=[];references=[];memo={}
    def verify(record):
        p=Path(record['path']);key=(str(p),record['sha256'])
        if key not in memo:
            actual=c.record(p);assert actual['sha256']==record['sha256'],str(p);assert actual['bytes']==record['bytes'];memo[key]=True
    for dataset in DATASETS:
        gtstage=latest('I20',dataset);result=json.loads((gtstage/'evaluation/metrics.json').read_text());optstage=FAMILY/result['source_run']/'stages/I12'
        optimizer=json.loads((optstage/'evaluation/metrics.json').read_text());i14=latest('I14',dataset);i15=latest('I15',dataset);i10=latest('I10',dataset)
        stages={k:latest(k,dataset) for k in ['I0','I1','I2','I3','I4','I10','I12','I14','I15','I20']}
        manifests={};verified_count=0
        for code,stage in stages.items():
            manifest=json.loads((stage/'manifest.json').read_text());assert manifest['status']=='completed'
            for record in manifest['artifacts']+manifest['parents']:verify(record);verified_count+=1
            manifests[code]=c.record(stage/'manifest.json')
            stage_rows.append(f"| {dataset} | {code} | [{stage.parents[1].name}](../{code}/{stage.parents[1].name}/report.md) | {manifest['decision']} |")
        for rec in result['inputs']+optimizer['inputs']:verify(rec)
        data=json.loads((i14/'evaluation/metrics.json').read_text())
        for rec in data['archives']+data['camera_files']:verify(rec)
        verify(json.loads((i15/'evaluation/model_provenance.json').read_text())['checkpoint'])
        model=json.loads((latest('I1',dataset)/'evaluation/model_provenance.json').read_text())
        for rec in model['models']:verify(rec)
        assert json.loads((optstage/'manifest.json').read_text())['ended_at']<json.loads((gtstage/'manifest.json').read_text())['started_at']
        assert not json.loads((optstage/'manifest.json').read_text())['gt_accuracy_evaluated']
        assert json.loads((gtstage/'manifest.json').read_text())['gt_accuracy_evaluated']
        assert np.array_equal(np.array(data['frames'][0]['camera']['params']),np.array(load(dataset)['frames'][0]['camera']['params']))
        # I1 began before a metadata-only I0 report fix. The actual split stayed fixed.
        oldparent=json.loads((latest('I1',dataset)/'manifest.json').read_text())['parents'][0]['path']
        oldcontract=Path(oldparent).parent/'artifacts/contract'/dataset/'split.npz'
        with np.load(oldcontract) as a,np.load(split_path(dataset)/'split.npz') as b:
            assert all(np.array_equal(a[k],b[k]) for k in a.files)
        with np.load(i10/'artifacts/named_or/retained/pointmap.npz') as a,np.load(optstage/'artifacts/photometric/retained/pointmap.npz') as b:
            retained_unchanged=all(np.array_equal(a[k],b[k]) for k in ['xyz','plane_id','rgb','observation_id','frame_id','pixel_uv','intrinsics','extrinsics'])
        assert retained_unchanged or optimizer['primary_passes_rgb_visibility']
        previous_GT=[p for p in sorted(FAMILY.glob(f'{dataset}-I20-*/stages/I20')) if p!=gtstage and json.loads((p/'manifest.json').read_text())['status']=='completed']
        IO_replay=None
        if previous_GT:
            first=json.loads((previous_GT[-1]/'evaluation/metrics.json').read_text())
            assert first['metrics']==result['metrics'] and first['alignment']==result['alignment']
            IO_replay=True
        # Public computation implementations were reused; only adapters/metadata were added.
        for filename in ['photometric_planes.py','named_or.py','export.py']:
            assert c.record(optstage/'artifacts/source'/filename)['sha256']==c.record(SOURCE/filename)['sha256'],filename
        plane_history=json.loads((optstage/'evaluation/planes.json').read_text());active=[p for p in plane_history if p['status']=='OPTIMIZED']
        weight=sum(p['initial_fit']['count'] for p in active)
        def fit_loss(arm):
            values=[p['initial_fit'] if arm=='plane_fixed' else p['arms'][arm]['fit_photo'] for p in active]
            return sum(p['count']*p['normalized_robust_mean'] for p in values)/max(weight,1)
        fitphoto={a:fit_loss(a) for a in ['plane_fixed','plane_distance','plane_distance_normal']}
        for arm in ['initial','plane_fixed','plane_distance','plane_distance_normal','retained']:
            m=result['metrics'][arm]['all']['depth'];rows.append(f"| {dataset.removeprefix('eth3d-')} | {arm} | {100*m['mae_m']:.4f} | {100*m['rmse_m']:.4f} | {m['abs_rel']:.7f} |")
        for arm in fitphoto:
            val=optimizer['validation_photo'][arm]['normalized_robust_mean'];rgb.append(f"| {dataset.removeprefix('eth3d-')} | {arm} | {fitphoto[arm]:.6f} | {val:.6f} |")
        summary[dataset]=dict(decision=result['decision'],GT_sensor=result['GT_sensor'],source_run=result['source_run'],I20_run=gtstage.parents[1].name,
            frames=[f['name'] for f in data['frames']],GT_valid_count=result['valid_GT_count'],GT_total=result['total_observations'],
            GT_validation=result['evaluation_count'],optimized_GT=result['optimized_GT_count'],optimized_planes=result['optimized_planes'],
            optimized_observations=result['optimized_observations'],retained=result['retained'],retained_unchanged=retained_unchanged,
            calibration_checks=result['calibration']['checks'],GT=result['metrics'],comparison=result['comparison'],fit_photo=fitphoto,
            validation_photo=result['rgb_validation'],validation_photo_relative_gain=result['rgb_validation_relative_gain'],
            primary_frustum_loss=optimizer['arms']['plane_distance_normal']['visibility']['maximum_frustum_loss'],
            RGB_visibility_pass=result['rgb_visibility_pass'],bounds_hit=sum(p['arms']['plane_distance_normal']['bound_hit'] for p in active),
            FOV=json.loads((latest('I2',dataset)/'evaluation/metrics.json').read_text()))
        summary[dataset]['named_OR_rescued_unknown']=json.loads((i10/'evaluation/metrics.json').read_text())['arms']['named_OR']['rescued_unknown_pixels']
        audit[dataset]=dict(manifests=manifests,artifact_records_verified=verified_count,GT_flags_and_execution_order_verified=True,
            I20_checks=result['checks'],I12_controls=optimizer['checks'],same_optimizer_source=True,
            metadata_corrected_I0_split_bitwise_identical_to_I1_parent=True,retained_unchanged_from_I10=retained_unchanged,
            standalone_download_bootstrap_GT_replay_identical=IO_replay)
        references.append(f"- **{dataset}**: [선택 RGB](../I14/{i14.parents[1].name}/figures/selected_RGB.png) · [named OR 마스크](../I10/{i10.parents[1].name}/figures/named_OR_mask.png) · [GT 보고서]({gtstage.parents[1].name}/report.md) · [GT 오차 이미지]({gtstage.parents[1].name}/figures/gt_depth_error.png)")
        # Correct only the copied documentation's legacy TUM evaluator name.
        copied=DOC/'I12'/optstage.parents[1].name/'report.md'
        copied.write_text(copied.read_text().replace('별도 프로세스 I13에서 수행한다.','ETH3D 전이 실험의 별도 프로세스 I20에서 수행한다.'))
    c.json_write(output/'summary.json',summary);c.json_write(output/'audit.json',audit)
    success={k:v['decision'] for k,v in summary.items()}
    report='''# ETH3D 실내 레이저 GT 전이 결과 — office / pipes

Kinect 깊이의 잔여 왜곡·센서 오차와 구분해 보기 위해 **서로 다른 실내 두 장면**에서 재실험했다. ETH3D의 FARO Focus X 330 레이저 스캔에서 가림·mask를 고려해 렌더한 camera-Z depth를 사용했다. 제공 RGB와 보정으로 **GT를 보지 않고 장면당 3장**을 선택하고, Omega 추론→SAM/DINO→FoV→자동 평면→named OR→평면 RGB 최적화→GT 평가까지 실행했다.

[사전 계획·데이터 조사](../../../vggt_omega_eth3d_laser_experiment_plan.md). [공식 데이터](https://eth3d.ethz.ch/datasets) · [공식 보정/depth 규약](https://eth3d.ethz.ch/documentation).

## 전체 GT 깊이 정확도

initial은 현재 FoV 초기 점군, plane_fixed는 named_OR 투영이다. 깊이는 baseline FIT의 공통 scale을 고정했고, 모든 군을 동일한 valid-GT validation 픽셀에서 평가했다. 단위 cm, 낮을수록 좋다.

| 장면 | 출력 | MAE ↓ | RMSE ↓ | AbsRel ↓ |
|---|---|---:|---:|---:|
'''+ '\n'.join(rows)+ '\n\n장면별 사전 기준 판정: `'+str(success)+'`.\n\n'
    for dataset,s in summary.items():
        report+=f"- {dataset}: 최적화 {s['optimized_planes']}개 평면·{s['optimized_observations']:,}점, optimized GT validation {s['optimized_GT']:,}개. 전체 GT validation {s['GT_validation']:,}개, 전체 유효 GT {s['GT_valid_count']:,}/{s['GT_total']:,}. 보류 RGB 손실 상대 감소 {s['validation_photo_relative_gain']:.4%}, 최대 frustum 손실 {s['primary_frustum_loss']:.4%}, retained=`{s['retained']}`.\n"
    report+='''
사무실은 평면 고정 1.6068→거리·법선 2.1235 cm로 전체 MAE가 늘었지만, RMSE는 5.5629→5.2274 cm로 줄었다. screen MAE도 14.4314→11.7289 cm로 줄었으나 wall MAE는 0.5400→2.1235 cm로 늘었다. 전체 오차와 일부 영역의 효과를 구분한다.

배관 실내는 **초기→고정 평면만** 적용할 때 MAE 2.2731→2.2031 cm, RMSE 3.6006→3.5890 cm로 소폭 줄었다. 그러나 거리·법선 RGB 재정렬 뒤 MAE 2.4325 cm, RMSE 4.0212 cm로 늘었다. 장면에 따라 평면 투영의 영향은 달랐지만, RGB 재정렬의 전체 개선은 두 장면 모두 확인하지 못했다.

baseline FIT-only 공통 Sim(3) 후 대응 3D mean 오차(cm)는 office initial/fixed/거리·법선 = 3.2186/3.5278/4.0588, pipes = 2.8014/2.7736/3.0090이다. 깊이와 별도의 공통 정렬을 쓰는 보조 지표이며 같은 추세였다. 원본 GT 3×3 이웃이 모두 유효한 smooth 보조 mask는 sparse 레이저 depth 때문에 office 8점, pipes 0점뿐이라 경계 민감도 결론에는 사용하지 않는다.

## FIT/보류 RGB와 해석

| 장면 | 출력 | FIT photo 손실 ↓ | 보류 photo 손실 ↓ |
|---|---|---:|---:|
'''+ '\n'.join(rgb)+'''

성공 조건은 주 처치군 거리·법선의 전체 깊이 MAE가 initial 및 plane_fixed 양쪽보다 1% 이상 줄고 RMSE가 늘지 않으며, 보류 RGB가 1% 이상 개선되고 frustum 손실이 0.5% 이하인 것이다. optimized GT validation 500개 미만이면 지지 부족이다. 일부 지표나 영역의 개선은 별도로 읽고 전체 개선으로 합치지 않는다. 각 군의 전체·투영·최적화·태그별·per-frame·smooth-depth 및 대응 3D 보조 지표는 run별 metrics JSON에 있다.

레이저 GT에서도 원래 기하·카메라·분할·RGB 목적함수의 문제는 남는다. GT 센서를 바꿨다고 RGB 손실 최소화가 실제 표면 복원을 보장하지는 않는다. 이 두 장면에서 관측한 효과만 보고하며, 원인을 잔여 렌즈 왜곡 하나로 확정하거나 모든 평면 최적화 방법이 불가능하다고 해석하지 않는다.

## 왜곡과 공정 비교 검증

DSLR의 왜곡 보정 RGB는 약 6220×4140, 원본 RGB/depth는 6048×4032로 **같은 격자가 아니다**. processed 512×336의 중심 광선을 공식 PINHOLE K에서 복원하고 THIN_PRISM_FISHEYE를 통해 원래 depth 격자로 대응했다. 최근접 유효 depth만 사용했으며 GT hole filling을 하지 않았다.

각 이미지의 4096개 투영을 수정하지 않은 공식 C++ 카메라 구현과 대조했다. 최대 차이는 office 0.000929 px, pipes 0.000734 px 이하이고, 원본/undistorted RGB 대응 MAE는 약 0.004 [0,1]였다. COLMAP corner-origin과 공식 loader의 cx/cy -0.5 shift, GT 생성 코드의 camera-Z 저장을 확인했다. camera 모델·GT 생성 source의 hash와 immutable camera source URL을 run에 보존했다.

I12는 레이저 GT 내용을 읽기 전에 완료했다. I20에서 initial FIT의 단일 median-ratio scale을 추정해 전 군에 고정했다. 비교군별 scale/shift/Sim(3) 재최적화나 GT 기반 mask 선택은 하지 않았다. unknown·미지원 평면·ID·RGB·UV·K·pose 보존을 검사했다.

## 전이 실험의 제한과 실행 보완

- DSLR 전체 해상도 대신 실제 processed RGB에서 SAM/DINO를 실행했다. TUM은 640×480 원본 SAM이었으므로 입력 해상도 차이가 있다. checkpoint·prompt·threshold·grid32·허용 wall/table/screen·평면/연결·RGB optimizer/가중치/bounds는 그대로다. floor·파이프·원통을 추가하지 않았다.
- 두 장면의 SIFT/FoV 지원은 기존 전체 기준에 못 미쳐 `LOW_SUPPORT_PROPOSED_PRESERVED`였다. 해당 제안값을 쓰는 기존 탐색 정책을 유지했다. 공식 GT 카메라 pose/K를 모델 또는 RGB 최적화에 넣지 않았다.
- 대부분의 평면 ID는 단일 view 패치일 수 있다. named target class가 같은 실제 표면임을 보장하지 않는다. 저텍스처·반사·가림·노출/JPEG·추정 카메라·초기 기하 오차는 남는다. 레이저 GT에도 결측·표면 반사·등록 오차가 있다.
- 두 장면 모두 named OR로 새로 구제된 unknown은 0점이었다. 따라서 이번 결과로 의미 OR 전달 자체의 이득을 평가할 수는 없으며 기존 named 평면의 투영 및 RGB 재정렬 효과를 주로 측정했다.
- 첫 office I0는 원본 RGB SHA를 processed RGB 파일에 비교하던 adapter metadata 오류로 중단돼 보존했다. 경로·SHA를 processed RGB와 맞춘 뒤 재실행했다. 상속된 TUM 고정 해상도·frame index 설명도 새 장면의 실제 값으로 수정했다. split 배열은 bitwise 동일함을 확인했고 I1의 이전 I0 parent와 canonical I0가 동일한 split임을 감사했다. I12 보고서의 TUM 템플릿 평가 단계명만 ETH3D의 I20으로 문서에서 수정했다. 추론·최적화·GT 수치는 수정하지 않았다.
- 재현용 다운로드 helper를 추가하고 평가 코드의 세션 임시 파일 의존을 제거한 뒤 I20을 `-002`로 재실행했다. 원래 `-001`을 보존했고 모든 GT metrics와 정렬 값이 정확히 동일함을 확인했다. RGB 최적화는 다시 하지 않았고 GT 결과를 보고 설정을 바꾸지 않았다.
- GPU는 호스트에서 실행했고 새 모델이나 패키지를 설치하지 않았다. 기존 libarchive로 압축을 풀고 공식 C++ 카메라 검증 도구만 로컬 컴파일했다. 이 결과는 공개 training 샘플 3장씩의 소규모 평가이며 ETH3D 전체 benchmark나 전체 SLAM 검증이 아니다. 선택·mask·scale을 GT 결과에 맞춰 반복 조정하지 않았다.

## 이미지·로그·출처

'''+ '\n'.join(references)+'''

[정확한 수치](summary.json) · [해시/순서/보존 검증](audit.json)

| 데이터 | 단계 | canonical run | 실행 판정 |
|---|---|---|---|
'''+ '\n'.join(stage_rows)+'''

대형 RGB/레이저 GT는 `data/eth3d_laser/`에, 모든 실행의 source·log·mask·NPZ/PLY/plane registry·support는 `results/global_planar_pointmap/<run_id>/stages/<code>/`에 보존했다. 다운로드 URL/크기/SHA는 I14, Omega GPU/checkpoint 출처는 I15, SAM/DINO 출처는 I1, GT 격자 대응·정렬·평가 배열은 I20에 있다.

재현 순서: 호스트 `eth3d_laser_download.py` → `eth3d_laser.py prepare` → 호스트 `infer` → `freeze` → 호스트 `segment` → `pipeline` → `eth3d_laser_evaluate.py` → `eth3d_laser_report.py`. Python 환경은 `.venvs/p2a/bin/python`, CPU thread 설정은 OPENBLAS_NUM_THREADS=2, OMP_NUM_THREADS=2다. GPU 단계는 I_HOST_GPU=1로 반드시 샌드박스 밖에서 실행한다. 다운로드 helper는 공식 archives와 immutable commit의 카메라/GT source를 data 캐시에 보관하며 완료된 파일을 재사용한다.
'''
    (output/'index.md').write_text(report)
    (DOC/'I14/index.md').write_text('# I14 — ETH3D RGB·보정 다운로드 및 triple 고정\n\n[계획](../../../vggt_omega_eth3d_laser_experiment_plan.md) · [최종 레이저 GT 결과](../I20/index.md)\n\n'+ '\n'.join(f"- [{ds}]({latest('I14',ds).parents[1].name}/report.md)" for ds in DATASETS)+'\n')
    (DOC/'I15/index.md').write_text('# I15 — ETH3D Omega 호스트 추론\n\n[최종 레이저 GT 결과](../I20/index.md)\n\n'+ '\n'.join(f"- [{ds}]({latest('I15',ds).parents[1].name}/report.md)" for ds in DATASETS)+'\n')
    print(json.dumps(dict(decisions=success,unique_file_hashes_verified=len(memo))))

if __name__=='__main__':run()
