"""Build a Korean cross-stage report from sealed metrics, without changing decisions."""
import json
from pathlib import Path
import common as c


def reports():
    docs=c.ROOT/'docs/experiments/camera_fov_alignment'
    rows=[]
    for manifest in sorted(docs.glob('*/*/manifest.json')):
        m=json.loads(manifest.read_text())
        if m['status']=='completed':
            metrics=json.loads((manifest.parent/'evaluation/metrics.json').read_text())
            rows.append((m,metrics,manifest.parent))
    return docs,rows


def main():
    docs,rows=reports()
    by={(m['experiment_code'],m['dataset']):(m,v,p) for m,v,p in rows}
    output='''# FoV 보정·Pointmap 정렬·색/깊이 융합 종합 결과

실행 기간: 2026-11-12~13 KST. **C0~C5의 실행·평가와 필요한 보조 검증을 완료했다.** 실행 완료와 효과 확인은 별개다. 실패·지원 부족·초기값 선택·탐색적 보완을 모두 보존했다.

FoV 변경 후 원본 Depth를 다시 역투영하는 파이프라인과 색/깊이 융합을 실제 구현·검증했다. 드론 일부 설정에서 보정에 사용하지 않은 대응점의 **내부 3D 정합성은 개선**됐다. 그러나 **깊이축 정합성 개선의 사전 기준과, coverage까지 보존하는 점군 압축 기준은 통과하지 못했다.** 실제 3D 정확도나 벽 층 해결, 연속 SLAM 성능을 입증한 결과는 아니다.

## 1. 단계별 결과

| 단계 | 결과 |
| --- | --- |
| C0 | 역투영·합성 복구·solver 검증 통과. 최초 최근접 검색 검증 실패를 보존하고 C0a에서 교정 |
| C0a/C0b | 정확한 BF 검색 대조, 순수 회전·평면·평행·동일 관측의 rank 및 지원 부족 제어 통과 |
| C1/C1a | 실내 SIFT·ORB·AKAZE 모두 모든 쌍의 지원 조건을 충족하지 못함 |
| C2/C3 | 정식 실내 보정은 지원 gate로 β=1 유지. 보정 성공으로 보고하지 않음 |
| C2a/C3a | 같은 sparse SIFT 관측에서 실제 solver 제안 계산. 저지원 탐색 진단이며 효과 확인으로 승격하지 않음 |
| C4 | 두 드론 장면에서 지원·rank 통과. AMtown01 공통 1변수 내부 3D 개선. 원래 6변수 정책은 coverage 때문에 초기값 선택 |
| C4a | 같은 coverage 기준에서 고정 선분 후보를 추가한 탐색 보완. 양 장면 내부 3D 개선, 깊이축 목표 기준 미충족 |
| C5/C5b | 실내·드론 대표점 수 축소 확인. 공통 영역 Z 변화는 예산 내지만 이전 카메라 coverage 손실 때문에 압축 기준 미달 |
| C5a/C5c | E0c 정확 재현·색/깊이 gate 제어, 전체 파일·파라미터·CSR·PLY 종합 검증 |

## 2. 실내의 지원 부족

원래 실내 SIFT 유효 대응은 0↔1: 30개, 0↔2: 11개, 1↔2: 16개이며 validation은 각각 6/3/1개다. 최소 100개 및 fit/validation·공간 분포 조건을 낮추지 않았다. ORB와 AKAZE는 일부 쌍을 늘렸지만 모든 쌍을 통과하지 못했다. 원래 C2/C3가 계수를 적용하지 않은 이유는 수식 오류가 아니라 사전 정의한 관측 지원 부족이다.

C2a는 실제 공통 β≈1.079055로 수렴했다. C3a도 6개 제안값을 구했지만 coverage 조건을 만족한 후보가 초기값뿐이었다. 이 소수 대응 진단은 카메라 보정의 정확성이나 실내 벽 층 해결의 근거로 사용하지 않는다. 의미가 검증된 벽 ROI는 확보하지 않았고 고정 중앙 ROI의 층 통계는 물체·가림을 포함한다.

## 3. 드론 FoV 보정

아래 감소율은 **고정 validation 대응의 양방향 상대 거리 median**이다. 카메라 쌍과 방향에 동일 가중치를 적용한다. 양수는 감소, 음수는 악화다. source Z-depth는 불변이며 Z 열은 다른 프레임 점과의 양방향 camera-Z 차이다.

| 장면 | 절차 | 3D median 감소 | Z median 감소 | 선택 | 판정·보고서 |
| --- | --- | --- | --- | --- | --- |
'''
    for dataset in ['hkairport01','amtown01']:
        for code in ['C4','C4a']:
            m,metric,parent=by[(code,dataset)]
            arms=[('공통 1변수',metric['common_1var']),('프레임별 6변수',metric['per_camera_6var'])] if code=='C4' else [('6변수·고정 선분 보조',metric)]
            for label,arm in arms:
                before=arm['geometry_before']['validation'];after=arm['geometry_after']['validation']
                g3=100*(1-after['relative_3d']['median']/before['relative_3d']['median'])
                gz=100*(1-after['relative_z']['median']/before['relative_z']['median'])
                link=(parent/'report.md').relative_to(docs)
                output+=f'| {dataset} | {code} {label} | {g3:+.3f}% | {gz:+.3f}% | {arm["selected_iteration"]} | [{arm["decision"]}]({link}) |\n'
    output+='''
원래 6변수 C4는 solver가 수렴했지만 저장된 IRLS 후보의 coverage 조건 때문에 초기값을 선택했다. 이는 FoV가 언제나 효과 없다는 뜻은 아니다. C4a는 α=0,1/16,…,1의 고정 후보로 이를 보완했으며 결과 확인 후 추가한 탐색적 amendment다. validation/GT로 α를 선택하지 않았지만 새 독립 데이터 검증은 아니다.

**깊이축 목표는 미충족:** HKairport01의 공통 1변수는 Z가 약 7% 줄어도 전체 3D가 악화했다. C4a의 전체 3D 개선도 Z에는 거의 효과가 없거나 소폭 악화했다. AMtown01의 Z 감소는 약 1% 미만으로 사전 5% 기준에 못 미쳤다. FoV는 자기 카메라의 Z-depth를 수정하지 않으므로 이 결과를 Depth 오차 교정으로 해석하지 않는다.

## 4. 점군 융합과 압축

색은 원본 RGB 각 채널의 그룹 범위 ≤30, 깊이는 새 카메라에서 **모든 원본 구성점과 현재 대표점**의 Z 범위/새 Depth ≤3%를 적용했다. 현재 대표점당 가중치 1로 Z를 평균하고, 새 owner의 원본 RGB를 표시한다. 프레임 팔레트를 색 gate로 쓰거나 원본 관측 색을 평균하지 않았다. 최종 그룹의 모든 관측과 출처 membership를 보존했다.

| 장면 | 절차·arm | 입력 점 | 융합 대표점 | 감소 | 최대 coverage 손실 | 판정·보고서 |
| --- | --- | --- | --- | --- | --- | --- |
'''
    artifacts=[]
    for code,dataset,arm_name in [('C5','tum-freiburg1_desk','B'),('C5','hkairport01','B'),
            ('C5','amtown01','B'),('C5b','hkairport01','D'),('C5b','amtown01','D')]:
        m,metric,parent=by[(code,dataset)];arm=metric['arms'][arm_name]
        comparison=metric['comparisons']['A_to_B' if arm_name=='B' else 'C_to_D']
        loss=max(r['coverage_loss_fraction'] for r in comparison['cameras'])
        link=(parent/'report.md').relative_to(docs)
        output+=f'| {dataset} | {code} {arm_name} | {arm["raw_observations"]:,} | {arm["representative_points"]:,} | {arm["reduction_fraction"]:.3%} | {loss*100:.3f}%p | [{comparison["decision"]}]({link}) |\n'
        stage=c.ROOT/'results/camera_fov_alignment'/m['run_id']/'stages'/code
        for name in ['all_source.ply','all_rgb.ply','map.npz']:
            record=c.record(stage/'artifacts/arms'/arm_name/name)
            artifacts.append(record|{'relative_path':str(Path(record['path']).relative_to(c.ROOT)),
                'dataset':dataset,'experiment_code':code,'arm':arm_name})
    output+='''
실내 C5의 C/D는 정식 FoV 지원 부족으로 미평가다. 원래 드론 C5는 C4 6변수 선택값이 초기값이므로 C=A, D=B다. 실제 보정 후의 융합 비교는 **C5b D**이며 원래 결과를 대체하지 않는다.

모든 융합 비교에서 공통 유효 픽셀의 front-Z 변화 p90은 3% 이하였지만, 이전 카메라에서 약 2.6~7.0%p의 픽셀이 사라져 0.5%p 제한을 초과했다. 최신 카메라는 새 픽셀마다 대표점을 남기므로 coverage 100%를 유지한다. 따라서 점 수는 크게 줄었지만 **모든 시점의 표면 지지를 보존하는 압축으로는 미통과**다. 공통 픽셀의 작은 Z 오차만 제시하면 사라진 픽셀을 놓치므로 두 결과를 함께 제시했다.

지도 core 배열의 논리 크기·provenance 포함 크기·파일 크기·실행 시간·실행 전체 peak RSS를 각 보고서/JSON에 기록했다. 원본 관측 보관 비용을 포함한 총 RAM 감소나 arm별 peak RSS, 장기 SLAM 메모리 안정성을 입증한 것은 아니다. 순차 평균은 처리 순서 0→1→2에 의존하며 후속 pose/FoV 보정 때는 원본 관측에서 재구성할 수 있다.

## 5. 파일과 육안 확인

대형 PLY/NPZ·중간 단계·투영 Z/출처 버퍼는 호스트의 `results/camera_fov_alignment/{run}/stages/{code}/`에 보관했다. GitHub에는 코드·보고서·그림·수치·manifest 해시를 저장했다. [대표 산출물 경로·크기·SHA-256](artifact_index.json)에 실제 파일 경로가 있다.

'''
    for code,dataset,filename,label in [
            ('C5','tum-freiburg1_desk','fusion_rgb_comparison.png','실내 RGB·융합 비교'),
            ('C4a','hkairport01','6var_source_comparison.png','HKairport01 보정 전후 출처 색'),
            ('C4a','amtown01','6var_source_comparison.png','AMtown01 보정 전후 출처 색'),
            ('C5b','hkairport01','fusion_source_comparison.png','HKairport01 보정·융합 네 경우'),
            ('C5b','amtown01','fusion_rgb_comparison.png','AMtown01 보정·융합 네 경우')]:
        parent=by[(code,dataset)][2]
        output+=f'- [{label}]({(parent/"figures"/filename).relative_to(docs)})\n'
    output+='''

모든 주 패널은 처리 원본과 같은 512×384 또는 512×432이다. 표시 도구가 패널 전체를 축소하면 개별 이미지 원본을 연다. 대표점 출처 색은 최신 owner이며, 여러 프레임에서 함께 관측됐는지는 membership로 확인한다. 색이 파랑으로 모였다는 사실 자체는 정합성 개선 증거가 아니다.

## 6. 검증·한계

'''
    m,verification,parent=by[('C5c','synthetic')]
    output+=f'종합 검증 [{verification["decision"]}]({(parent/"report.md").relative_to(docs)}): 완료 실행 {len(verification["completed_runs_verified"])}개, 해시 기록 {verification["artifact_hash_records_verified"]:,}개, 카메라 파라미터 파일 {len(verification["camera_parameter_files_verified"])}개, raw/융합 지도 {len(verification["fusion_maps_verified"])}개를 재검증했다. C5c 자체를 포함하면 완료 실행은 {len(rows)}개이며 최초 C0 기술 실패는 별도 보존했다.\n\n'
    output+='''GT 기하 정확도·미사용 카메라 일반화·연속 SLAM은 평가하지 않았다. TUM의 고정 자기 Depth GT RMSE는 FoV 효과를 측정하지 못하며, UAVScenes의 LiDAR/pose/calibration 좌표 정합은 이 평가에 검증되지 않았다. 내부 residual 감소를 물리적인 카메라 참값 복구나 벽 층 해결로 확대하지 않는다.

추가 패키지 설치·모델 재추론 없이 호스트 CPU로 수행했다. C0~C5의 현재 비교를 마쳤으며 별도 후속 실험을 자동으로 시작하지 않는다. [전체 실행 이력](index.md), [보조 검증·amendment](amendments.md), [재현 명령](../../../experiments/camera_fov_alignment/README.md)을 보존했다.
'''
    c.json_write(docs/'artifact_index.json',artifacts)
    (docs/'summary.md').write_text(output)
    print(json.dumps({'summary':str(docs/'summary.md'),'completed_runs':len(rows),
        'representative_artifacts':len(artifacts)},ensure_ascii=False))


if __name__=='__main__':main()
