# VGGT-Ω Pointmap 정렬·보정 실험

대학원 졸업논문을 위한 실험 저장소다. 여러 RGB 이미지로 추론한 프레임별 pointmap의 불일치와 벽의 층 분리를 진단하고, 점군 융합·RGB 기반 정점 이동·FoV 보정·점/선/깊이 제약을 비교했다.

**C3a의 실제 FoV 제안 점군을 기준으로 H0~H6 실행을 완료했다.** 영상 분할·독립/공유 평면·hard/soft 깊이 보정을 비교했다. 기본 군은 공유 평면 지지가 부족했고, 중복 마스크 정리 보조 군은 앞의 두 카메라가 공유하는 벽 하나를 보정했다. 벽 두께와 층 간격 지표는 상충했으며 GT 정확도 개선은 미확인이다.

후속 **I0~I9 전체 화면 자동 평면 파이프라인**과 **I10 named OR 평면 테스트**를 실행했다. I10은 wall/table/screen만 투영하고 모든 view에서 이름 지지가 없는 영역을 제외한다. **I11 TUM 센서 GT 평가에서는 전체 깊이 정확도가 개선되지 않았다.** 보정 전→OR의 scale 정렬 MAE는 주 구간 5.3767→5.5114 cm, 추가 구간 2.0196→2.1514 cm다. 추가 구간 retained는 기존 가시성 판정에 따라 initial이다. [전체 계획](docs/vggt_omega_global_planar_pointmap_experiment_plan.md) · [GT 평가](docs/experiments/global_planar_pointmap/I11/index.md)

**I12~I13에서는 평면의 거리·법선을 타 시점 RGB로 미분 최적화하고 GT로 평가했다.** 두 구간 모두 보류 RGB와 전체 깊이 정확도가 악화돼 기존 retained를 유지했다. 평면 고정→거리·법선 최적화 MAE는 주 구간 5.5114→6.1364 cm, 추가 구간 2.1514→2.4524 cm다. [계획](docs/vggt_omega_plane_photometric_experiment_plan.md) · [실행 결과·오차 이미지](docs/experiments/global_planar_pointmap/I13/index.md)

**ETH3D office/pipes의 레이저 GT로 새 실내 2장면을 재검증했다.** 초기/평면 고정/거리·법선의 MAE는 office 1.3286/1.6068/2.1235 cm, pipes 2.2731/2.2031/2.4325 cm다. pipes의 고정 평면은 소폭 개선됐지만 RGB 재정렬은 두 장면 모두 전체 개선 기준을 실패했다. 공식 왜곡 모델·C++ 구현·RGB 대응을 검증했으며 기존 retained를 유지했다. [계획·데이터 조사](docs/vggt_omega_eth3d_laser_experiment_plan.md) · [레이저 GT 결과·이미지](docs/experiments/global_planar_pointmap/I20/index.md)

최종 갱신: 2026-11-14 KST. 실행 완료, 사전 기준 통과, 육안 개선, GT 정확도는 구분해서 기록한다.

**I21에서 무보정 Omega raw를 ETH3D 2장면과 TUM 2구간 모두에 추가했다.** 기존 initial은 `fov`로 구분했다. raw는 원래 depth·K·pose 그대로 역투영한 전체 점군이며 원본 beta1 캐시와 bitwise 동일하다. depth Z는 FoV와 같지만 3D 점 오차는 다르다. 공정 비교를 위해 카메라 pose만으로 구한 공통 3D 정렬과 raw/FoV 표면 기준 정렬의 민감도 표를 함께 보고한다. [raw 포함 비교표·출처·오차 이미지](docs/experiments/global_planar_pointmap/I21/index.md)

## 1. 데이터와 비교 조건

| 데이터 | 용도 | 입력 |
| --- | --- | --- |
| TUM `freiburg1_desk` | 주 실내 실험 | 원본 RGB index 30/40/50, 3장 공동 추론 |
| 같은 실내의 추가 구간 | G5a의 고정 구간 재검증 | index 100/110/120, 3장 공동 추론 |
| ETH3D `office`, `pipes` | 독립 레이저 스캔에서 렌더한 GT로 새 실내 전이 평가 | RGB 공시성으로 선택한 각 3장, 512×336 공동 추론, FARO Focus X330 GT |
| UAVScenes `HKairport01`, `AMtown01` | 야외·드론 전이 비교 | 기존 E0d에서 고정한 각 3장 |
| 일반 VGGT | 같은 실내 원본의 모델 출력 육안 비교 | 주 실내와 같은 RGB 3장, V0 |

