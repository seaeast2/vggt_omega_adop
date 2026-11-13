# I0–I9 전역 자동 평면 pointmap 실행 결과

**최신 [I21 무보정 Omega raw 포함 비교](I21/index.md)**: ETH3D 2장면·TUM 2구간에 raw를 추가했다. 기존 initial은 FoV 보정 후이므로 `fov`로 구분한다. 깊이 Z와 3D 위치 오차를 나누고 모든 군에 같은 GT 마스크·공통 정렬을 적용했다. 3D 순위의 raw/FoV 표면 정렬 의존성이 있어 후보 점군에 맞추지 않는 camera-pose 공통 정렬도 보고한다. 기존 결과는 아래에 보존한다.

후속 **[ETH3D office/pipes 실내 레이저 GT 평가](I20/index.md)** 완료: 새로운 RGB에서 전체 분할·평면·RGB 최적화를 재실행했다. 초기/고정 평면/거리·법선 MAE(cm)는 office 1.3286/1.6068/2.1235, pipes 2.2731/2.2031/2.4325다. pipes의 고정 평면은 소폭 개선됐으나 RGB 재정렬의 전체 개선 기준은 두 장면 모두 실패했다. 왜곡 격자 대응은 공식 C++ 구현으로 검증했다.

후속 **[I12–I13 평면 거리·법선의 RGB 미분 최적화](I13/index.md)** 완료: 거리만/거리·법선 군을 실행했으나 전체 GT 정확도 개선이 없었다. 평면 고정→거리·법선 MAE는 주 구간 5.5114→6.1364 cm, 추가 구간 2.1514→2.4524 cm. 보류 RGB 조건도 실패해 기존 I10 retained를 유지했다. [사전 계획](../../vggt_omega_plane_photometric_experiment_plan.md).

후속 **[I11 현재 I10의 TUM GT 평가](I11/index.md)**: baseline FIT의 공통 scale을 고정해 validation에서 평가했다. 보정 전→named OR 깊이 MAE는 주 구간 5.3767→5.5114 cm, 추가 구간 2.0196→2.1514 cm로 전체 정확도 개선이 없었다. 아래 GT 미평가 표기는 당시 I0–I9 실행의 상태이며, I11은 별도의 사후 평가다.

후속 [I10 named OR 평면 테스트](I10/index.md): `wall/table/screen`만 허용하고 대응 표면의 named 정보를 OR했다. 주 구간은 가시성 통과, 추가 실내는 기준 초과로 initial 유지. 박스·원통·구 보정은 적용하지 않았다. 아래 I0–I9/A4 판정은 기존 실행 결과로 보존한다.

추가 시각 검토: [주 구간 unknown 표시](I1u/tum-freiburg1_desk-I1u-20261113-001/report.md) · [추가 실내 unknown 표시](I1u/tum-freiburg1_desk-extra-I1u-20261113-001/report.md). 빨강은 이름 있는 마스크를 뺀 unknown-only, 초록은 이름 있는 마스크, 파랑은 미포함이다. 평면 판정이나 새로운 보정 결과가 아니다.

주 구간 30/40/50과 추가 실내 100/110/120에서 I0–I9 및 A0–A6 비교를 실행했다. 각 구간은 589,824개 원본 관측을 유지한다. 실험 실행 완료와 알고리즘의 과학적 성공은 구분한다. GT_NOT_EVALUATED이며 실제 소속/구조 정확도·전체 SLAM 정확도의 향상을 주장하지 않는다.

**자동 주 결과 A4는 두 구간 모두 가시성 보존 기준을 통과하지 못해 retained=initial이다.** 평면식 일치 기술 검증은 통과했지만 화면 전체 개선은 확정하지 않았다.

| 구간 | 수용 관측 | 최대 frustum loss | retained |
| --- | --- | --- | --- |
| tum-freiburg1_desk | 480,284 (81.4284%) | 25.1102% | initial |
| tum-freiburg1_desk-extra | 467,051 (79.1848%) | 0.9381% | initial |

B1은 기존 C3a 실제 proposed이고 B1s는 공통 fit/보류 분리를 적용한 새 I2 proposed다. 자동 군은 B1s에서 시작한다. 기존 C3a split 재현은 I0에서 별도 검증했다. historical fit와 새 보류의 겹침 때문에 B1을 새 독립 보류 기준으로 해석하지 않는다.

