# PlanarGS 조사: C3a/G 점군에 사용할 수 있는 요소

> 작성일: 2026-11-13<br>
> 상태: **논문·공식 코드 정적 조사 완료. 설치·모델 추론·PLY 보정 실험은 미실행**<br>
> 대상: 기존 실내 RGB 3장과 C3a/G 미융합 pointmap<br>
> 결론: **LP3의 분할 정제와 평면 깊이 계산을 가져올 가치가 크다. 여러 프레임을 하나의 공유 평면에 묶는 단계와 안전한 점 이동 규칙은 별도로 구현해야 한다.**

## 1. 이번 조사에서 구분한 것

사용자는 G 실험의 일부 PLY에서 벽의 겹침이 개선된 것을 관찰했다. 이 관찰을 유지한다. [G 계열 종합 보고서](../experiments/point_line_depth_refinement/summary.md)의 전체 대응점 잔차·고정 벽 ROI와 육안 관찰을 함께 보며, G가 효과 없었다고 단정하지 않는다.

이번 목적은 기존 정렬 결과를 초기값으로 사용해 영상에서 평면 후보를 찾고, 구불구불한 깊이와 남아 있는 층을 공유 평면으로 정리할 수 있는지 조사하는 것이다. 기존 결과를 덮어쓰거나 종료한 C/G 실험을 자동 재개하지 않는다.

자료는 세 종류로 구분한다.

- **논문 설명:** 저자가 제안·보고한 내용.
- **코드 확인:** 아래 commit에서 실제 읽은 구현과 기본값. 실행 검증을 의미하지 않는다.
- **우리 적용안:** 원본 픽셀색·관측 ID를 보존하는 PLY 보정을 위한 제안. PlanarGS 공식 기능이라고 표시하지 않는다.

## 2. 논문과 소스 식별