VGGT-Ω 주 실내 출력은 512×384×3 = **589,824개 관측점**이다. 일반 VGGT는 공식 전처리 격자 518×392×3 = **609,168점**으로, 점 수·해상도·좌표계가 다르다. 두 모델의 점군을 직접 점별 차분하거나 강제로 같은 scale에 맞춘 결과가 아니다.

## 2. 지금까지의 실험 흐름

| 계열·코드 | 검증 목적 | 실행 내용과 확인 사항 | 상태 |
| --- | --- | --- | --- |
| **P0/P1** | 환경·공동 추론·좌표계 검증 | 공식 모델 접근과 호스트 추론, 카메라 규약·depth 역투영·관측 출처 확인 | 완료 |
| **P2/P2a~c** | 렌더링·미분 검증 | PyTorch3D 비교, 검은 테두리·색 합성·가림·gradient 진단 | 완료, 제한 기록 |
| **E0/E0a/E1** | 보정 전 원본과 층 분리 진단 | raw 관측 보존, 프레임별 빨강/초록/파랑 PLY 및 카메라별 투영 | 완료 |
| **E2** | 보수적인 공유점 융합 | 589,824 → 510,427점, 가시성과 내부 기하 비교 | 완료, 기하 개선 미확인 |
| **E0b/E0c** | 순차 깊이 평균·색 조건 융합 | 각각 341,325점 / 419,864점. E0c는 원본 RGB 채널 범위 ≤30 적용 | 완료 |
| **E3/E3b/E3c** | 카메라 고정·RGB 손실로 정점 이동 | 원본/융합 초기값에서 owner ray 방향 이동. E3c는 실제 이동과 RGB 감소 확인 | 실행 완료, 지표 상충 |
| **E3d/E0d/E3e** | ADOP에서 착안한 최소 보정과 드론 전이 | 실내 및 두 드론 장면 검증, selected/last 결과 보존 | 해당 방법 종료 |
| **C0~C3/C2a/C3a** | 원본 depth·pose 고정 FoV 보정 | 역투영·solver 검증. 실내 정식 군은 지원 부족, 보조 군은 실제 제안값 산출 | 완료, 저지원 탐색 |
| **C4/C4a** | 드론 FoV 보정 | 일부 고정 보류 대응의 3D 잔차 감소, 깊이축 목표 기준 미충족 | 완료 |
| **C5/C5b 및 보조 검증** | FoV 전후 색+깊이 조건 융합 | 대표점 수 감소와 provenance 보존, 이전 카메라의 coverage 손실 확인 | 완료, 압축 기준 미달 |
| **V0** | 일반 VGGT와 육안 비교 | 동일 실내 3장으로 depth 기반·point-head 기반 PLY를 각각 생성 | 완료 |
| **G0~G6/G0a/G0b/G5a** | C3a에 점·선·깊이 제약 추가 | 18개 주 비교군, 20개 초기값·가중치 비교, 실제 MoGe-2 prior 포함 | 완료, 탐색적 결과 |
| **PlanarGS 조사** | 영상 분할·평면 보정 요소의 재사용 검토 | 공식 코드 commit·함수·임계값 의미와 이식 조건 조사 | 정적 조사 완료 |
| **H0~H6 및 보조 검증** | C3a에 분할·공유 평면 재투영 | GroundingDINO+SAM ViT-H, 독립/공유 평면, hard/soft, 실제 PLY·보존 검증 | **완료, 지표 상충·탐색적 결과** |
| **I0~I9** | 화면 전체 자동 평면 정렬·기록 | SAM 전체 영상 tag → FoV → 후보 분리·전역 연결·관계 추론·공동 최적화 → 재투영·plane registry | **계획 작성, 미실행** |

실행별 상세 근거와 실패 이력은 다음 문서를 따른다.

- [P/E 계열 전체 현황](docs/experiments/pointmap_refinement/index.md)
- [C 계열 전체 현황](docs/experiments/camera_fov_alignment/index.md) · [종합 결과](docs/experiments/camera_fov_alignment/summary.md)
- [V0 일반 VGGT 비교](docs/experiments/vggt_baseline/index.md)
- [G 계열 전체 현황](docs/experiments/point_line_depth_refinement/index.md) · [종합 결과](docs/experiments/point_line_depth_refinement/summary.md)
- [H 계열 계획·상태](docs/experiments/c3a_plane_refinement/index.md)
- [I 계열 전체 화면 자동 평면 계획·상태](docs/experiments/global_planar_pointmap/index.md)