| 구간 | 단계 | canonical run·보고서 | stage wall time | 판정 |
| --- | --- | --- | --- | --- |
| desk | I0 | [tum-freiburg1_desk-I0-20261113-002](I0/tum-freiburg1_desk-I0-20261113-002/report.md) | 2.14s | CONTRACT_FROZEN_WITH_EXPLICIT_SPLIT_AMENDMENT |
| desk | I1 | [tum-freiburg1_desk-I1-20261113-001](I1/tum-freiburg1_desk-I1-20261113-001/report.md) | 547.14s | FULL_IMAGE_CANDIDATES_TAGGED |
| desk | I2 | [tum-freiburg1_desk-I2-20261113-001](I2/tum-freiburg1_desk-I2-20261113-001/report.md) | 2.06s | LOW_SUPPORT_PROPOSED_PRESERVED |
| desk | I3 | [tum-freiburg1_desk-I3-20261113-002](I3/tum-freiburg1_desk-I3-20261113-002/report.md) | 14.46s | CANDIDATES_EVALUATED |
| desk | I4 | [tum-freiburg1_desk-I4-20261113-002](I4/tum-freiburg1_desk-I4-20261113-002/report.md) | 70.36s | CONSERVATIVE_GLOBAL_IDS |
| desk | I5 | [tum-freiburg1_desk-I5-20261113-003](I5/tum-freiburg1_desk-I5-20261113-003/report.md) | 5.13s | RELATION_EVIDENCE_INSUFFICIENT_FREE_RETAINED |
| desk | I6 | [tum-freiburg1_desk-I6-20261113-004](I6/tum-freiburg1_desk-I6-20261113-004/report.md) | 768.45s | JOINT_SOLVE_EXECUTED |
| desk | I7 | [tum-freiburg1_desk-I7-20261113-002](I7/tum-freiburg1_desk-I7-20261113-002/report.md) | 3.01s | HARD_REPROJECTION_PASSED_RETAIN_INITIAL |
| desk | I8 | [tum-freiburg1_desk-I8-20261113-002](I8/tum-freiburg1_desk-I8-20261113-002/report.md) | 165.24s | STATE_BOUND_BUNDLES_EXPORTED |
| desk | I9 | [tum-freiburg1_desk-I9-20261113-001](I9/tum-freiburg1_desk-I9-20261113-001/report.md) | 26.81s | COMPARISON_EXECUTED_NO_GT_ACCURACY_CLAIM |
| desk-extra | I0 | [tum-freiburg1_desk-I0-20261113-002](I0/tum-freiburg1_desk-I0-20261113-002/report.md) | 2.14s | CONTRACT_FROZEN_WITH_EXPLICIT_SPLIT_AMENDMENT |
| desk-extra | I1 | [tum-freiburg1_desk-extra-I1-20261113-001](I1/tum-freiburg1_desk-extra-I1-20261113-001/report.md) | 948.60s | FULL_IMAGE_CANDIDATES_TAGGED |
| desk-extra | I2 | [tum-freiburg1_desk-extra-I2-20261113-001](I2/tum-freiburg1_desk-extra-I2-20261113-001/report.md) | 1.93s | FOV_PROPOSED |
| desk-extra | I3 | [tum-freiburg1_desk-extra-I3-20261113-002](I3/tum-freiburg1_desk-extra-I3-20261113-002/report.md) | 16.33s | CANDIDATES_EVALUATED |
| desk-extra | I4 | [tum-freiburg1_desk-extra-I4-20261113-002](I4/tum-freiburg1_desk-extra-I4-20261113-002/report.md) | 184.08s | CONSERVATIVE_GLOBAL_IDS |
| desk-extra | I5 | [tum-freiburg1_desk-extra-I5-20261113-002](I5/tum-freiburg1_desk-extra-I5-20261113-002/report.md) | 5.28s | RELATION_EVIDENCE_INSUFFICIENT_FREE_RETAINED |
| desk-extra | I6 | [tum-freiburg1_desk-extra-I6-20261113-003](I6/tum-freiburg1_desk-extra-I6-20261113-003/report.md) | 1186.19s | JOINT_SOLVE_EXECUTED |
| desk-extra | I7 | [tum-freiburg1_desk-extra-I7-20261113-001](I7/tum-freiburg1_desk-extra-I7-20261113-001/report.md) | 3.23s | HARD_REPROJECTION_PASSED_RETAIN_INITIAL |
| desk-extra | I8 | [tum-freiburg1_desk-extra-I8-20261113-001](I8/tum-freiburg1_desk-extra-I8-20261113-001/report.md) | 104.10s | STATE_BOUND_BUNDLES_EXPORTED |
| desk-extra | I9 | [tum-freiburg1_desk-extra-I9-20261113-001](I9/tum-freiburg1_desk-extra-I9-20261113-001/report.md) | 26.74s | COMPARISON_EXECUTED_NO_GT_ACCURACY_CLAIM |

