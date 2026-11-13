# I21 — 무보정 Omega raw를 포함한 공정 비교

**무보정 Omega raw를 4개 구간 모두의 비교군에 추가했다.** 기존 initial은 FoV 보정 후였으므로 이 문서에서는 `fov`로 표시한다. 이후는 평면 고정, 평면 거리만 조정, 평면 거리·법선 조정, 기존 retained다. 기존 출력·판정·실패 기록은 수정하지 않았다.

raw는 Omega가 예측한 depth·K·pose를 그대로 역투영한 점군이며 저장 캐시에 별도 XYZ head는 없다. FoV/평면/융합/점 필터 없이 모든 관측을 유지했다. I2에 저장된 원본 beta1 점군과 bitwise 동일함을 확인했고, 원래 모델 좌표의 raw NPZ/PLY를 새 run에 보존했다. GPU 재추론은 하지 않았다.

## camera-Z 깊이 MAE (cm)

raw FIT의 공통 scale을 모든 군에 적용하고 동일 validation/유효 GT mask로 평가했다. 낮을수록 좋다.

| 데이터 | omega_raw | fov | plane_fixed | 거리 | 거리·법선 | retained |
|---|---:|---:|---:|---:|---:|---:|
| eth3d-office | 1.3286 | 1.3286 | 1.6068 | 1.9941 | 2.1235 | 1.6068 |
| eth3d-pipes | 2.2731 | 2.2731 | 2.2031 | 2.3574 | 2.4325 | 2.2031 |
| tum-freiburg1_desk | 5.3767 | 5.3767 | 5.5114 | 6.2751 | 6.1364 | 5.5114 |
| tum-freiburg1_desk-extra | 2.0196 | 2.0196 | 2.1514 | 2.6439 | 2.4524 | 2.0196 |

raw와 FoV는 원래 camera-Z를 유지하므로 깊이 MAE가 사실상 동일하다. 따라서 FoV 보정의 영향을 보려면 다음 3D 지표를 함께 봐야 한다.

## 대응 3D 점 mean 오차 (cm)

**카메라 pose만으로 구한 하나의 공통 Sim(3)**를 모든 비교군에 적용했다. 회전은 카메라 자세에서, scale/translation은 중심 위치에서 구하여 어떤 후보 점군이나 surface GT에도 맞추지 않았다. 이 변환은 평가용 gauge 정렬이며 raw 저장 좌표를 수정하지 않는다. 각 군의 개별 정렬을 허용하지 않았다. 카메라 baseline이 짧고 pose 오차가 있을 수 있으므로 정렬의 중심/자세 잔차도 JSON에 기록했다. 깊이 지표와 구분한다.

| 데이터 | omega_raw | fov | plane_fixed | 거리 | 거리·법선 | retained |
|---|---:|---:|---:|---:|---:|---:|
| eth3d-office | 4.4061 | 3.6670 | 3.9814 | 4.3633 | 4.4782 | 3.9814 |
| eth3d-pipes | 10.6720 | 8.3758 | 8.3157 | 8.3776 | 8.1417 | 8.3157 |
| tum-freiburg1_desk | 58.3343 | 59.8528 | 60.2172 | 60.3344 | 60.3194 | 60.2172 |
| tum-freiburg1_desk-extra | 11.7157 | 9.7491 | 9.8275 | 10.3249 | 10.1151 | 9.7491 |

각 run에는 raw 표면 FIT 및 기존 FoV 표면 FIT 공통 정렬 표도 함께 있다. 기존 FoV 표에서 과거의 비raw 지표가 재현됨을 확인했다. 첫 I21에서 두 표면 정렬 사이에 3D 순위가 뒤집히는 경우를 확인해, 후보 표면에 의존하지 않는 camera-pose 정렬을 3D 주 표에 추가했다. 첫 실행은 보존했다. 이는 정렬 민감도 분석이며 비교군마다 재정렬한 결과가 아니다. 깊이 scale의 FIT/validation은 분리했고, pose 정렬에는 surface GT 평가 픽셀을 쓰지 않았다. 새 GT 마스크·모델 보정·optimizer 실행·GT 기반 retained 선택은 하지 않았다.

카메라 pose 기준 3D 수치는 depth shape뿐 아니라 pose scale 오차도 포함한다. 특히 TUM 주 구간은 camera baseline scale 약 1.838과 depth scale 약 1.318의 차이가 커 3D mean이 약 58–60 cm로 커진다. 표면 정렬 표의 수 cm와 직접 혼합하거나, 정렬에 따른 순위 변화만으로 보정 효과를 확정하지 않는다. 카메라 기준 정렬이 표면을 편들지 않는다는 것과 그 scale이 짧은 baseline에서 정확히 추정됐다는 것은 별개다. scale·중심·자세 잔차를 run별 alignment JSON에 함께 기록했다.

## 보고서와 출처

- [eth3d-office](eth3d-office-I21-20261114-002/report.md) · [GT 오차 이미지](eth3d-office-I21-20261114-002/figures/raw_fov_optimized_GT.png)
- [eth3d-pipes](eth3d-pipes-I21-20261114-002/report.md) · [GT 오차 이미지](eth3d-pipes-I21-20261114-002/figures/raw_fov_optimized_GT.png)
- [tum-freiburg1_desk](tum-freiburg1_desk-I21-20261114-002/report.md) · [GT 오차 이미지](tum-freiburg1_desk-I21-20261114-002/figures/raw_fov_optimized_GT.png)
- [tum-freiburg1_desk-extra](tum-freiburg1_desk-extra-I21-20261114-002/report.md) · [GT 오차 이미지](tum-freiburg1_desk-extra-I21-20261114-002/figures/raw_fov_optimized_GT.png)

[전체 정확한 수치·입력 hash·정렬·보존 검증](summary.json)

GT는 ETH3D office/pipes의 FARO 레이저-rendered depth 및 TUM 두 구간의 Kinect depth다. 기존 보정·왜곡 좌표 매핑·센서 오차·희소 GT·소규모 표본·FoV 지원 부족 등의 제한은 그대로다. 이번에는 비교군 누락을 수정한 사후 평가이며 통계적 유의성이나 전체 SLAM 일반화를 주장하지 않는다.

재현: `OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/raw_baseline.py`. 기존 I12/I11/I20 캐시가 필요하다. raw 파일은 각 I21 stage의 `artifacts/omega_raw/pointmap.npz`, `pixel_rgb.ply`다. 기존 raw/FoV/평면 결과 파일은 읽기 전용으로 사용했다.