## 3. 주요 관찰과 해석

### 원본부터 존재한 벽 층과 RGB 최적화의 한계

원본 E0 PLY에서도 프레임별 벽이 분리된 것이 관찰됐다. E0a는 출처별 색과 타 프레임 투영으로 이를 확인하기 위한 실험이다. 여러 이미지가 공동 입력이었다는 사실만으로 각 관측점이 정확히 같은 표면에 놓이거나 중복점이 융합되는 것은 아니다.

E0b는 새 카메라 픽셀에 겹친 이전 점의 깊이를 평균·치환했고, E0c는 여기에 색 유사도를 추가했다. **E0c에는 명시적인 깊이 차이 gate가 없었다.** 이후 C5에서 전체 그룹의 깊이 범위 조건을 별도로 추가했다.

RGB 기반 이동에서 E3c 처치군은 RGB 손실이 약 2.33% 감소했지만 고정 공통 영역의 GT 깊이 오차가 늘었다. 이는 RGB 손실 감소가 깊이 정확도 개선을 보장하지 않는 사례다. 반대로 해당 지표만으로 PLY 전체 표면의 육안 품질이 악화됐다고 단정하지 않는다. 이 방법은 실내·드론의 최소 후속 검증 뒤 종료했다.

### C3a: 현재 후속 실험의 기준선

C3a는 카메라 중심·회전·원본 Z-depth·RGB·주점을 고정하고, **카메라별 fx/fy에 대응하는 역초점거리 배율 β 6개**를 보정했다. 매 후보에서 depth를 다시 역투영했으며 점 융합이나 자유 정점 이동은 하지 않았다.

사용자는 **실제 제안 점군의 표면 정합이 특히 좋다**고 관찰했다. 이 점군은 다음 경로다.

```text
results/camera_fov_alignment/tum-freiburg1_desk-C3a-20261112-001/
  stages/C3a/artifacts/fit/proposed_not_selected/
```

`proposed_not_selected`는 단순 실패 파일이 아니다. 실제 solver는 수렴했지만 원래 coverage 기준 때문에 자동 선택되지 않은 후보다. **기존 selected는 β=1이므로, 이번 후속 기준선과 다르다.** 대응 지원 부족·GT 미평가라는 한계와 육안 관찰을 함께 보존한다. [C3a 보고서](docs/experiments/camera_fov_alignment/C3a/tum-freiburg1_desk-C3a-20261112-001/report.md)

드론에서는 C4a의 보류 대응 3D median이 HKairport01 약 10.42%, AMtown01 약 23.16% 감소했지만, 깊이축 개선의 사전 기준에는 미달했다. C5/C5b는 점 수를 줄였으나 이전 시점의 픽셀 coverage 손실로 압축 기준을 통과하지 못했다.

### 일반 VGGT와 VGGT-Ω 비교

V0는 동일 실내 원본 3장을 일반 VGGT에 함께 입력해 보정·융합 없는 PLY를 생성했다. 사용자는 일반 VGGT의 벽 깊이와 프레임 간 겹침이 더 좋다고 관찰했다. 이는 이 샘플의 육안 관찰이며, 모델 전체의 우열이나 점군 융합 기능의 유무를 증명하는 결과는 아니다.

### G: 전체 지표와 국소 벽 개선이 다르게 나타남

G는 C3a proposed를 기준으로 점(P), 선(L), 교차 시점 깊이(Z), 제한된 프레임별 깊이 배율, 외부 MoGe-2 prior(E)를 비교했다. 아래는 모두 **제안 결과**의 탐색적 수치다.

| 비교 | 관찰된 변화 | 함께 볼 한계 |
| --- | --- | --- |
| 기존 실내 G2 F-PZ | C3a 대비 보류 대응 3D median 약 2.28% 감소 | 사전 5% 개선 기준 미달 |
| 기존 실내 G3 D-P | 고정 벽 ROI 층 간격 약 27.80% 감소 | 전체 보류 대응 3D 오차 약 10.13% 증가 |
| 기존 실내 G4 D-P+E | 같은 벽 ROI 층 간격 약 29.47% 감소 | 전체 보류 대응 3D 오차 약 11.95% 증가 |
| 추가 실내 G5a D-PL | 해당 구간 기준선 대비 3D median 약 8.85% 감소 | Z 오차 약 27.97% 증가, 선 구조 지원 부족 |