## tum-freiburg1_desk

확정·수용 관측 480,284/589,824 (81.4284%). 최대 frustum loss 25.1102%; retained=`initial`.

고정 보류 camera pair 01/02/12 상대 3D median: B1s `[0.007974095155875353, 0.005394425104897326, 0.005732453966444455]`, A4 `[0.511895842237216, 0.20330515398503884, 0.008402806863276656]`. 이는 동일 joint inference의 내부 정합이며 GT 오차가 아니다.

PLY 검토 폴더: `/home/hlee221212/works/gradresearch/vggt_omega_adop/results/global_planar_pointmap/ply_review/tum-freiburg1_desk-I9-20261113-001`. pixel RGB/frame/plane 색을 구분한 B0/B1/B1s/A0–A6 파일이 있다.

## tum-freiburg1_desk-extra

확정·수용 관측 467,051/589,824 (79.1848%). 최대 frustum loss 0.9381%; retained=`initial`.

고정 보류 camera pair 01/02/12 상대 3D median: B1s `[0.00592655524934526, 0.004195071390946612, 0.004614521340609069]`, A4 `[0.007789175314084128, 0.008077345150518, 0.006970445219176781]`. 이는 동일 joint inference의 내부 정합이며 GT 오차가 아니다.

PLY 검토 폴더: `/home/hlee221212/works/gradresearch/vggt_omega_adop/results/global_planar_pointmap/ply_review/tum-freiburg1_desk-extra-I9-20261113-001`. pixel RGB/frame/plane 색을 구분한 B0/B1/B1s/A0–A6 파일이 있다.

## 보존·재현성과 제한

- I1 GPU는 호스트에서 실행했고 CPU geometry와 환경 기록을 구분했다. 모델 SHA256와 source revision은 I1 보고서에 있다.
- I3 보류 XYZ의 분할 유입을 고친 뒤 후보·모델 선택·소속·normal의 보류 perturbation 불변 검증을 통과했다. 초기·중단 실행은 제외 목록에 남겼다.
- 소속 변경 뒤 effective fit의 최소 50개/퇴화 조건도 검사한다. 이 조건은 동결된 원래 fit 기준을 적용한 정확성 수정이며 이동 크기 gate가 아니다.
- initial/proposed/retained bundle은 각각 state/hash로 연결하며 RGB/ID/UV/K/pose·비대상 XYZ를 검사한다. PLY 속성 재읽기·경계 round-trip·이전 checkpoint 복원·잘못된 registry export 거부를 검사했다.
- 경계의 물리 edge/가림 분류는 provisional이다. 미관측 hole을 실제 구멍으로 확정하거나 watertight mesh를 생성하지 않았다.
- semantic tag는 모델 예측이며 수동 category/plane annotation이 없다. 추가 실내는 과거 사용 구간이고 threshold를 바꾸는 데 사용하지 않았다.
- 비용은 각 stage의 wall time/peak RSS이며 모델 GPU peak는 shared process 기준이다. 병렬 실행 시간은 단순 합산한 전체 경과시간과 다르다.

SAM inference와 pre-NMS 보존/계층 처리의 세부 CPU/GPU 시간은 묶여 있다. A6의 end-to-end GPU 비용 절감량은 별도로 측정하지 않았다. plane 불확실성은 원본 fit에 조건부인 근사이며 공동 solve의 보정된 posterior가 아니다. 선택 민감도 I1a/I2a와 야외 I9b는 이번 필수 실행 범위에 합산하지 않았다.

실행 코드의 권위 있는 원본은 각 stage `artifacts/source`와 해당 manifest hash다. 주 구간 retained bundle의 중복 code 관측 필드 한 곳은 직렬화 시점의 후속 I9 그림 편집 버전을 기록했다. 실행 snapshot을 별도로 특정했고 geometry/bundle 함수 AST가 동일함을 검증했다. 수치·원본 bundle을 바꾸지 않은 [출처 보완 기록](provenance_amendment.json)을 함께 보존한다.

[수치 원본](canonical_results.json) · [제외·중단 실행](excluded_runs.json) · [보류 유입 회귀 검증](holdout_perturbation_audit.json) · [별도 육안 검토](visual_review.json) · [최종 보존 검사](final_audit.json) · [환경 snapshot](environment_snapshot.json)