- 논문: *PlanarGS: High-Fidelity Indoor 3D Gaussian Splatting Guided by Vision-Language Planar Priors*, NeurIPS 2025.
- [저자 프로젝트](https://planargs.github.io/) · [논문 v1](https://arxiv.org/html/2510.23930v1) · [공식 저장소](https://github.com/SJTU-ViSYS-team/PlanarGS).
- 확인한 코드 commit: `a68f22043e95146c4f1c52cc0e471a6a90e86f73`.
- 조회일·파일 SHA-256·immutable URL은 [조사 소스 manifest](planargs_source_manifest.json)에 기록한다.
- 소스 검토 캐시: `.cache/planargs_review/`. 저장소의 `.gitignore` 대상이며 모델·전체 submodule은 받지 않았다.

**논문 개요:** PlanarGS는 GroundedSAM 기반 LP3로 평면 후보를 생성하고 다른 시점의 정보와 기하 prior로 정제한다. Gaussian 표현에는 공면성·깊이·법선 제약을 추가한다. 기본 다중 시점 prior는 DUSt3R이며 VGGT 대체 ablation도 있다. 이는 동일 VGGT-Ω 3장/C3a 조건의 검증이 아니다. [논문 §3, Table 4](https://arxiv.org/html/2510.23930v1#S3)

이하 세부 구현 분석은 논문 요약과 구분하고, 함수별 공식 코드 링크를 근거로 한다.

## 3. 전체 실행과 부분 도입의 차이

| 항목 | PlanarGS 공식 실행 경로 | 우리 점군 보정에 필요한 처리 |
| --- | --- | --- |
| 입력 | COLMAP 형식 영상·카메라·희소 점군과 사전정보 | 기존 RGB, K/pose, Z-depth, `frame_id/pixel_uv` 연결 |
| 공간 표현 | 위치·회전·크기·불투명도·외관을 가진 Gaussians | 원래 관측점 ID와 픽셀 RGB를 가진 점군 |
| 분할 | GroundingDINO + 원래 SAM ViT-H | 먼저 SAM의 점/박스 지정 방식만으로도 후보 검증 가능 |
| 기하 prior | DUSt3R 및 희소 기하에 대한 정렬 | 기존 공동 추론 depth/K/pose를 adapter로 제공 |
| 주 최적화 | 미분 렌더링과 Gaussian 파라미터 학습 | 공유 평면 적합·광선 방향 깊이 보정부터 분리 |
| 출력 | Gaussian 속성 PLY와 별도 TSDF mesh | 일반 XYZ+원본 픽셀색 PLY, 보정 전후 ID 유지 |

`scene/gaussian_model.py::training_setup`은 xyz뿐 아니라 SH 외관, opacity, scaling, rotation도 optimizer에 넣는다. 따라서 전체 실행 결과는 원본 색을 고정한 정점 위치 보정과 동일하지 않다. [optimizer 구성](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/scene/gaussian_model.py#L188)

## 4. 요소별 재사용 판단

### 4.1 영상으로 평면 후보를 제한: 우선 도입 가치 높음

`lp3/run_groundedsam.py`는 GroundingDINO로 텍스트에 맞는 박스를 얻고 SAM으로 마스크를 생성한다. 벽이라는 이름을 판단하는 부분과 마스크를 만드는 부분은 별도다. 코드가 사용하는 것은 `sam_vit_h`이며 SAM 2/3가 아니다.

검출 score 기본값은 box 0.25, text 0.2다. 이 값은 평면성 신뢰도나 3D 거리 허용 오차가 아니다. 마스크 예측은 box prompt와 `multimask_output=False`로 호출한다. [검출·분할 wrapper](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/lp3/run_groundedsam.py)

**우리 적용안:** 첫 검증에서는 각 영상의 벽에 점/박스를 지정해 마스크를 저장한다. 자동 텍스트 검출은 다음 비교군으로 분리하면 탐지 실패와 평면 보정 실패를 구분할 수 있다. 마스크는 한 번 동결해 C3a와 각 G 결과에서 같은 영상 후보를 사용한다. 'wall' 전체를 평면 하나로 간주하지 않는다.

### 4.2 다른 시점의 후보 전달: 유용하지만 공유 평면 융합은 아님

`lp3/box_migrate.py`는 이전 시점의 마스크 픽셀을 depth로 역투영하고 현재 카메라에 투영해 보충 박스를 만든다. 전달 대상은 기본적으로 면적이 큰 마스크 3개다. `run_lp3.py`는 순서대로 처리한 직전 카메라의 결과를 보관한다.

이 구현은 **검출 후보 보완**이다. frame별로 저장하는 mask 번호는 다시 1부터 부여되며, 이것만으로 영구적인 3D 벽 ID가 생기지 않는다. 또한 mask projection 경로는 투영 위치를 표시하는 방식으로, 엄격한 target depth 가림 검증이나 같은 물리적 표면임을 보장하는 최종 association 단계로 해석하면 안 된다. [후보 전달 코드](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/lp3/box_migrate.py) · [처리 루프](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/run_lp3.py)

**우리 적용안:** 3장 사이의 양방향 투영 overlap, 양의 Z, 가림·깊이 차이, 법선과 평면 offset을 확인한 뒤 별도의 `shared_plane_id`를 만든다. 전역 plane ID와 `(frame_id, local_mask_id)` 연결을 저장한다. 이 추가 association은 자체 설계다.

### 4.3 법선과 거리 정보로 마스크를 정제: 핵심 도입 후보

공식 코드에서는 다음 동작이 확인된다.

| 함수·위치 | 확인한 동작 | 복사 전에 확인할 점 |
| --- | --- | --- |
| `NormalSplit`, `SplitPic` | 정규화한 법선을 RGB 범위로 바꿔 K-means, 기본 5개 cluster | 5는 각도 허용값이나 장면의 평면 수가 아님 |
| `merge_similar` | 위 법선 표현의 평균 차이를 비교, 기본 threshold 50 | 이 호출 경로의 'color'는 사진의 실제 RGB가 아님 |
| `NormalSplit` | 마스크와 overlap이 큰 법선 cluster를 최대 두 개 선택 | 복잡한 마스크의 모든 평면을 완전 분리한다고 볼 수 없음 |
| `adjust_masks`, `MaxConnect` | 중복·겹침을 정리하고 연결 성분·면적 조건 적용 | 2,000/700 pixel 등은 해상도에 의존 |
| `MaskDistance` | `abs(n·X)`를 영상 전체 min/max로 정규화한 값에 threshold 적용 | RANSAC inlier 거리나 5cm·깊이 5%가 아님 |

[법선 cluster·거리 마스크](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/lp3/color_cluster.py) · [마스크 정제](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/lp3/mask_refine.py)

특히 `MaskDistance`의 `dis_thresh=0.05`는 평면 적합 잔차가 아니다. 확인한 식은 다음과 같다.

```text
s(u) = abs(n(u) dot X(u))
s_normalized = (s - min(s)) / (max(s) - min(s) + 1e-8)
mask = s_normalized > dis_thresh
```

그 뒤 반대 영역을 3×3 max-pooling으로 두껍게 해 제외한다. 이 경로에는 국소 plane-distance gradient를 직접 계산하는 연산은 보이지 않았다. '기하 경계 검출'이라는 개념과 이 commit의 실제 연산을 구분해야 한다. [거리·pooling 유틸리티](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/common_utils/graphics_utils.py#L212)

**우리 적용안:** segmentation을 구조 후보로 사용하되, 구불구불한 Omega depth의 인접 픽셀 법선을 절대 기준으로 삼지 않는다. 여러 크기의 이웃에서 법선·잔차를 측정하고, 영상 경계와 조합해 평면 조각을 만든다. 거리·각도·면적 기준은 원래 코드값과 자체 설정을 따로 기록한다. 특히 512×384 영상에 2,000 pixel 기준을 그대로 적용하면 작은 영역이 사라질 수 있으므로 고정 면적 비율과 실제 pixel 수를 병기한다.

### 4.4 평면 적합과 광선 교차 깊이: 가장 직접적으로 이식 가능

`planar/co_planar.py`는 현재 depth와 segmentation으로 카메라 좌표 점을 만들고, 마스크별로 다음 형태를 계산한다.

```text
Q: 한 마스크의 점 좌표를 행으로 둔 N×3 행렬
Q A ≈ 1
A = (QᵀQ + εI)⁻¹ Qᵀ1
D_plane(u) = 1 / (Aᵀ K⁻¹ [u,v,1]ᵀ)
```

코드는 `ε=0.01`을 사용한다. **이것은 1cm의 평면 허용 오차가 아니라 정칙화 계수**다. 이 함수 자체에는 RANSAC·robust loss·명시적인 점–평면 최대거리 gate가 없다. 하나의 label 안에 포함된 점으로 적합하므로 mask에 다른 표면이 섞이면 결과도 영향을 받는다.

`co_planar`는 입력 label 배열의 **영상 바깥 테두리 8 pixel**을 0으로 수정한다. 각 물체 마스크의 경계를 8 pixel 침식하는 동작과는 다르다. `.cuda()`·명시적 역행렬에 의존하는 구현이므로 독립 CPU/float64 유틸리티로 쓰려면 변경이 필요하다. [공면 깊이 함수](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/planar/co_planar.py)

**우리 적용안:** frame별 독립 적합만 하면 평평한 벽이 여러 겹 남을 수 있다. 먼저 같은 벽의 관측을 묶고 **월드 좌표의 공유 평면**을 적합한다. 원본 광선은 `r=K_i⁻¹[u,v,1]ᵀ`로 두면 다음과 같이 깊이를 구할 수 있다.

```text
X_world = C_i + D * R_i⁻¹ r
공유 평면: nᵀ X_world + d = 0
D_plane = -(nᵀ C_i + d) / (nᵀ R_i⁻¹ r)
```

이는 위 원리를 월드 좌표 공유 평면에 적용한 자체 유도식이다. 관측별 픽셀과 원본 RGB를 유지할 수 있다. 분모가 작거나 깊이가 비양수인 점, 큰 상대 깊이 이동이 필요한 점은 그대로 유지하고 별도 마스크로 기록한다. 적용 강도는 `D_new=(1-α)D_old+αD_plane`처럼 분리할 수 있지만 α는 새 실험에서 사전 확정해야 한다.

실제 구현에서는 QR/SVD 기반 적합과 robust 재가중, 고정 지지점/잔차 한계, 원본으로의 복귀 경로를 마련한다. 이는 공식 코드의 직접 실행이 아니라 수치 안정성과 provenance를 위한 변경이다. 원점 근처 평면에 민감할 수 있는 `AᵀX=1`보다 일반형 `nᵀX+d=0`도 비교할 가치가 있다.

### 4.5 공면 손실과 depth/normal prior: 후속 최적화에 참고

`train.py`는 렌더링된 depth로 `co_planar`를 호출하고, 그 결과와 현재 렌더 depth 사이의 L1 손실을 더한다. **원본 PLY를 한 번 읽어 바로 평면으로 치환하는 실행 경로가 아니다.**

코드 기본값은 depth prior/normal-consistency를 약 7,000 iteration, planar loss를 14,000, prior normal을 20,000부터 사용한다. 총 iteration은 30,000이며 관련 계수는 `lambda_dnloss=0.05`, `lambda_planar=0.5`, `lambda_priordepth=0.05`, `lambda_priornormal=0.2`다. 이 스케줄·계수는 Gaussian 학습용이므로 G의 β·깊이 배율 solver에 그대로 더하지 않는다. [학습 손실 경로](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/train.py#L130) · [기본 설정](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/arguments/__init__.py)

**우리 적용안:** 먼저 분할·공유 평면·일회 재배치만 평가한다. 그 효과를 확인한 다음, 점 대응과 평면 거리 및 원래 깊이 보존 항을 함께 쓰는 보정으로 확장한다. RGB 렌더러와 색 학습을 바로 재도입하지 않는다.

### 4.6 prior의 scale/shift 정렬: 개념은 유용, 기준 데이터는 필요

`geomprior/align_opt.py::OptimizeGroupDepth`는 그룹 내 depth에 공유 scale·shift를 적용해 target sparse depth와 맞춘다. 읽은 구현은 weighted L2와 Adam을 사용하며 양수가 아닌 깊이에 penalty를 준다. 논문의 정렬 식이 L1인 것과 구분한다. [그룹 정렬 코드](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/geomprior/align_opt.py)

**우리 적용안:** 동일 Omega 결과에 다시 맞춘 값을 독립적인 정확도 증거로 쓰지 않는다. 새 외부 prior를 넣을 경우 fit 영역으로만 보정값을 정하고 고정해야 한다. scale/shift를 바꾸는 처리는 FoV 보정과도 별도 변수다. 현재 목적의 첫 단계에는 추가 depth 모델이 필수는 아니다.

### 4.7 초기 점 보충·Gaussian flattening·TSDF: 이번 단순 이식에서는 보류

`planar/densify_points.py`는 마스크를 Gaussian 점에 연결하고 부족한 영역의 점을 보충하는 유틸리티를 포함한다. 일부 최근접 검색은 M×N broadcast 텐서를 만들어 큰 입력에서 메모리 비용이 커질 수 있다. [초기 점 보충](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/planar/densify_points.py)

우리는 기존 관측점이 이미 조밀하다. 우선 점 추가·삭제 없이 보정해 평면 효과를 분리한다. Gaussian flattening은 Gaussian 축 크기에 대한 항이며, 일반 PLY에는 대응 변수가 없다. TSDF mesh 생성은 표면 표현·융합의 추가 단계로 별도 평가한다. LP3의 'cross-view fusion'을 기존 색·깊이 gate 점군 융합과 동일하다고 부르지 않는다.

## 5. 좌표계·해상도·공유 ID adapter

독립적으로 가져올 요소라도 다음 계약을 먼저 검증해야 한다.

1. 기존 NPZ의 `x_c=R_i X_w+t_i`, 카메라 Z-depth, `C_i=-R_i⁻¹t_i` 규약을 유지한다. COLMAP reader의 R 저장 관례를 그대로 복사하지 않는다.
2. segmentation 영상과 pointmap 격자의 resize/crop 변환을 저장한다. label mask resize는 nearest-neighbor로 하고 경계 확인을 별도 수행한다.
3. 픽셀 좌표와 주점은 기존 규약을 유지한다. 공식 `Depth2Pointscam`도 정수 u/v를 사용하지만 직접 재투영 검증 전 일치를 가정하지 않는다.
4. normal은 카메라/월드 좌표를 명시하고 방향 부호를 일관되게 처리한다.
5. label은 frame별 local ID와 cross-frame shared ID를 분리한다. label 숫자가 같거나 'wall' 이름이 같다는 이유로 묶지 않는다.
6. 어떤 보정값의 depth/normal/K를 마스크 정제와 association에 사용했는지 기록한다. 후보 결과마다 마스크를 바꿔 평가 대상을 바꾸지 않는다.

기존 RGB/K/pose/depth와 원본 관측 ID를 함께 읽는 adapter는 새로 필요하다. LP3 전체는 `sparse/` COLMAP 입력을 요구하므로 원본 PLY 파일만 전달해 즉시 실행할 수 없다. [공식 전처리 루프](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/run_lp3.py#L58)

## 6. 적용 우선순위와 비용

아래 비용은 **정적 코드 조사에 따른 상대적인 구현 판단**이며 이 호스트에서 측정한 시간·VRAM이 아니다.

| 우선순위 | 도입 요소 | 계산/구현 부담 | 준비 조건 |
| --- | --- | --- | --- |
| 1 | 3장에 벽 마스크 생성·캐시 | 분할 모델 초기 준비, 이후 반복 사용 가능 | 마스크 육안 검증, 이미지 격자 연결 |
| 1 | 공유 평면 적합·광선 교차 | 점 순회와 작은 선형계가 중심 | 같은 벽의 관측 association, robust 적합 |
| 2 | LP3 법선·거리 정제 | 분할 추가 학습 없이 가능, 기존 depth 품질 영향 큼 | 다중 크기 법선·연결 성분 검사 |
| 2 | 시점 간 후보 전달 | 투영 비용, 가림 처리 추가 필요 | 올바른 K/pose·고정 mask·전역 ID |
| 3 | 평면+점 대응+depth prior 공동 최적화 | 설계·퇴화 검증 필요 | 일회 재배치 결과와 명확한 변수 정의 |
| 별도 비교 | PlanarGS 전체 Gaussian 학습 | rasterizer·KNN·PyTorch3D 등 빌드와 학습 환경 필요 | COLMAP 포맷, prior 생성, 체크포인트 준비 |

공식 README는 장면당 약 1시간/RTX 3090을 보고하고, 모델·CUDA 확장 설치 및 custom data의 COLMAP 전처리를 요구한다. 이는 우리 3장 데이터의 실행 시간 추정치가 아니다. 기본 prior 경로도 그룹 입력을 사용하므로 극소 baseline의 3장만으로 같은 성능을 보장하지 않는다. VGGT 대체 실험이 있다는 사실과 이 commit에 바로 쓸 VGGT adapter가 제공됐다는 것은 별개이며, 검토한 `geomprior/` 경로는 DUSt3R용이었다. [공식 설치·입력·출력 안내](https://github.com/SJTU-ViSYS-team/PlanarGS/blob/a68f22043e95146c4f1c52cc0e471a6a90e86f73/README.md)

소스의 최상위 LICENSE는 MIT지만 `common_utils/graphics_utils.py` 등에는 기존 3DGS의 별도 copyright/license 표기가 남아 있다. 실제 코드를 가져올 때 원래 파일과 사용 submodule의 표기를 함께 보존·확인한다. 이번 조사에서는 실행 환경을 설치하거나 upstream 코드를 우리 실험 코드로 편입하지 않았다.

## 7. 가장 작은 후속 검증안 — 아직 미실행

새 실험을 요청받으면 별도 코드·run 폴더로 분리한다. G 계열 결과의 자동 selected 대신 사용자가 관찰한 **실제 proposed**를 기준 후보로 포함한다.

| 비교군 | 목적 |
| --- | --- |
| C3a proposed 그대로 | 기존 좋은 FoV 기준선 |
| C3a + 기하만 사용한 공유 평면 보정 | 영상 분할 없이 얻는 평면 보정 효과 |
| C3a + 영상 마스크 + 공유 평면 보정 | 분할을 추가했을 때의 차이 |
| 사전 지정한 G proposed 그대로 | 일부 벽 겹침이 개선된 G 결과의 보존 |
| 같은 G + 같은 영상 마스크 + 공유 평면 보정 | G의 정렬이 후속 평면 보정에 주는 효과 |

G 기준을 전체 validation 또는 최종 그림에서 사후 선택해 최고값만 보고하지 않는다. 예를 들어 기존 고정 ROI에서 개선된 D-P/D-P+E 등을 후보로 포함하되 선택 근거를 사전 기록한다. 공통 마스크에서 시작하고 geometry 정제·association의 기준 arm도 고정한다. 후보마다 가시성 차이로 유효점이 달라지면 수와 제외 이유를 공개한다.

점–평면 거리, 법선, 마스크 면적, 광선 교차의 분모 한계, 최대 상대 Z 이동은 서로 다른 파라미터로 둔다. 이전에 제안한 거리 0.25%/0.5%/1%는 우리 샘플의 탐색 후보이지 PlanarGS의 사전값이 아니다. 평면 소속 허용값을 그대로 최대 이동량으로 재사용하지 않는다.

결과물은 다음을 함께 보존한다.

- 원본 RGB 위 local mask/shared plane ID와 검출·분리·병합 근거.
- 평면 계수, 고정 지지점, inlier/거절점, source frame 분포, 잔차·법선·이동량 분포.
- 전후 XYZ와 불변 `frame_id/pixel_uv/rgb`, 원본 픽셀색·출처색 PLY.
- 같은 카메라/점 크기의 투영, 타 프레임만의 투영, 외부 시점, 고정 벽 단면.
- 전체 대응점과 국소 벽 ROI를 나눠 평가. 점을 평면에 옮겨 잔차가 줄어든 사실은 독립적인 정확도 증거가 아니므로 보류 관측·경계·coverage·필요 시 검증된 GT를 함께 사용.

## 8. 조사 결론

**우리 목적에는 PlanarGS 전체를 먼저 실행하는 것보다, LP3의 영상 후보 정제와 평면 깊이 계산을 분리해 C3a/G pointmap에 연결하는 접근이 직접적이다.** 다만 같은 벽의 cross-frame association과 공유 평면 적합은 별도 구현해야 한다. 공식 코드의 `co_planar`를 frame마다 호출하는 것만으로 층이 하나로 정렬된다고 기대하면 안 된다.

현재 완료한 것은 논문·코드 조사와 적용안 정리다. 설치 호환성, segmentation 품질, 실제 시간/VRAM, 보정 후 PLY 품질은 아직 검증하지 않았다.