고정 벽 ROI는 프레임 0/1만 지지하며 프레임 2의 지지점은 없다. 사용자는 G 일부 PLY에서도 더 정확한 벽 겹침을 확인했다. **일관된 전체 개선이 미확인이라는 판정과 국소·육안 개선은 양립한다.** 전체 품질을 단일 잔차나 coverage로 단정하지 않는다.

## 4. H 완료: C3a → 영상 분할 → 공유 평면 재투영

[H0~H6 실험 계획](docs/c3a_planargs_plane_refinement_experiment_plan.md)은 C3a의 실제 FoV 제안값만을 초기값으로 고정한다. G 결과를 초기값으로 혼용하지 않는다.

1. **H0:** C3a 재현과 평면·광선 교차 수식 검증.
2. **H1~H2:** 영상의 벽 후보 분할, 법선·거리·연결 성분 정제, 평가 영역 동결.
3. **H3:** 프레임별 독립 평면 재투영.
4. **H4:** 같은 벽의 관측을 연결한 공유 평면 재투영.
5. **H5:** 동일 공유 평면에서 원래 깊이를 보존하는 soft 보정.
6. **H6:** PLY·벽 단면·투영·정합성·보존 조건 종합 비교.

원본 픽셀색·관측점 ID·카메라와 **589,824점**을 유지하고, 수용된 관측의 자기 광선 Z-depth만 최대 2% 이동했다. 전체 24개 제안군의 NPZ·두 색상 PLY를 다시 읽어 좌표·RGB·출처와 거절점 bitwise 보존을 검증했다.

H0의 합성 제어 오류는 H0a로 보완했다. H2/H2b의 타일 분리에서 알려진 track 10개가 양쪽 split에 걸린 것을 발견해, **c=track 전체 holdout을 적용한 기본 최종 군, d=같은 분리와 중복 마스크 NMS를 적용한 보조 최종 군**으로 재실행했다. 보완 전 결과도 보존한다. H6a는 E0 참고 수치·고정 축 확대 단면·공유 평면색을 추가했다.

| 최종 비교 | 실제 변경 | C3a 대비 고정 벽 ROI 관찰 |
| --- | --- | --- |
| H4c 기본 공유 평면 | 유효 공유 평면 0, A0 유지 | 중복 마스크를 모호 영역으로 제외해 벽 지지 부족 |
| H4d A3 원시 마스크 공유 hard | 공유 벽 1개, 50,934점 이동 | 두께 약 18.51% 감소, source median 층 간격 약 5.17% 증가 |
| H4d A4 법선 정제 공유 hard | 같은 카메라 0/1의 공유 벽 1개, 31,352점 이동 | 두께 약 20.88% 감소, 층 간격 약 41.22% 증가 |
| H5d A5 공유 soft | A4와 같은 평면·관측·gate, 31,352점 이동 | 두께 약 18.18% 감소, 층 간격 약 29.11% 증가 |
| H4d A6 기하 전용 | 유효 공유 평면 0, A0 유지 | 큰 연결 후보의 robust 지지 부족 |

위 벽 ROI는 camera0/1만 포함한다. 서로 다른 표면 패치의 signed median과 두께를 함께 보며, 보류 matching 지표가 거의 그대로인 것을 벽 정확도 검증으로 해석하지 않는다. 확대 단면에서는 H4d A3의 수용된 두 출처가 얇은 띠로 모이는 모습과 마스크 밖·거절점의 잔여 굴곡을 함께 볼 수 있다. A4는 법선 분리로 보정 범위가 줄어든다. 이 지표만으로 전체 PLY 육안 품질을 단정하지 않는다. [H 종합 결과](docs/experiments/c3a_plane_refinement/summary.md) · [벽 확대 단면](docs/experiments/c3a_plane_refinement/H6a/tum-freiburg1_desk-H6a-20261113-001/report.md)

