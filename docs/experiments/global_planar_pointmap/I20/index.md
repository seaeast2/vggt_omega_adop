# ETH3D 실내 레이저 GT 전이 결과 — office / pipes

Kinect 깊이의 잔여 왜곡·센서 오차와 구분해 보기 위해 **서로 다른 실내 두 장면**에서 재실험했다. ETH3D의 FARO Focus X 330 레이저 스캔에서 가림·mask를 고려해 렌더한 camera-Z depth를 사용했다. 제공 RGB와 보정으로 **GT를 보지 않고 장면당 3장**을 선택하고, Omega 추론→SAM/DINO→FoV→자동 평면→named OR→평면 RGB 최적화→GT 평가까지 실행했다.

[사전 계획·데이터 조사](../../../vggt_omega_eth3d_laser_experiment_plan.md). [공식 데이터](https://eth3d.ethz.ch/datasets) · [공식 보정/depth 규약](https://eth3d.ethz.ch/documentation).

## 전체 GT 깊이 정확도

initial은 현재 FoV 초기 점군, plane_fixed는 named_OR 투영이다. 깊이는 baseline FIT의 공통 scale을 고정했고, 모든 군을 동일한 valid-GT validation 픽셀에서 평가했다. 단위 cm, 낮을수록 좋다.

| 장면 | 출력 | MAE ↓ | RMSE ↓ | AbsRel ↓ |
|---|---|---:|---:|---:|
| office | initial | 1.3286 | 3.4709 | 0.0065164 |
| office | plane_fixed | 1.6068 | 5.5629 | 0.0080843 |
| office | plane_distance | 1.9941 | 5.6804 | 0.0097368 |
| office | plane_distance_normal | 2.1235 | 5.2274 | 0.0102895 |
| office | retained | 1.6068 | 5.5629 | 0.0080843 |
| pipes | initial | 2.2731 | 3.6006 | 0.0109778 |
| pipes | plane_fixed | 2.2031 | 3.5890 | 0.0107216 |
| pipes | plane_distance | 2.3574 | 3.9110 | 0.0113421 |
| pipes | plane_distance_normal | 2.4325 | 4.0212 | 0.0116598 |
| pipes | retained | 2.2031 | 3.5890 | 0.0107216 |

장면별 사전 기준 판정: `{'eth3d-office': 'NO_CONFIRMED_GAIN', 'eth3d-pipes': 'NO_CONFIRMED_GAIN'}`.

- eth3d-office: 최적화 16개 평면·62,359점, optimized GT validation 2,913개. 전체 GT validation 23,187개, 전체 유효 GT 118,686/516,096. 보류 RGB 손실 상대 감소 -8.6243%, 최대 frustum 손실 0.0479%, retained=`I10_retained`.
- eth3d-pipes: 최적화 10개 평면·31,628점, optimized GT validation 830개. 전체 GT validation 8,142개, 전체 유효 GT 47,380/516,096. 보류 RGB 손실 상대 감소 -95.5918%, 최대 frustum 손실 0.0072%, retained=`I10_retained`.

사무실은 평면 고정 1.6068→거리·법선 2.1235 cm로 전체 MAE가 늘었지만, RMSE는 5.5629→5.2274 cm로 줄었다. screen MAE도 14.4314→11.7289 cm로 줄었으나 wall MAE는 0.5400→2.1235 cm로 늘었다. 전체 오차와 일부 영역의 효과를 구분한다.

배관 실내는 **초기→고정 평면만** 적용할 때 MAE 2.2731→2.2031 cm, RMSE 3.6006→3.5890 cm로 소폭 줄었다. 그러나 거리·법선 RGB 재정렬 뒤 MAE 2.4325 cm, RMSE 4.0212 cm로 늘었다. 장면에 따라 평면 투영의 영향은 달랐지만, RGB 재정렬의 전체 개선은 두 장면 모두 확인하지 못했다.

baseline FIT-only 공통 Sim(3) 후 대응 3D mean 오차(cm)는 office initial/fixed/거리·법선 = 3.2186/3.5278/4.0588, pipes = 2.8014/2.7736/3.0090이다. 깊이와 별도의 공통 정렬을 쓰는 보조 지표이며 같은 추세였다. 원본 GT 3×3 이웃이 모두 유효한 smooth 보조 mask는 sparse 레이저 depth 때문에 office 8점, pipes 0점뿐이라 경계 민감도 결론에는 사용하지 않는다.

## FIT/보류 RGB와 해석

| 장면 | 출력 | FIT photo 손실 ↓ | 보류 photo 손실 ↓ |
|---|---|---:|---:|
| office | plane_fixed | 0.967414 | 0.469773 |
| office | plane_distance | 0.905829 | 0.498612 |
| office | plane_distance_normal | 0.872082 | 0.510288 |
| pipes | plane_fixed | 0.482300 | 0.442111 |
| pipes | plane_distance | 0.483033 | 0.598064 |
| pipes | plane_distance_normal | 0.450752 | 0.864733 |

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

- **eth3d-office**: [선택 RGB](../I14/eth3d-office-I14-20261114-001/figures/selected_RGB.png) · [named OR 마스크](../I10/eth3d-office-I10-20261114-001/figures/named_OR_mask.png) · [GT 보고서](eth3d-office-I20-20261114-002/report.md) · [GT 오차 이미지](eth3d-office-I20-20261114-002/figures/gt_depth_error.png)
- **eth3d-pipes**: [선택 RGB](../I14/eth3d-pipes-I14-20261114-001/figures/selected_RGB.png) · [named OR 마스크](../I10/eth3d-pipes-I10-20261114-001/figures/named_OR_mask.png) · [GT 보고서](eth3d-pipes-I20-20261114-002/report.md) · [GT 오차 이미지](eth3d-pipes-I20-20261114-002/figures/gt_depth_error.png)

[정확한 수치](summary.json) · [해시/순서/보존 검증](audit.json)

| 데이터 | 단계 | canonical run | 실행 판정 |
|---|---|---|---|
| eth3d-office | I0 | [eth3d-office-I0-20261114-003](../I0/eth3d-office-I0-20261114-003/report.md) | NEW_SCENE_RGB_FIT_HOLDOUT_FROZEN |
| eth3d-office | I1 | [eth3d-office-I1-20261114-001](../I1/eth3d-office-I1-20261114-001/report.md) | FULL_IMAGE_CANDIDATES_TAGGED |
| eth3d-office | I2 | [eth3d-office-I2-20261114-001](../I2/eth3d-office-I2-20261114-001/report.md) | LOW_SUPPORT_PROPOSED_PRESERVED |
| eth3d-office | I3 | [eth3d-office-I3-20261114-001](../I3/eth3d-office-I3-20261114-001/report.md) | CANDIDATES_EVALUATED |
| eth3d-office | I4 | [eth3d-office-I4-20261114-001](../I4/eth3d-office-I4-20261114-001/report.md) | CONSERVATIVE_GLOBAL_IDS |
| eth3d-office | I10 | [eth3d-office-I10-20261114-001](../I10/eth3d-office-I10-20261114-001/report.md) | NAMED_OR_PLANE_TEST_EXECUTED |
| eth3d-office | I12 | [eth3d-office-I12-20261114-001](../I12/eth3d-office-I12-20261114-001/report.md) | RGB_PLANE_OPTIMIZATION_EXECUTED |
| eth3d-office | I14 | [eth3d-office-I14-20261114-001](../I14/eth3d-office-I14-20261114-001/report.md) | LASER_DATASET_RGB_TRIPLE_FROZEN |
| eth3d-office | I15 | [eth3d-office-I15-20261114-001](../I15/eth3d-office-I15-20261114-001/report.md) | NEW_SCENE_OMEGA_INFERRED |
| eth3d-office | I20 | [eth3d-office-I20-20261114-002](../I20/eth3d-office-I20-20261114-002/report.md) | NO_CONFIRMED_GAIN |
| eth3d-pipes | I0 | [eth3d-pipes-I0-20261114-002](../I0/eth3d-pipes-I0-20261114-002/report.md) | NEW_SCENE_RGB_FIT_HOLDOUT_FROZEN |
| eth3d-pipes | I1 | [eth3d-pipes-I1-20261114-001](../I1/eth3d-pipes-I1-20261114-001/report.md) | FULL_IMAGE_CANDIDATES_TAGGED |
| eth3d-pipes | I2 | [eth3d-pipes-I2-20261114-001](../I2/eth3d-pipes-I2-20261114-001/report.md) | LOW_SUPPORT_PROPOSED_PRESERVED |
| eth3d-pipes | I3 | [eth3d-pipes-I3-20261114-001](../I3/eth3d-pipes-I3-20261114-001/report.md) | CANDIDATES_EVALUATED |
| eth3d-pipes | I4 | [eth3d-pipes-I4-20261114-001](../I4/eth3d-pipes-I4-20261114-001/report.md) | CONSERVATIVE_GLOBAL_IDS |
| eth3d-pipes | I10 | [eth3d-pipes-I10-20261114-001](../I10/eth3d-pipes-I10-20261114-001/report.md) | NAMED_OR_PLANE_TEST_EXECUTED |
| eth3d-pipes | I12 | [eth3d-pipes-I12-20261114-001](../I12/eth3d-pipes-I12-20261114-001/report.md) | RGB_PLANE_OPTIMIZATION_EXECUTED |
| eth3d-pipes | I14 | [eth3d-pipes-I14-20261114-001](../I14/eth3d-pipes-I14-20261114-001/report.md) | LASER_DATASET_RGB_TRIPLE_FROZEN |
| eth3d-pipes | I15 | [eth3d-pipes-I15-20261114-001](../I15/eth3d-pipes-I15-20261114-001/report.md) | NEW_SCENE_OMEGA_INFERRED |
| eth3d-pipes | I20 | [eth3d-pipes-I20-20261114-002](../I20/eth3d-pipes-I20-20261114-002/report.md) | NO_CONFIRMED_GAIN |

대형 RGB/레이저 GT는 `data/eth3d_laser/`에, 모든 실행의 source·log·mask·NPZ/PLY/plane registry·support는 `results/global_planar_pointmap/<run_id>/stages/<code>/`에 보존했다. 다운로드 URL/크기/SHA는 I14, Omega GPU/checkpoint 출처는 I15, SAM/DINO 출처는 I1, GT 격자 대응·정렬·평가 배열은 I20에 있다.

재현 순서: 호스트 `eth3d_laser_download.py` → `eth3d_laser.py prepare` → 호스트 `infer` → `freeze` → 호스트 `segment` → `pipeline` → `eth3d_laser_evaluate.py` → `eth3d_laser_report.py`. Python 환경은 `.venvs/p2a/bin/python`, CPU thread 설정은 OPENBLAS_NUM_THREADS=2, OMP_NUM_THREADS=2다. GPU 단계는 I_HOST_GPU=1로 반드시 샌드박스 밖에서 실행한다. 다운로드 helper는 공식 archives와 immutable commit의 카메라/GT source를 data 캐시에 보관하며 완료된 파일을 재사용한다.