후속 **H4e**에서는 확정한 공유 평면을 기준으로 모든 프레임의 점을 다시 소속시키고, 법선 15/25/35°와 이동 2/5/10%를 12군으로 비교했다. 기존 소속에서 이동 제한만 풀면 31,352→31,367점으로 변화가 작았지만, 재소속·35°·5%에서는 **56,160점(프레임 0/1/2: 32,262/18,643/5,255)**으로 늘었다. 같은 설정에서 10%는 추가 수용이 없었다. 12군 모두 기술·가시성 보존 조건을 통과했다. [H4e 보고서](docs/experiments/c3a_plane_refinement/H4e/tum-freiburg1_desk-H4e-20261113-001/report.md)

**H4f**에서는 H1 SAM 벽 마스크를 직접 소속으로 사용하고 법선·신뢰도·경계·참조깊이·이동 상한을 제거했다. camera1의 NMS에서 빠진 넓은 마스크도 복원했다. 주 군 `SAM_SHARED_UNCAPPED`는 **80,770점(camera0/1/2: 40,065/32,089/8,616)**을 같은 평면으로 이동했다. 20% 초과 변화 6,767점·100% 초과 790점도 포함한다. 고정 벽 ROI 단면에서는 잔여 굴곡이 제거됐지만 전체 정확도를 입증한 것은 아니다. [H4f 상세 결과](docs/experiments/c3a_plane_refinement/H4f/tum-freiburg1_desk-H4f-20261113-001/report.md)

**H4g**는 사용자 확인으로 드러난 H4f의 소속 오류를 수정했다. camera1 큰 마스크의 왼쪽 **8,290점**은 별도 벽이므로 오른쪽 plane에 보내지 않고 수직인 L plane에 배치한다. camera0/1의 기존 오른쪽 보정값은 bitwise 유지하고 모호한 231점은 C3a로 복원했다. 자유 적합(73.13°)과 사용자 수직 prior(90°)를 함께 보존했다. 주 군은 같은 왼쪽 plane을 camera2의 808점에도 적용한다. 수직은 부과한 제약이며 실제 위치/각도의 GT 검증은 아니다. [H4g 결과](docs/experiments/c3a_plane_refinement/H4g/tum-freiburg1_desk-H4g-20261113-001/report.md)

## 5. PLY와 결과 찾기

대형 PLY/NPZ·checkpoint·입력 데이터는 로컬에 보관하며 `.gitignore` 대상이다. GitHub에는 코드·설정·보고서·그림·수치·파일 해시를 저장한다. 따라서 저장소를 clone하는 것만으로 모든 PLY가 내려오지는 않는다.

| 경로·목록 | 내용 |
| --- | --- |
| `results/c3a_plane_refinement/ply_review/` | H 기준선·모든 군의 RGB/프레임색 빠른 경로. 최종 기본=c, 중복 정리 보조=d |
| [H PLY inventory](docs/experiments/c3a_plane_refinement/H6/tum-freiburg1_desk-H6-20261113-001/evaluation/ply_inventory.json) | 146개 상태·색상별 항목, 실제 경로·해시. initial/retained는 동일 파일을 가리킬 수 있음 |
| `results/point_line_depth_refinement/ply_review/` | C3a와 G 주 비교군의 원본 픽셀색·프레임색 PLY에 대한 빠른 symlink 경로 |
| [G 전체 PLY 목록](docs/experiments/point_line_depth_refinement/G0b/tum-freiburg1_desk-G0b-20261113-001/evaluation/ply_files.json) | G0/G2/G3/G4/G5a의 상태·색상별 154개 PLY 경로·크기·해시. 동일 후보의 중복 상태 포함 |
| [기존 PLY inventory](docs/ply_inventory/files.csv) | 앞선 E/C/V 및 표시용 PLY 목록. G/H를 포함한 최신 전체 목록은 아니므로 범위를 확인 |
| `results/vggt_baseline/tum-freiburg1_desk-V0-20261113-002/stages/V0/artifacts/maps/` | 일반 VGGT의 `vggt_depth_rgb.ply`, `vggt_depth_frames.ply` 및 point-head 결과 |
| `results/ply_visualization/E3b_pixel_rgb-001/` | E3b geometry에 원본 관측 픽셀색을 표시한 버전 |
| `results/ply_visualization/E3c_pixel_rgb-001/` | E3c의 control_E0b / treatment_E0c 원본 관측 픽셀색 버전 |

`initial`, `proposed` 또는 `proposed_not_selected`, `selected`, `last`는 서로 다를 수 있다. 자동 selected가 초기값이면 실제 이동 결과는 proposed/last에서 확인해야 한다. RGB 색과 프레임 팔레트도 구분한다. 표시용 픽셀색 재출력은 geometry나 과거 최적화를 다시 실행한 것이 아니다.

## 6. 문서와 저장 규칙

| 문서 | 범위 |
| --- | --- |
| [초기 Pointmap Refinement 계획](docs/vggt_omega_pointmap_refinement_experiment_plan.md) | P/E 계열 설계와 종료 이력 |
| [FoV 정렬·융합 계획](docs/vggt_omega_fov_pointmap_alignment_experiment_plan.md) | C 계열 설계·실행 결과 연결 |
| [점·선·깊이 제약 계획](docs/vggt_omega_point_line_depth_refinement_experiment_plan.md) | G 계열 사전 설계·구현 변경·결과 연결 |
| [PlanarGS 재사용 조사](docs/research/planargs_reuse_review.md) | 공식 소스·분할 정제·평면 깊이 계산과 적용 조건 |
| [PlanarGS 조사 소스 manifest](docs/research/planargs_source_manifest.json) | 확인한 commit·파일 해시·immutable URL |
| [C3a 기준 공유 평면 보정 계획](docs/c3a_planargs_plane_refinement_experiment_plan.md) | H 계열의 사전 범위·비교군·판정 기준과 실행 보완 기록 |
| [화면 전체 자동 평면 Pointmap 계획](docs/vggt_omega_global_planar_pointmap_experiment_plan.md) | I0~I9 자동화·무제한 재투영·평면/경계/관계 보존 설계 |
| [I0~I9 실행 결과](docs/experiments/global_planar_pointmap/index.md) | 주/추가 실내·A0~A6 실행 완료. 기술 검증 통과, A4 가시성 실패로 retained=initial, GT 미평가 |
| [I10 named OR 평면 테스트](docs/experiments/global_planar_pointmap/I10/index.md) | wall/table/screen만 투영, 대응 영역 named OR. 주 구간 가시성 통과·추가 실내 initial 유지 |
| [I11 현재 I10의 TUM GT 평가](docs/experiments/global_planar_pointmap/I11/index.md) | 두 구간의 전체 깊이 MAE·RMSE 악화. 주 구간 wall 개선, table·screen 악화. 공통 baseline FIT 정렬·validation 평가 |
| [평면 거리·법선 RGB 최적화 계획](docs/vggt_omega_plane_photometric_experiment_plan.md) | I12 RGB 최적화와 I13 별도 GT 평가의 비교군·미분·지원·손실·성공 기준 |
| [I12~I13 평면 RGB 최적화 결과](docs/experiments/global_planar_pointmap/I13/index.md) | 거리만/거리·법선 모두 전체 GT 정확도 악화. 주 처치군 보류 RGB도 악화, 기존 retained 유지 |
| [ETH3D 실내 레이저 GT 계획](docs/vggt_omega_eth3d_laser_experiment_plan.md) | 데이터 조사·새 장면 선택·왜곡/픽셀 좌표·동결 설정·독립 GT 평가 규약 |
| [ETH3D office/pipes 레이저 GT 결과](docs/experiments/global_planar_pointmap/I20/index.md) | pipes 고정 평면 소폭 개선, RGB 거리·법선 재정렬은 두 장면 모두 전체 개선 실패 |
| [I21 무보정 Omega raw 포함 비교](docs/experiments/global_planar_pointmap/I21/index.md) | raw/FoV/평면/거리/거리·법선/retained를 4구간에서 비교. 고정 depth mask·공통 정렬, 3D 정렬 민감도 분리 |

실험은 `experiments/<계열>/<코드>/`, 결과는 `results/<계열>/<run_id>/stages/<코드>/`, 보고서는 `docs/experiments/<계열>/<코드>/<run_id>/`로 구분한다. 보조 검증은 a/b/c 접미사를 붙이고 실패·중간 결과를 덮어쓰지 않는다. 실제 실행 명령은 각 계열의 코드·실행 보고서를 따른다.

GPU 작업은 호스트에서 실행하며 실행 환경·입력·코드·모델의 출처와 해시를 기록한다. 실험 완료 후 코드·경량 결과·보고서를 커밋·푸시하고 원격 반영을 확인한다. 단일 샘플의 내부 정합성·육안 개선을 GT 기반 전체 정확도나 연속 SLAM 성능으로 확대 해석하지 않는다.
