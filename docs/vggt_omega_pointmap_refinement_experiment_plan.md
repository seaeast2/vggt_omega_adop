# VGGT-Ω 기반 단일 공유 Point Cloud의 다중 시점 미분 가능 렌더링을 통한 기하 재정렬 실험 계획서

> 상태: 설계 초안 v1.1 · 작성일: 2026-11-12 · 갱신일: 2026-11-12<br>
> 연구 용도: 대학원 졸업논문 실험 — VGGT-Ω 초기 Point Cloud를 원본 RGB 영상으로 정렬·보정할 수 있는지 검증<br>
> 실행 환경: NVIDIA RTX 5060 8GB VRAM, 단일 GPU  
> 핵심 범위: RGB 영상 → VGGT-Ω 초기 기하 → **하나의 공유 3D Point Cloud** → 다중 카메라 미분 가능 렌더링 → **동일한 3D 점 좌표의 공동 최적화**  
> 제외 범위: 영상 생성, 새로운 장면의 생성·완성, 동적 장면 모델링, 별도의 렌더링 표현 학습  
> 문서 성격: 실험 전 설계 및 구현 명세. 결과 수치·성능 향상은 아직 검증하지 않음.

## 0. 핵심 결정 사항

1. 최초 검증은 **정적인 장면의 RGB 입력 3장**으로 한다. 여유가 확인되면 4장으로 확장한다. 이전 VGGT 환경에서 4장이 실측 상한이었던 사실을 우선 고려하며, VGGT-Ω에서의 실제 상한은 재측정한다.
2. VGGT-Ω는 **Camera Pose, Intrinsics, Depth, Depth Confidence**를 초기화용으로만 사용한다. Pointmap은 Depth를 월드 좌표계로 역투영하여 생성한다.
3. 여러 이미지에서 생성한 점을 단순히 이어 붙인 집합은 아직 **융합된 공유 표면**이 아니다. 중복 관측을 식별하고 하나의 대표 3D 점 또는 표면 요소로 결합하는 단계를 별도로 구현한다.
4. 모든 카메라가 **같은 공유 점 집합의 위치 변수**를 참조한다. 프레임마다 독립적인 최종 Pointmap을 학습하지 않는다.
5. 첫 실험에서는 Camera Pose, Intrinsics, 점의 RGB 색상과 크기를 **고정**하고, 3D 점의 위치만 갱신한다.
6. 최적화는 다중 카메라 RGB 손실로 시작하되, 단순 자기 시점 복원과 과적합을 피하기 위한 **다중 시점 관측·가시성 검사 및 기하 Prior**를 반드시 포함한다.
7. 최종 판단은 **미사용 카메라에서의 영상 재현**과 **Ground Truth 기반 3D 기하 정확도**를 별도로 측정한다. 학습 영상 PSNR의 상승만으로 성공이라고 주장하지 않는다.
8. ADOP의 접근은 참고하지만, 본 연구에서 **ADOP 전체 신경 렌더링 파이프라인을 재구현하지 않는다.** 최초 구현은 최소 기능의 미분 가능 Point Renderer를 사용한다.
9. **실험코드별로 실행 코드, 중간 결과, 최종 결과와 보고서를 구분한다.** E0~E9의 의미는 13절을 따르며, 실행 회차마다 고유 Run ID를 부여하고 기존 결과를 덮어쓰지 않는다. 폴더 구조와 보고 규칙은 11.1절 및 17절을 따른다.

---

## 1. 연구 배경 및 목표

### 1.1 문제 정의

VGGT-Ω에 동일 장면의 N개 RGB 이미지를 입력하면 각 시점의 카메라 파라미터와 깊이 영상이 나온다. 이 정보에서 월드 좌표계의 점들을 생성하면 하나의 3D 공간에 여러 관측이 모인다. 그러나 동일한 표면의 관측들이 서로 정확하게 일치한다고 보장할 수는 없다. 카메라 및 깊이 예측 오차는 벽·바닥·물체 표면의 중복 층, 두께 증가, 공간적 이탈로 나타날 수 있다.

본 실험의 목적은 **하나의 공유 Point Cloud를 여러 카메라에서 반복 투영하여 원본 RGB 영상과 비교하고, 그 오차를 3D 점의 위치로 역전파해 동일한 장면의 기하학적 정합성을 개선할 수 있는지** 검증하는 것이다.

본 프로젝트는 **대학원 졸업논문을 위한 실험 저장소**로 운영한다. 여기서 Point Cloud 정렬은 원본 RGB 관측을 이용한 공유점 위치의 보정을 뜻하며, GT 비교를 위한 좌표계 정렬과는 구분한다. 논문에 사용할 수 있도록 실험 조건, 중간 산출물, 실패 기록과 최종 판단의 근거를 실험코드와 실행 회차로 추적한다.

이 연구는 카메라별 Depth Map을 독립적으로 예쁘게 보정하는 것이 아니다. 하나의 공유 변수인 3D 점 X_k를 수정했을 때 **그 점을 보는 모든 카메라에 동시에 영향이 미치는** 구조를 목표로 한다.

### 1.2 연구 질문

- RQ1. VGGT-Ω에서 얻은 초기 점들을 융합한 공유 장면을 고정 카메라들에서 렌더링하고 RGB 손실을 최소화하면 실제 3D 기하 오차가 감소하는가?
- RQ2. XYZ 자유 이동, 생성 카메라의 Ray 방향 깊이 이동, 초기 표면의 법선 방향 이동 중 어느 매개변수가 안정적인가?
- RQ3. 관측 카메라 수, 실제 시차각, VGGT-Ω Depth Confidence는 수정 대상 점의 선택과 가중치 결정에 유용한가?
- RQ4. 공유점 융합, 자기 관측 편향 억제, 가시성 검사, 기하 Prior는 각각 얼마나 기여하는가?
- RQ5. RTX 5060 8GB에서 실험을 재현 가능한 메모리 사용량과 시간으로 수행할 수 있는가?

### 1.3 가설 및 반증 가능성

| ID | 가설 | 반증에 해당하는 관측 |
| --- | --- | --- |
| H1 | 다중 시점 RGB 최적화가 초기 공유점의 기하 정확도를 개선한다 | 학습 영상만 좋아지고 GT Depth/Chamfer가 유지 또는 악화 |
| H2 | 기하 Prior를 추가하면 XYZ 최적화의 과도한 변형이 감소한다 | Prior 적용 후에도 GT 기하 오차·이상점 지표가 악화 |
| H3 | 유효한 복수 관측과 충분한 시차각을 가진 점을 선택하면 개선이 더 안정적이다 | 선택 최적화가 무작위 선택 또는 전체 최적화보다 지속적으로 열세 |
| H4 | Ray-depth 최적화는 XYZ보다 작은 자유도로 초기에 더 안정적이다 | 깊이 수렴이 불안정하거나 기하 정합성 개선이 현저히 낮음 |
| H5 | 단계 분리·부분 점 샘플링으로 8GB 환경에서 최소 실험이 가능하다 | 3장/저해상도/소량 포인트 설정에서도 반복 OOM 또는 허용 불가 실행시간 |

이 가설들은 **미확인 가설**이다. 어떤 개선도 사전에 보장하지 않는다.

### 1.4 명시적 비목표

- VGGT-Ω 모델 자체의 재학습 또는 파인튜닝.
- 3D 공간에 존재하지 않았던 물체/표면의 추론적 생성.
- 카메라의 절대 위치가 정확하다는 보장.
- 모든 종류의 Bundle Adjustment 대체. 카메라를 고정하는 본 실험은 **고정 Pose의 공유 기하 최적화**이며 Pose Drift를 직접 해결하지 못한다.
- 원본 RGB 영상만으로 가려진 영역의 정확한 깊이 복원.

---

## 2. 관련 연구 및 구현 근거

### 2.1 VGGT-Ω

- 공식 코드: https://github.com/facebookresearch/vggt-omega
- 논문: https://arxiv.org/abs/2605.15195
- 공식 Quick Start는 모델 출력에서 <code>pose_enc</code>를 <code>encoding_to_camera</code>로 변환하여 **extrinsics, intrinsics**를 얻고, <code>depth</code> 및 <code>depth_conf</code>를 직접 사용한다.
- 공식 <code>demo_gradio.py</code>는 <code>unproject_depth_map_to_point_map</code>를 사용해 여러 프레임의 Depth를 공통 월드 좌표계 점으로 변환한다.
- 공식 데모가 GLB에 여러 점을 모으는 것은 **중복 표면의 관측 기반 데이터 연관과 공동 최적화가 구현되었다는 뜻이 아니다.**
- 모델 사용 전 체크포인트 접근 승인 및 라이선스 조건을 확인한다.

**중요한 카메라 규약:** 공식 <code>pose_enc.py</code>는 extrinsic을 **OpenCV 좌표계 world-to-camera**로 설명한다. world-to-camera가 R,t인 경우 세계점 P_w를 카메라 점으로 변환하는 식은 P_c=R P_w+t이며, 역변환은 P_w=Rᵀ(P_c−t)이다. 코드 내부의 순서 및 축 방향을 단위 테스트로 확인한다.

### 2.2 ADOP

- 논문: https://arxiv.org/abs/2110.06635
- 구현: https://github.com/darglein/ADOP
- 초기 Point Cloud를 미분 가능하게 렌더링하고 점 위치와 카메라 등 여러 파라미터를 개선한다.
- 이산적인 1-pixel Rasterization에서 공간 기울기를 근사하는 Ghost Geometry와 신경망 보정 및 카메라 Photometric Model도 포함한다.
- **본 실험은 이 논문의 핵심 아이디어인 point-position gradient만 참고**한다. 신경망 기반 구멍 메우기·색상 자유 학습 등은 최초 실험에서 제외한다.

### 2.3 PyTorch3D

- Point Renderer 문서: https://pytorch3d.readthedocs.io/en/latest/modules/renderer/points/renderer.html
- 점의 투영 위치와 픽셀 중심 사이 거리에 따른 Soft Alpha Weight를 사용해 위치 관련 기울기를 생성할 수 있다.
- 다만 **PyTorch3D를 선택했다는 이유만으로 깊이 방향 미분·가시성의 불연속·색상 보정 문제가 해결되는 것은 아니다.** 실제 Gradient를 유한차분과 비교하는 별도 검증이 필요하다.
- GPU 및 CUDA/PyTorch 버전의 호환성은 설치 시 확인한다. 빌드 실패 시 문서에 지정된 버전으로 고정하거나 독립된 Minimal Soft-Splat 구현으로 대체한다.

### 2.4 본 실험의 선행연구 대비 위치

본 실험은 '포인트를 렌더링하면서 위치를 최적화한다'는 개념 자체를 새로운 발명으로 주장하지 않는다. 연구 후보는 **VGGT-Ω 초기 예측의 신뢰도, 다중 카메라 관측 출처, 시차각을 이용해 한정된 자원에서 공유 기하를 선택적으로 재정렬하는 절차**와 그 실험적 효과에 있다.

---

## 3. 시스템 전체 흐름

~~~text
RGB 입력 N=3(기본), 4(확장)
    │
    ▼
[Stage A] VGGT-Ω 추론 (GPU, inference_mode)
    ├─ camera: K_i, T_c←w,i
    ├─ depth: D_i
    ├─ depth confidence: Q_i
    └─ preprocessed RGB: I_i
    │     저장 후 모델 해제 / 별도 프로세스 권장
    ▼
[Stage B] Depth 역투영 → 월드 점 생성
    ├─ source frame / source pixel
    ├─ initial position / color / confidence
    └─ invalid / padded / background mask
    ▼
[Stage C] 관측 대응 추정 및 단일 공유점 융합
    ├─ voxel candidate search
    ├─ reprojection + depth + normal gating
    ├─ 3D representative points X_k
    └─ observation lists O_k
    ▼
[Stage D] Multi-view visibility / consistency
    ├─ project X_k to camera i
    ├─ frustum & positive-depth check
    ├─ z-buffer + depth agreement
    ├─ baseline/parallax check
    └─ visibility mask V_ki (periodic refresh)
    ▼
[Stage E] Differentiable Point Rendering
    └─ one shared X → N rendered RGB images & coverage
    ▼
[Stage F] Multi-view optimization
    ├─ photo reconstruction loss
    ├─ initial geometry / surface / displacement prior
    ├─ optionally cross-view depth consistency
    └─ gradient → update X_k
    │
    ├─ periodic visibility/match refresh
    └─ validation / early stopping
    ▼
[Stage G] 정량/정성 평가 + Ablation + 보고
    ├─ input & held-out image quality
    ├─ GT geometry (if available)
    ├─ cross-view consistency / outlier ratio
    ├─ runtime / peak VRAM
    └─ failure case analysis
~~~

각 단계가 산출한 중간 파일을 저장해 추론 오류와 기하 최적화 오류를 분리한다.

---

## 4. 실행 환경 및 메모리 전략

### 4.1 실험 장비

| 항목 | 계획 |
| --- | --- |
| GPU | NVIDIA RTX 5060 8GB VRAM |
| 입력 수 | 기본 3장, 비교 2장, 확장 4장 |
| 실험 방식 | 오프라인 재구성 및 최적화 |
| 정밀도 | VGGT-Ω 추론은 공식 권장 경로부터 검증; 렌더링/위치 변수는 우선 float32 |
| 운영체제 | 실제 장비에서 CUDA 지원 OS 및 드라이버 버전 기록 |
| 실행 관리 | Python venv/conda; 의존성 버전과 Commit SHA 고정 |

**원본 VGGT에서 4장 제한을 경험했다는 실측을 VGGT-Ω로 일반화하지 않는다.** VGGT-Ω README의 A100 624×416, 1B-512 피크 VRAM 보고값은 1장 6.02GB, 10장 6.67GB이다. 이는 **A100에서의 전체 추론 프로그램** 측정이며 RTX 5060, 실행 중인 데스크톱 메모리 사용량, 이후의 최적화와 동일하지 않다.

### 4.2 체크포인트

- 1차: <code>VGGT-Omega-1B-512</code> + <code>mode="max_size"</code>, <code>image_resolution=512</code>.
- 대안: 공식적으로 공개된 별도 416 체크포인트(벤치마크 재현용)의 적합성을 검토한다. 체크포인트와 입력 해상도를 정확히 대응시키고 임의 혼용하지 않는다.
- Checkpoint 파일은 Git에 커밋하지 않는다.
- 외부 모델의 라이선스·상업적 이용 제한을 확인한다. 본 연구 산출물의 라이선스와 구분한다.

### 4.3 GPU 사용 단계 분리

**프로세스 A(추론):** 모델 로드 → 2/3/4장 추론 → CPU 디스크에 카메라/Depth/Confidence/정렬된 RGB/전처리 메타데이터 저장 → 프로세스 종료.

**프로세스 B(최적화):** 중간 결과 로드 → 후보 점 생성 → 포인트 융합 → 미분 가능 Renderer → 위치 최적화.

단순 <code>empty_cache()</code> 호출만으로 살아있는 모델 텐서가 해제되지는 않는다. **서로 다른 프로세스**를 사용해 그래프와 모델 메모리가 완전히 제거되는 경로를 기본값으로 한다.

### 4.4 초기 메모리 절감 설정(성능 주장 아님)

- 3장, 입력 긴 변 512 이하, 렌더 256×256 또는 종횡비 유지한 유사 면적부터 시작.
- 활성 공유 점 수 20k → 50k → 100k 순차 증가.
- Point Rasterizer의 <code>points_per_pixel</code>을 4로 시작, 8·16을 순차 비교.
- 카메라별 Forward+Loss를 순차 처리하고 가능하다면 각 뷰의 기울기를 누적.
- 높은 해상도·많은 점·다수 뷰를 한 번에 처리하지 않는다.
- <code>torch.cuda.max_memory_allocated()</code>, <code>max_memory_reserved()</code>를 구분해 기록.
- 각 단계 OOM일 때 (1) 활성 점 수 (2) 렌더링 해상도 (3) points_per_pixel (4) 관측 쌍 수 순으로 줄인다.
- 8GB 장비에서 <code>points_per_pixel</code>을 크게 잡으면 픽셀×후보점 텐서가 커질 수 있음을 경계한다.

---

## 5. 데이터셋 및 실험 샘플 선정

### 5.1 1차 데이터: 정적 실내 장면

최소 두 종류의 장면을 준비한다.

1. **텍스처 풍부한 장면:** 책장, 물체, 모서리, 다채로운 무늬. Gradient가 실제로 나오는지 확인하기 쉽다.
2. **저텍스처 장면:** 흰 벽, 바닥, 복도. Photometric Loss의 모호성을 확인한다.

카메라 3장은 동일 영역을 충분히 공유하지만 카메라 중심에 적절한 시차가 존재하도록 고른다. 거의 동일한 프레임 3장은 깊이 검증에 부적합하다. 회전만 있고 이동이 없는 구간도 우선 제외한다.

### 5.2 GT를 가진 벤치마크

- **TUM RGB-D:** RGB만 모델에 입력하고 제공되는 Depth/Camera 정답은 **평가 전용**으로 사용한다. 센서 정렬·해상도·타임스탬프 일치를 확인한다.
- **Replica:** 가상 장면의 카메라·Depth GT로 기하 정확도를 검증하기 쉽다. 이용 가능 라이선스와 파일 구성을 확인한다.

GT가 없는 사내 촬영 영상은 정성 실험에 사용할 수 있으나, 그 결과만으로 실제 깊이 정확도 개선을 주장하지 않는다. 회사 데이터는 반출·공개 가능 여부를 먼저 확인한다.

### 5.3 학습·평가 뷰 분리

- 최소 구현: 입력 3장으로 VGGT-Ω 및 지도 구성, 동일 3장으로 최적화.
- 일반화 평가: **최적화에 포함되지 않은 별도 1장 이상**을 확보한다. 테스트 카메라의 GT Pose가 있다면 사용하고, 예측 Pose라면 Pose 오차를 명시한다.
- 입력이 모두 4장뿐이라면 3장을 최적화에 사용하고 1장을 평가용으로 분리하는 설정을 추가한다.
- 최적화에 사용한 원본 영상과 미사용 영상의 지표는 별도 표로 보고한다.

### 5.4 데이터 전처리 추적

VGGT-Ω의 <code>load_and_preprocess_images</code>는 종횡비 보정, 크기 변경, 경우에 따라 패딩을 수행한다. **최적화 및 평가의 RGB/Depth/Intrinsics는 동일한 이미지 격자**를 사용해야 한다.

- 원본 → Crop → Resize → Pad의 변환 파라미터를 기록.
- 패딩 픽셀은 원본 관측이 아니므로 손실에서 제외.
- GT Depth를 비교할 때도 같은 픽셀 변환 및 유효영역을 적용.
- 카메라 내부행렬을 다른 해상도로 옮기면 fx,fy,cx,cy를 같은 스케일 및 오프셋으로 변환.
- 전처리된 영상과 모델 출력의 픽셀 좌표계를 반드시 일치시킨다.

---

## 6. 좌표계·기하 수식 및 구현 계약

### 6.1 기호

| 기호 | 정의 |
| --- | --- |
| N | 입력 카메라 수(3 또는 4) |
| I_i | i번째 전처리 RGB 영상 |
| K_i | i번째 Intrinsic 3×3 |
| R_i,t_i | i번째 world-to-camera 회전/이동 |
| D_i(u) | i번째 영상 픽셀 u의 깊이 |
| Q_i(u) | 초기 Depth Confidence(확률로 단정하지 않음) |
| X_k | 공유 Point Cloud의 k번째 월드 3D 점(최적화 변수) |
| X_k⁰ | 초기 공유 점 위치 |
| C_k | 공유 점의 고정 RGB 색상 |
| O_k | 점 k에 대응된 원본 관측 (camera, pixel) 목록 |
| V_ki | 점 k의 카메라 i 관측 가능 여부 추정 |
| R(·) | 미분 가능 Point Renderer |

### 6.2 Depth 역투영

픽셀 좌표 u=(u,v), 동차 좌표 ũ=(u,v,1)ᵀ, 깊이 d=D_i(u)일 때:

\[
p_{c_i}(u)=d K_i^{-1}\tilde u
\]

\[
p_w(u)=R_i^\top\left(p_{c_i}(u)-t_i\right)
\]

### 6.3 다른 카메라로의 투영

\[
p_{c_j}=R_j X_k+t_j,\qquad
\tilde u_j \sim K_j p_{c_j}
\]

\[
u_j=\left(f_{x,j}\frac{x_j}{z_j}+c_{x,j},\
             f_{y,j}\frac{y_j}{z_j}+c_{y,j}\right)
\]

단, z_j>0, 화면 안쪽, 신뢰할 수 있는 표면인지 검사한다.

### 6.4 확인할 규약

- OpenCV 카메라 좌표계 / 오른손·왼손 변환 여부.
- world-to-camera와 camera-to-world 행렬 혼동 여부.
- Depth가 **카메라 Z 깊이**인지, Ray 길이인지. 공식 역투영 코드 기준 Z 깊이로 사용한다.
- 픽셀 중심 (u+0.5,v+0.5) 규약을 Renderer와 영상 샘플러에서 통일.
- (H,W) 순서, RGB/BGR, float [0,1]/uint8 [0,255].
- VGGT 단안 스케일의 임의성: GT 비교 전 필요 시 하나의 **고정된 Sim(3) 또는 scale alignment**를 별도로 적용하고 정렬 기준을 명시한다.

---

## 7. 공유 Point Cloud 생성·융합

### 7.1 관측 레코드

초기에는 픽셀별 관측을 개별 레코드로 유지한다.

~~~python
# 개념 구조. 실제 구현에서는 배열/CSR로 압축할 것.
Observation = {
    "frame_id": int,
    "pixel_uv": (float, float),
    "world_xyz_initial": (float, float, float),
    "depth_initial": float,
    "depth_conf_raw": float,
    "rgb": (float, float, float),
    "valid": bool,
}
~~~

각 레코드에 원본 프레임·원본 픽셀의 provenance를 반드시 남긴다. 단순 3D 좌표 병합 이후 이 정보가 사라지면 자기 재현 편향을 분석하기 어렵다.

### 7.2 초기 필터

- NaN/Inf, 음수 또는 0 Depth, 영상 Padding 제외.
- Confidence 분포를 먼저 저장한 뒤 **분위수 기반** 또는 검증된 임계값으로 필터. 원시 Confidence가 0~1 확률이라고 가정하지 않는다.
- 동적 물체, 유리, 거울, 하늘, 포화/과노출 영역은 가능하면 별도 Mask로 취급.
- 거리 상·하한과 샘플링 간격은 장면 크기에 따라 기록하고 조절한다.

### 7.3 단순 연결과 실제 융합을 분리

**Baseline F0:** 모든 관측 점들을 같은 월드 좌표계에 연결한다. 동일 표면의 중복점을 그대로 유지한다.

**Fusion F1:** 가까운 점을 합치되 다음 조건을 만족하는 후보만 같은 물리적 표면이라고 본다.

1. 공간 거리: \(\|p_a-p_b\|<\tau_x\) (단위·스케일 의존).
2. 다른 카메라로의 재투영 위치 및 Depth 동의.
3. 가능하면 Local Normal 방향 일치.
4. Color 차이는 조명 변화의 영향을 받으므로 보조적 게이트로 사용.

구현은 voxel hash로 근접 후보를 찾고 union-find/클러스터링 또는 대표점 축적을 사용한다. **가까운 3D 점이라는 이유만으로 서로 다른 표면(앞면/뒷면)을 병합하면 안 된다.**

### 7.4 공유점 초기값과 속성

각 관측 그룹 \(G_k\)의 위치·색상 초기값:

\[
X_k^0=\frac{\sum_{o\in G_k}w_o p_o}{\sum_{o\in G_k}w_o}
\]

\[
C_k=\operatorname{robust\_aggregate}\{I_{i(o)}(u_o)\}
\]

Confidence는 단순 합산보다 **클리핑·정규화된 상대 가중치**를 사용하고, 색상은 우선 Median 또는 Robust Mean으로 고정한다. 각 점의 관측 목록 O_k는 희소 CSR 형태로 유지한다.

### 7.5 점 자료구조 제안

~~~python
SharedPointMap:
    xyz0: float32 [M,3]          # 초기 세계좌표
    xyz:  float32 [M,3]          # learnable
    rgb:  float32 [M,3]          # 초기에는 고정
    normal0: float32 [M,3]       # 가능하면 국소 PCA 또는 Depth로 계산
    radius: float32 [M]          # 초기에는 고정
    conf: float32 [M]            # 정규화된 상대 신뢰도
    obs_offsets: int32 [M+1]     # CSR
    obs_camera: uint8/int16 [K] # 관측 프레임
    obs_pixel: float32 [K,2]    # 원본 관측 픽셀
    owner_camera: int16 [M]      # 대표 관측 소유 카메라
    active: bool [M]
~~~

여기서 M은 공유점 개수이며 영상 수 N과 구분한다.

---

## 8. 관측·가시성 추정

### 8.1 정의

관측 출처 **O_k**와 현재 위치에서 보일 수 있는 카메라 집합 **V_k**는 다르다.

- O_k: 데이터 연관으로 '동일한 물리적 3D 점'이라고 판단한 실제 원본 관측 목록.
- V_k: 현재 X_k를 투영했을 때 해당 카메라에서 보인다고 **추정**되는 집합.
- 이미지 내부에 투영되었다는 사실만으로 실제 관측되었다고 할 수 없다.

### 8.2 Visibility 검사 절차

각 후보 점 X_k, 카메라 i:

1. \(p_c=R_i X_k+t_i\), z>0 검사.
2. 픽셀 투영 및 원본 유효 영역 내 검사.
3. 현재 렌더러 Z-buffer에서 표면까지의 깊이 \(D_i^{render}(u)\)와 비교.
4. VGGT 초기 Depth \(D_i^{VGGT}(u)\)와도 비교하되, 이 값은 **오차가 있을 수 있는 Prior**라는 점을 유지.
5. 깊이 허용 차이는 고정 절대 임계값보다 장면 스케일에 맞는 절대+상대 임계값 병용.
6. 해당 픽셀의 Confidence, 경계/물체 가림 여부 검사.
7. 각 이미지에서 유효하게 관찰될 가능성이 있는 점만 Loss 계산에 포함.

예시 게이트:

\[
|z_i(X_k)-D_i(u_i)| <
\tau_{abs}+\tau_{rel}D_i(u_i)
\]

이는 초기 후보 추정용으로 사용한다. **초기 VGGT Depth 자체가 틀리면 실제 좋은 점까지 탈락**할 수 있으므로 임계값을 민감도 실험한다.

### 8.3 관측 수·시차각

점 k를 보는 두 카메라 중심 C_i,C_j에 대해:

\[
\theta_{ij,k}=\cos^{-1}
\frac{(X_k-C_i)\cdot(X_k-C_j)}
{\|X_k-C_i\|\|X_k-C_j\|}
\]

- 관측 수가 2 이상이어도 시차각이 너무 작으면 깊이는 잘 결정되지 않는다.
- 점별 <code>n_observed</code>, <code>parallax_median</code>, <code>parallax_max</code>를 저장한다.
- 최초 실험에서는 관측 2회 이상/비영(非零) 시차를 가진 점만 적극 최적화하고 단독 관측점은 Anchor로 유지하는 실험을 비교한다.
- 절대 각도 임계값은 데이터 분포를 본 후 정한다. 고정된 5° 등을 보편적 정답으로 취급하지 않는다.

### 8.4 마스크 재계산

- 초기 Data Association은 신중히 설정하고 최적화 중 **빈번한 무조건 병합·분리는 하지 않는다.**
- Visibility/coverage는 10~25 iteration마다 재계산하는 설정부터 시작한다.
- 이산적인 가시성 판정은 기본적으로 <code>detach</code>한다. Soft Rasterization 자체는 미분 가능하게 유지한다.
- 갑작스러운 점 추가·제거로 발생하는 불안정은 모니터링하고 필요하면 마스크 변화율을 제한한다.
- 평가 지표를 현재 Mask의 유효 픽셀만으로 계산하면 분모가 변해 성능이 좋아 보일 수 있으므로 **고정 평가 마스크**도 반드시 사용한다.

---

## 9. 미분 가능한 Point Renderer 설계

### 9.1 Renderer가 해야 할 일

입력: 공유 XYZ[M,3], RGB[M,3], 반경/가중치, 고정된 K_i, R_i, t_i.

출력: 렌더 RGB \(\hat I_i\), 누적 Weight/Alpha, Z-buffer 또는 Rendered Depth, 유효 Coverage Mask.

핵심 요구는 **\(\partial \hat I_i/\partial X_k\)**가 유효하게 계산되는 것이다.

### 9.2 1차 선택: PyTorch3D

후보: <code>Pointclouds</code>, <code>PointsRasterizer</code>, <code>PointsRenderer</code>, <code>AlphaCompositor</code> 또는 기능상 필요에 맞는 compositor.

- 점마다 RGB를 feature로 사용한다.
- Soft splat radius와 <code>points_per_pixel</code>을 제어한다.
- Point Rasterizer와 카메라 좌표계를 맞추기 위한 명시적 adapter를 만든다.
- 배경색·빈 픽셀 처리·충돌 지점의 합성 순서를 통제한다.
- 색상 고정이 목표이므로 이미지 보정 CNN을 추가하지 않는다.

**주의:** PyTorch3D의 카메라 좌표계와 VGGT-Ω의 OpenCV Extrinsics는 그대로 호환된다고 가정하지 않는다. 축 반전, screen/NDC 변환, 영상 수평·수직 반전 여부를 테스트 이미지로 확인한다.

### 9.3 미분 가능성이 보장되지 않는 부분

- 정수 픽셀 반올림과 hard visibility.
- 이산적인 최근접 점 선택이나 hard Z-buffer 교체.
- 완전히 빈 픽셀에서 기여 가능한 점이 없어 Loss Gradient가 0이 되는 경우.
- 동일 카메라 Ray를 따라 이동하는 깊이 변화: 자기 영상의 좌표상 변화가 없어서 **다른 카메라의 시차 또는 별도 기하 제약이 있어야** 결정된다.

따라서 'Loss.backward()가 실행된다'와 '올바른 깊이 Gradient가 존재한다'는 별개이다.

### 9.4 필수 Gradient 검증

코드 구현 전에 두 개의 합성 장면을 만든다.

**Test A: 1개 점 + 1대 카메라**
- 점의 X를 \(\epsilon\)만큼 변화시키고 RGB Loss 변화를 유한차분으로 계산.
- Autograd의 \(dL/dX\)와 방향·크기 비교.
- 같은 카메라 Ray 방향으로 이동하면 self-view 영상 투영 오차의 깊이 신호가 매우 약하거나 0임을 확인.

**Test B: 1개 점 + 이동한 2대 카메라**
- 두 번째 카메라의 시차를 주면 초기 깊이 오차에 대한 손실 경사가 나타나는지 확인.
- \(dL/dx,dL/dy,dL/dz\)를 중심차분
  \((L(x+\epsilon)-L(x-\epsilon))/(2\epsilon)\)과 비교.
- 유한차분 오차, 점 반경, 해상도, Soft Rasterizer의 온도/반경 영향을 기록.

**Test C: 최소 표면**
- 텍스처가 있는 평면 Point Grid를 생성하고 GT 위치에서 일부 점을 인위적으로 이동.
- 2~3대 카메라로 최적화한 후 GT 좌표로 회복되는지 검증.
- '학습 이미지 PSNR'이 아니라 **3D 위치 오차 감소**를 우선 성공 기준으로 삼는다.

### 9.5 가시성 및 포인트 색상

렌더링할 때 각 점의 RGB가 고정되어 있더라도 색상 합성 규칙과 반경 때문에 원본 카메라에서도 렌더링 오차가 남을 수 있다. 이를 '깊이가 잘못되었다'는 증거로 해석하지 않는다.

- RGB는 Linear/Display 공간 일관성을 맞춘다. 첫 실험에서는 전처리된 RGB를 그대로 사용하되 손실 경로를 고정한다.
- 사진별 자동노출·화이트밸런스 차이는 후속 실험에서 별도의 보정 변수로 고려할 수 있지만 **첫 실험에서는 점 위치 개선 효과와 혼동하지 않도록 제외**한다.
- 최소 렌더링은 Geometry-only 방식(고정점 색상, 학습 이미지 보정 없음)을 유지한다.

---

## 10. 최적화 변수와 업데이트 방식

### 10.1 기본 목적함수

공유점 전체를 \(X=\{X_k\}_{k=1}^M\), 렌더러를 \(\mathcal R\), 고정 카메라들을 \(C_i=(K_i,R_i,t_i)\)라 하자.

\[
X^*=\arg\min_X \mathcal L(X)
\]

\[
\mathcal L =
\lambda_p\mathcal L_{photo}
+\lambda_0\mathcal L_{anchor}
+\lambda_s\mathcal L_{surface}
+\lambda_c\mathcal L_{crossdepth}
\]

여기서 처음에는 \(\lambda_p>0\)만 활성화해 동작을 점검하고, 이후 Anchor/Surface/CrossDepth를 순차적으로 추가한다. 모든 가중치는 **실험적으로 정할 후보**이다.

### 10.2 Photometric Loss

\[
\mathcal L_{photo}
=
\frac{\sum_{i,u}M_i(u)\,\rho(\hat I_i(u)-I_i(u))}
     {\sum_{i,u}M_i(u)+\epsilon}
\]

- 유효 픽셀 마스크 M_i는 **원본 이미지 유효영역, 신뢰 가능한 Coverage, 가시성**에서 만든다.
- Robust Charbonnier/L1부터 시작. 선택적으로 SSIM 성분을 비교.
- Loss는 카메라 수·픽셀 수에 따라 정규화하여 장면간 비교 가능하게 한다.
- 빈 영역을 배경색으로 채우면 Loss가 큰데 Gradient가 0일 수 있다. 학습/평가 Coverage를 반드시 같이 기록한다.
- 초기에는 점의 색상 고정. 점 색상을 동시에 최적화해 위치 오차를 감추지 않는다.

### 10.3 자기 재현 편향 방지

단일 장면이라고 하더라도 초기 구성 시 동일 표면을 중복 대표하는 점이 남으면 각 카메라가 자신에서 만들어진 점을 주로 보는 문제가 발생한다.

1. **필수:** 중복 표면 융합 및 관측 출처 유지.
2. **비교군:** 전체 카메라 손실 vs **cross-view 중심 손실**.
3. 후자의 구현 후보: 특정 카메라 i의 오류를 평가할 때 i에서만 나온 점의 가중치를 0으로 하거나, **다른 카메라의 관측이 존재하는 점만** 사용한다.
4. 이는 이미지마다 별도의 지도를 최적화하는 것이 아니다. 동일한 공유 \(X_k\)를 사용하고 렌더링 마스크만 카메라별로 달리한다.
5. Cross-view에서 미관측 영역을 억지로 복원할 수 없으므로, 각 손실의 평가 영역과 Coverage를 함께 보고한다.

### 10.4 Anchor Loss

\[
\mathcal L_{anchor}
=
\frac1M\sum_k q_k\,\rho\!\left(
  \frac{\|X_k-X_k^0\|}{s_{scene}+\epsilon}
\right)
\]

q_k는 초기 신뢰도·관측 수에 따른 보존 가중치. 실제 오차를 확률적으로 보정한 Confidence라고 가정하지 않는다.

**과도한 Anchor**는 기존 깊이 오류를 고착시킬 수 있으므로 0, 약함, 중간, 강함 조건을 비교한다.

### 10.5 Local Surface Loss

가능한 선택지:

**점-평면 일치:** 초기 인접 점 집합 \(\mathcal N(k)\)의 법선 \(n_l^0\)에 대해

\[
\mathcal L_{plane}
=\sum_{k,l\in\mathcal N(k)}
w_{kl}\left[n_l^{0\top}(X_k-X_l)\right]^2
\]

**국소 변형 보존:** 상대 변위 \((X_k-X_l)-(X_k^0-X_l^0)\)를 정규화.

주의: 가까운 점이 다른 면에 속하는 모서리에서는 Surface Loss를 줄이거나 배제해야 한다. 인접 그래프는 초기 추정 후 고정하고, 장면 변형이 커지면 안전하게 재구축한다.

### 10.6 Cross-view Depth Consistency

공유점 \(X_k\)가 카메라 i에서 보일 때 \(z_{ki}\)와 해당 시점의 초기 Depth 또는 검증 가능한 대응 관측 Depth를 비교한다.

\[
\mathcal L_{crossdepth}
=\sum_{(k,i)\in \mathcal V}
w_{ki}\,\rho\left(z_{ki}-D_i(\pi_i(X_k))\right)
\]

이는 **불완전한 초기 VGGT Depth에 대한 동의 항**이지 GT 기하 오차 자체가 아니다. 너무 강하면 네트워크의 일관된 편향을 보존할 수 있다. Depth 자체가 동일 공유 지도에서 렌더된 결과와 비교되는 순환 정의가 되지 않도록 대상 데이터를 명확히 구별한다.

### 10.7 세 가지 위치 매개변수 비교

**A. XYZ 자유 이동**

\[
X_k=X_k^0+\Delta_k,\qquad\Delta_k\in\mathbb R^3
\]

- 장점: 초기 Ray 밖으로도 이동 가능.
- 위험: 표면 찢어짐, 색상 적합을 위한 비물리적 이동.

**B. Source-camera Ray 방향 깊이 이동**

\[
X_k=C_{owner(k)} + d_k\,r_{owner(k),k}
\]

- 초기 소유 카메라의 **고정된 월드 단위 Ray**를 사용한다.
- \(d_k=\operatorname{softplus}(a_k)+d_{min}\) 등 양수 제약. 또는 \(d_k=d_k^0\exp(\delta_k)\).
- 장점: 변수 1개/점, 초기 기하 구조 보존에 유리.
- 단점: **하나의 공유점에 소유 카메라가 하나만 정해지는 점**을 명시해야 한다. 그 점이 다른 카메라의 관측과도 연관된다는 사실은 바뀌지 않는다. 초기 Pose나 소유 Ray가 잘못되면 실제 정답점에 도달할 수 없다.

**C. 초기 표면 법선 방향 이동**

\[
X_k=X_k^0+\alpha_k n_k^0
\]

- 장점: 공유표면의 두께/깊이 오차를 줄이는 단순한 형태.
- 위험: 초기 Normal이 노이즈·모서리·잘못된 융합으로 오염될 수 있다.

권장 순서: **B(Ray-depth)로 먼저 안정성을 확보 → A(XYZ)를 비교 → C(Normal)를 추가**. 원칙적으로 최적화 변수는 서로 다른 방식이어도 같은 공유 3D 점 집합을 갱신한다.

### 10.8 학습률 및 제약

- 초기값(예시): Adam 1e-3, 200~500 iteration, gradient clip, displacement bound. 이 값은 검증 결과가 아니라 **출발점**이다.
- 위치 단위가 cm인지 m인지 불명확하면 Learning Rate가 의미를 잃는다. scene-scale 정규화 후 최적화하고 원래 단위로 복구한다.
- 변위량 \(\|\Delta_k\|\)의 중앙값, 95분위값, 최댓값 기록.
- Loss가 감소해도 기하가 악화될 수 있어 validation geometry가 있으면 기준으로 early stopping.
- Surface/Anchor 가중치는 모든 장면에 고정해서 먼저 비교한 다음, 필요할 때만 장면별 추가 실험을 한다.

---

## 11. 구현 의사 코드 및 모듈 경계

### 11.1 저장소 구조 제안

~~~text
vggt_omega_adop/
├── docs/
│   ├── vggt_omega_pointmap_refinement_experiment_plan.md
│   └── experiments/
│       └── pointmap_refinement/
│           ├── index.md                 # 전체 실험 현황과 보고서 링크
│           └── E3/                      # E0~E9 및 세부 코드별 동일 구조
│               ├── README.md            # 목적·조건·실행 이력 요약
│               └── <run_id>/
│                   ├── progress.md      # 중간 결과 및 실패·변경 기록
│                   ├── report.md        # 해당 실행의 결과 보고서
│                   └── figures/         # 보고서용 비교 이미지·그래프
├── experiments/
│   └── pointmap_refinement/
│       └── E3/
│           ├── README.md               # 재현 절차와 완료 기준
│           ├── configs/                # 실험별 설정 및 변경 조건
│           └── scripts/                # 실험별 실행 진입점
├── configs/
│   ├── default_3views.yaml
│   └── ablations.yaml
├── src/
│   ├── infer_vggt_omega.py
│   ├── camera_geometry.py
│   ├── unproject.py
│   ├── fuse_points.py
│   ├── visibility.py
│   ├── point_renderer.py
│   ├── losses.py
│   ├── optimize_points.py
│   ├── evaluate.py
│   └── io_schema.py
├── tests/
│   ├── test_camera_roundtrip.py
│   ├── test_renderer_gradients.py
│   ├── test_visibility.py
│   ├── test_fusion.py
│   └── test_synthetic_recovery.py
├── scripts/
│   ├── run_inference.sh
│   ├── run_refinement.sh
│   └── run_ablation.sh
├── data/                 # 원본 데이터: .gitignore
├── checkpoints/          # 모델 가중치: .gitignore
├── thirdparty/           # Commit을 고정한 외부 코드: .gitignore
└── results/
    └── pointmap_refinement/
        └── <run_id>/
            └── stages/
                └── E3/  # 실험코드별 중간·최종 산출물, 상세 구조는 17.1절
~~~

**주의:** 위는 앞으로의 권장 구조이다. 현재 해당 파일들이 존재한다는 뜻이 아니다.

운영 방식은 참고 저장소 [gradresearch_vggt_mast3r_slam의 README](https://github.com/seaeast2/gradresearch_vggt_mast3r_slam/blob/main/README.md)와 [E0 재현 절차](https://github.com/seaeast2/gradresearch_vggt_mast3r_slam/blob/main/experiments/pointmap_comparison/E0/README.md)를 따른다. 실험코드별 재현 코드와 실행 회차별 `results/<연구명>/<run_id>/stages/<실험코드>/`를 분리하고, 설정·로그·Manifest·해시를 보존한다. 이번 프로젝트에서는 **중간·최종 보고서도 `docs/experiments/pointmap_refinement/<실험코드>/<run_id>/`로 분리**한다.

`src/`와 공통 `configs/`, `scripts/`는 공통 구현이며, 실험별 설정과 진입점은 `experiments/pointmap_refinement/<실험코드>/`에 둔다. 코드·설정·보고서·소규모 보고용 그림은 Git으로 관리하고, 원본 데이터·모델·외부 코드·대용량 `results/`는 제외한다. 제외된 파일은 보고서에 저장 위치·출처·해시·재생성 절차를 기록한다. 참고 저장소의 모델·데이터·실험 결과 수치는 이번 실험의 결과로 옮기지 않는다.

### 11.2 VGGT-Ω 추론 단계(실제 API 기반 의사 코드)

~~~python
import torch
from vggt_omega.models import VGGTOmega
from vggt_omega.utils.load_fn import load_and_preprocess_images
from vggt_omega.utils.pose_enc import encoding_to_camera

images = load_and_preprocess_images(
    paths, mode="max_size", image_resolution=512
)
model = VGGTOmega().cuda().eval()
state = torch.load(checkpoint_path, map_location="cpu")
model.load_state_dict(state)

with torch.inference_mode():
    pred = model(images.cuda())
    extr, intr = encoding_to_camera(
        pred["pose_enc"], pred["images"].shape[-2:]
    )
    # depth: predicted depth; depth_conf: raw confidence
    # save CPU tensors + exact preprocessed RGB/metadata to NPZ/PT

# inference 종료 후 별도 optimizer 프로세스 실행
~~~

위 코드는 간략화된 API 사용 예이다. 실제 로더 옵션·저장 텐서 차원·라이브러리 버전은 공식 코드와 대조한다.

### 11.3 공유점 최적화 단계(인터페이스 의사 코드)

~~~python
state = load_inference_artifacts(config.source_artifact_path)
# 입력 경로는 source experiment/run ID 및 SHA-256과 함께 기록한다.
observations = unproject_to_observations(state)
shared = fuse_observations(observations, state.cameras)

# 선택적 위치 파라미터화: xyz / ray_depth / normal
geometry = LearnableSharedGeometry(shared, mode="ray_depth")
renderer = DifferentiablePointRenderer(config.renderer)
optimizer = torch.optim.Adam(geometry.parameters(), lr=config.lr)

for step in range(config.steps):
    if step == 0 or step % config.visibility_update_interval == 0:
        visibility = compute_visibility(
            geometry.xyz.detach(), state.cameras, shared, config
        )

    optimizer.zero_grad(set_to_none=True)
    xyz = geometry.xyz  # 동일한 [M,3] 텐서를 모든 카메라에서 사용
    total = torch.zeros((), device=xyz.device)

    for cam_idx in config.train_cameras:
        rgb_hat, render_depth, coverage = renderer(
            xyz, shared.rgb_fixed, shared.radius_fixed,
            state.cameras[cam_idx],
        )
        valid = build_loss_mask(
            cam_idx, coverage, visibility, state, shared
        )
        total = total + photometric_loss(
            rgb_hat, state.rgb[cam_idx], valid
        )

    total = total + geometry_regularizers(geometry, shared, config)
    total.backward()
    monitor_gradients(geometry, total, step)
    clip_gradients(geometry)
    optimizer.step()

    if should_validate(step):
        evaluate_and_checkpoint(...)
~~~

정확한 클래스명은 본 프로젝트에서 정의할 인터페이스다. PyTorch3D의 API 이름과 혼동하지 않는다.

### 11.4 구현 우선순위

1. **Camera Round-trip 테스트**가 먼저다.
2. 다음은 **Renderer Gradient 테스트**다.
3. 그다음 공유점 Association/Fusion.
4. 마지막에 실장면 전체 최적화.

렌더링이 원본과 달라진 이유가 카메라 좌표 변환 오류인지 최적화 문제인지 구분하지 못한 상태에서 본 실험을 진행하지 않는다.

---

## 12. 정량 평가 프로토콜

### 12.1 영상 품질

| 지표 | 방향 | 평가 구분 |
| --- | --- | --- |
| MAE 또는 Robust RGB Error | 낮을수록 좋음 | Train/held-out 별도 |
| PSNR | 높을수록 좋음 | 고정 유효영역, Train/held-out |
| SSIM | 높을수록 좋음 | 동일 해상도·마스크 |
| Coverage (%) | 높을수록 좋음 | 원본 유효영역 대비 |
| Invalid/Hole Ratio (%) | 낮을수록 좋음 | 전/후 렌더 비교 |

**반드시 고정된 평가 픽셀 집합**에서 같은 마스크로 전/후를 비교하고, 추가로 조건별 유효 Coverage를 따로 기록한다. 그렇지 않으면 어렵거나 틀린 픽셀을 마스크에서 삭제하여 PSNR만 높일 수 있다.

### 12.2 기하 정확도

| 지표 | 방향 | 의미 |
| --- | --- | --- |
| GT Depth AbsRel, RMSE | 낮을수록 좋음 | 평가 카메라에서의 표면 깊이 |
| Accuracy (recon→GT) | 낮을수록 좋음 | 추정점이 실제 표면에서 떨어진 거리 |
| Completeness (GT→recon) | 낮을수록 좋음 | 실제 표면이 얼마나 덜 누락되었는가 |
| Chamfer Distance | 낮을수록 좋음 | 양방향 기하 거리 |
| Multi-view Depth Disagreement | 낮을수록 좋음 | 동일 표면의 시점간 편차 |
| Outlier Ratio | 낮을수록 좋음 | 정의된 거리 임계값 밖의 점 비율 |

GT Depth는 **모델/손실의 입력으로 사용하지 않는다.** 평가에서만 활용한다.

단안 복원의 Global Scale 모호성을 고려해, 공정한 GT 정렬 방법을 고정한다. 정확도 개선을 보이기 위해 전후 장면에 **각각 다른 유리한 정렬을 임의 선택하는 방식은 피하고**, 정렬 방식과 자유도를 명시한다.

### 12.3 최적화 및 자원

- 전체 추론 실행시간과 최적화 실행시간 분리.
- Peak allocated / reserved VRAM, Point 수, 렌더 해상도, points-per-pixel.
- Iteration별 모든 Loss 항, Gradient Norm, 점 변위 통계.
- 유효 관측점 비율, 평균 관측 카메라 수, 재융합/마스크 변경 비율.
- 실패·OOM·NaN 발생 건수.
- CPU RAM 사용량과 디스크 중간 결과 크기.

### 12.4 성공·보류·실패 판정

**성공:** 3개 이상 독립 장면에서 GT Depth 또는 3D 거리 기반 기하 지표가 반복적으로 개선되고, 미사용 시점 렌더링 및 Coverage를 희생하지 않으면서 재현 가능한 실행 자원을 보인다.

**부분 성공:** Train RGB와 Cross-view Consistency는 개선되나 GT Geometry 개선이 불명확. 이 경우 '기하 정확도 개선' 대신 '영상 적합 및 관측 일관성 개선'으로 결론을 제한한다.

**실패 또는 재설계:** Train PSNR만 상승하고 GT 기하·held-out 렌더가 악화; 초기 장면의 표면 중복이 지속; Gradient가 0/NaN; 8GB에서 최소 구성도 실행 불가.

임계 수치를 사전에 임의의 확정 성과처럼 쓰지 않고, 파일럿 분산·반복 횟수를 측정한 후 최종 프로토콜에 고정한다.

---

## 13. 실험 매트릭스 및 Ablation

**실험코드는 아래 비교 조건을 식별한다.** 참고 저장소의 동명 코드와 연구 내용이 같다는 뜻은 아니다. 환경 준비를 위해 E0의 의미를 바꾸지 않으며, 준비·합성 검증은 `P0`(환경), `P1`(좌표계), `P2`(Renderer/Gradient)로 별도 기록한다. 이 코드들도 17절의 동일한 격리·보고 규칙을 적용한다.

| ID | 초기 표현 | Renderer/Loss | 위치 변수 | 가시성/기하 제약 | 목적 |
| --- | --- | --- | --- | --- | --- |
| E0 | VGGT-Ω 원본 역투영 | 없음 | 없음 | 없음 | 원본 기준 |
| E0a | E0 원본, 프레임별 빨강/초록/파랑 | Native z-buffer 출처 색상 투영 | 없음 | 최소 camera-Z 앞면 | 초기 점군의 출처·가림 시각 진단 |
| E0b | E0 원본, 0→1→2 순차 치환 | 다음 카메라 픽셀 Z 산술 평균 | 비학습 깊이 평균 | 같은 픽셀 연관, 추가 gate 없음 | 단순 점군 융합 기준선·중간/최종 출처 추적 |
| E1 | 단순 연결(F0) | 평가만 | 없음 | 없음 | 중복 표면 문제 측정 |
| E2 | 공유 융합(F1) | 평가만 | 없음 | 융합만 | 데이터 연관 효과 |
| E3 | 공유 융합 | Photo | Ray-depth | 최소 가시성 | 최적화 기본선 |
| E3b | E0b 순차 융합 점군 초기값 | Photo | Ray-depth | 기존 E3 초기 가시성·고정 RGB/카메라 | E0b 위의 실제 RGB 역전파 정점 이동 |
| E4 | 공유 융합 | Photo | XYZ | 최소 가시성 | XYZ vs Depth |
| E5 | 공유 융합 | Photo+Anchor | XYZ | 관측 수 | 기하 보존 효과 |
| E6 | 공유 융합 | Photo+Anchor+Surface | XYZ | 시차 가중치 | 표면 정규화 효과 |
| E7 | 공유 융합 | Cross-view Photo+Prior | XYZ | 관측 출처 마스크 | 자기 재현 억제 효과 |
| E8 | 공유 융합 | Photo+Prior | Normal 방향 | 관측 수·시차 | 제3의 위치 매개변수 |
| E9 | 공유 융합 | E7 설정 | 최적 점만 | 선택 기준 비교 | Selective Refinement |

E3~E9는 전체 시스템 완성이 확인된 이후 실행한다. 먼저 E0/E1/E2를 만들어 정당한 초기 비교기준을 확보한다.

**E0 완료 기록(2026-11-12):** `tum-freiburg1_desk-E0-20261112-001`에서 P0/P1 결과를 재사용해 보정 전 원본 기준선을 확정했다. 프레임별 196,608점, 총 589,824점과 원본 예측·카메라·관측 출처를 보존하고 진단 시각화·해시·재로딩 검증을 완료했다. 융합·최적화·카메라 RGB 재렌더링·GT 정확도 평가는 수행하지 않았다. [E0 보고서](experiments/pointmap_refinement/E0/tum-freiburg1_desk-E0-20261112-001/report.md). 다음 단계는 P2 Renderer·Gradient 검증이다.

**E1 완료 기록(2026-11-12):** `tum-freiburg1_desk-E1-20261112-001`에서 전체 F0 589,824점을 유지해 6개 방향 깊이 잔차, projected layer spread, voxel co-occupancy와 all/own/cross RGB를 평가했다. 경계 제외 타 시점 잔차 중앙값은 1.01~1.39%, 3% 초과 비율은 14.1~26.5%였다. 가림·다른 표면·픽셀 이산화가 포함된 예측 간 진단이며 GT 오류나 실제 표면 두께로 단정하지 않는다. 원본 F0와 초기 평가 마스크를 E2 비교용으로 고정했다. [E1 보고서](experiments/pointmap_refinement/E1/tum-freiburg1_desk-E1-20261112-001/report.md).

**E2 완료 기록(2026-11-12):** `tum-freiburg1_desk-E2-20261112-001`에서 원본 관측 589,824개를 CSR로 모두 보존하면서 F1 대표점 510,427개를 생성했다. 공간·왕복 투영·깊이·법선 gate, 고유 프레임·모든 쌍 제약과 가시성 검증을 통과했다. 고정 E1 마스크의 RGB PSNR은 약 0.10~0.24dB 낮아졌고, 기하 진단은 coverage 변화·동일 대표점의 구조적 일치를 포함하므로 실제 정확도 향상은 미확인이다. 원본 F0와 불리한 결과를 보존했다. [E2 보고서](experiments/pointmap_refinement/E2/tum-freiburg1_desk-E2-20261112-001/report.md).

**E3 실행·평가 기록(2026-11-12):** `tum-freiburg1_desk-E3-20261112-001`에서 고정 E2 초기점의 67,906개 Ray-depth 변수를 200회 Photo-only로 최적화했다. 학습 손실은 0.06458→0.17513으로 악화했고, 평가한 체크포인트 중 selected는 초기 0회였다. 실제 이동된 last도 별도 보존했으며 초기 고정 스케일·공통 픽셀의 GT Depth RMSE는 0.16412→0.16457m였다. 현재 구현·설정에서 최적화 효과는 실패다. Hard visibility/stencil 변화와 실제 장면 Gradient의 불일치 진단을 기록했으며, 이를 RGB 기반 보정 방법 전체의 불가능성으로 일반화하지 않는다. [E3 보고서](experiments/pointmap_refinement/E3/tum-freiburg1_desk-E3-20261112-001/report.md).

동일 실험의 세부 비교 조건은 `E3a`, `E3b`처럼 소문자 접미사를 사용하고, 실행 전에 해당 코드의 목적·변경 변수·비교 기준을 등록한다. 동일 조건의 장면·Seed·재실행은 새로운 Run ID로 구분한다. 등록된 코드의 의미를 바꾸어 과거 결과와 섞지 않는다.

**E0a 진단 기록(2026-11-12):** `tum-freiburg1_desk-E0a-20261112-001`에서 E0의 589,824점과 예측 카메라를 유지한 채 출처별 빨강/초록/파랑 PLY와 native 512×384 z-buffer 투영을 생성했다. 전체·자기 출처 제외·출처별 단독 영상, 3% near-front 출처 혼합색과 깊이/출처 버퍼를 보존했다. 전체 앞면 중 자기 출처 비율은 약 60~64%였으며, 이는 출처·가림 진단으로 GT 정확도·실제 벽 두께를 뜻하지 않는다. XYZ·출처·부모 해시 불변 및 PLY/PNG/NPZ 재로딩 검증을 통과했다. E2/E3 출력이나 GT를 사용하지 않았다. [E0a 보고서](experiments/pointmap_refinement/E0a/tum-freiburg1_desk-E0a-20261112-001/report.md).

**E0b 융합 기준선 기록(2026-11-12):** `tum-freiburg1_desk-E0b-20261112-001`에서 E0를 0→1→2 순서로 처리했다. 다음 카메라의 같은 픽셀에 투영되는 현재 지도 점의 Z와 새 관측 Z를 산술 평균해 새 픽셀 시선의 점 하나로 치환하고 이전 대응점을 삭제했다. 깊이/법선/가림 gate는 없으며 비중첩 이전 점을 보존했다. 589,824개 원본 관측의 출처를 CSR로 추적하면서 최종 341,325점(42.13% 감소)을 생성했다. Camera 0/1/2의 한 픽셀 투영 coverage는 91.25/93.04/100%다. 단일 층·최신 owner 색과 점 수 감소는 정의상 결과이며 정확도 증거가 아니다. 알려진 평균값·시선·치환·비중첩 보존·출처 분할·저장 검증을 통과했고 GT 정확도는 평가하지 않았다. [E0b 보고서](experiments/pointmap_refinement/E0b/tum-freiburg1_desk-E0b-20261112-001/report.md).

**E3b 재지정(2026-11-12, 사용자 명시 요청):** 비교만 수행했던 E3b 코드·보고서·로컬 `tum-freiburg1_desk-E3b-20261112-001`을 삭제했다. 이전 내용은 Git 커밋 `6de932f167f577ddcb7b7b500412da53eb69444e`에만 남긴다. 현재 E3b는 E0b 점군 초기값에서 원본 RGB 손실을 역전파하는 미분 위치 최적화이며, 새 Run ID `tum-freiburg1_desk-E3b-20261112-002`로 실행한다. 이번 명시 요청에 한해 코드 의미를 변경하며 E0b/E3 등 기존 결과는 유지한다. [E3b 실행 이력](experiments/pointmap_refinement/E3b/README.md).

**E3b 실행 기록(2026-11-12):** `tum-freiburg1_desk-E3b-20261112-002`에서 E0b의 341,325점을 정확히 초기화하고 135,193개 후보에 Photo-only Ray-depth 역전파를 200회 적용했다. 실제 126,222점이 이동했지만 RGB 손실은 0.059157→0.209852로 악화했고 selected는 초기 step 0이었다. 초기 기준 단일 GT scale=1.3171403295592672, 공통 402,577픽셀에서 RMSE는 0.146852→0.147653m, AbsRel은 3.374634→3.653819%였다. 초기/selected/실제 이동 last를 보존했고 현재 설정의 효과는 실패로 기록한다. [보고서](experiments/pointmap_refinement/E3b/tum-freiburg1_desk-E3b-20261112-002/report.md).

**P2b 검은 테두리 진단(2026-11-12):** `tum-freiburg1_desk-P2b-20261112-001`에서 E3b의 E0b 초기 RGB/alpha 버퍼만 재사용했다. 좌표·가림 변경 없이 alpha 곱을 제거한 진단에서 밝은 목표 영역의 어두운 픽셀 프로브가 3,366→432개로 감소했다. 현재 검은 배경 합성이 테두리에 크게 기여하지만, 해당 초기 픽셀 중 학습 마스크 안은 207개여서 최적화 실패 전체의 원인으로 단정하지 않는다. Default P2·E3b·GT·Gradient는 변경/재학습하지 않았다. [보고서](experiments/pointmap_refinement/P2b/tum-freiburg1_desk-P2b-20261112-001/report.md).

**P2c 실행 기록(2026-11-12):** `tum-freiburg1_desk-P2c-20261112-001`에서 기존/alpha 제거/compact+hard/compact+soft를 분리 비교했다. compact_soft는 합성 가림·stencil 경계·평면 회복 및 실제 전체 E0b의 float64 방향 미분(상대 오차 3.26e-9~3.60e-7)을 통과했다. 같은 active 135,193개·초기 마스크의 10회 Adam에서 손실 0.042625→0.042087, 지원도 감소 0%p였고 133,555점이 실제 이동했다. 사전 기준에 따라 ready_for_E3b=true이며 실제 GT/200회 학습은 미실행이다. 이전 P2 default와 E3b는 보존한다. [보고서](experiments/pointmap_refinement/P2c/tum-freiburg1_desk-P2c-20261112-001/report.md).

### 13.1 제어 변수

같은 장면에서 비교 실험 간 다음은 고정한다.

- VGGT-Ω 체크포인트, 입력 이미지 세트, 전처리 변환.
- 카메라 Pose·Intrinsics.
- 초기 융합 결과, 점 RGB, 렌더 반경(명시적으로 변경하는 Ablation 제외).
- 해상도, 학습/평가 마스크, 난수 seed, 최대 iteration.
- 동일 GT 정렬 방식 및 평가 영역.

### 13.2 점 선택 실험

정량화 가능한 점별 스코어 후보:

\[
s_k = f(\text{cross-view residual},\text{confidence},
          \text{observation count},\text{parallax})
\]

비교 대상:
- 모든 유효 점.
- VGGT Confidence가 낮은 점.
- 여러 뷰에 관측되지만 Cross-view 오차가 큰 점.
- 관측 수 2 이상 + 충분한 시차각 + 큰 오차의 점.
- 같은 개수의 무작위 점.

**상대적 실험:** 활성 점 수를 반드시 동일하게 맞춰서 성능 차이가 선택 기준 때문인지 단순 연산량 때문인지 구별한다.

---

## 14. 단계별 실행 계획 및 완료 기준

Phase는 구현 순서이며 실험코드와 다르다. Phase 0은 P0, Phase 1은 P1 및 E0, Phase 2는 P2, Phase 3은 E1/E2, Phase 4는 E3~E7, Phase 5는 E8/E9 및 반복 평가에 대응한다. 모든 단계에서 실제 사용한 실험코드·Run ID·산출물 경로를 기록하며, 각 실험의 완료에는 17절의 결과 검증과 보고서 작성도 포함한다.

### Phase 0. 환경/실측 (가장 먼저)

- [x] CUDA, 드라이버, PyTorch, GPU 모델, OS, Python 버전 기록.
- [x] 공식 1B-512 Checkpoint 접근·로드 가능 확인.
- [x] 2장 / 3장 / 4장 VGGT-Ω 추론, peak VRAM 및 시간 측정.
- [x] max_size와 balanced를 같은 장면에서 비교.
- [x] 중간 파일 저장 후 종료된 프로세스에서 GPU 메모리 회수 확인.

**완료 기준:** 3장 입력의 고정된 카메라·Depth·Confidence·RGB 파일을 재현 가능하게 생성. 3장 실패 시 2장/해상도 축소로 최소 PoC를 지속한다.

**2026-11-12 실행 기록:** `smoke-P0-20261112-001`에서 호스트 CUDA 계산과 RGB 전처리 6개 조합을 검증했다. 공식 체크포인트가 HTTP 401 / GatedRepo이고 실험 프로세스에서 인증정보를 확인하지 못해 실제 모델 추론은 미실행이다. **P0 미완료**이며 상세 근거는 [P0 결과 보고서](experiments/pointmap_refinement/P0/smoke-P0-20261112-001/report.md)를 따른다.

**인증 후 재시도:** `smoke-P0-20261112-002`에서 호스트 로그인을 확인하고 CUDA·전처리를 재검증했다. 공식 파일 서버는 HTTP 403 / GatedRepo와 함께 모델 접근 신청 검토 대기 상태를 반환했다. 로그인 문제는 해결됐으나 가중치 다운로드·추론은 여전히 미실행이다. **P0 미완료**이며 [재시도 보고서](experiments/pointmap_refinement/P0/smoke-P0-20261112-002/report.md)에 기록한다.

**승인 후 완료:** `smoke-P0-20261112-003`에서 공식 가중치 해시 검증, 7회 추론, 출력 저장·재로딩, 3장 반복 일치와 GPU 메모리 회수를 확인했다. **P0 완료.** [완료 보고서](experiments/pointmap_refinement/P0/smoke-P0-20261112-003/report.md).

### Phase 1. 기하 및 데이터 계약

- [x] OpenCV world-to-camera round-trip 구현.
- [x] 자기 카메라 재투영 오차 분포 확인(올바른 변환 시 수치 오차 수준).
- [x] 타 카메라 투영/Depth/유효영역/패딩 검사.
- [x] GT Depth와 전처리 RGB 정렬 테스트.
- [x] 관측 출처가 보존된 Point Cloud 저장.

**완료 기준:** 합성 카메라/평면에서 3D→2D→3D 변환과 좌표계 방향 오류가 없음.

**2026-11-12 완료:** `tum-freiburg1_desk-P1-20261112-001`에서 공식 역투영 일치, 합성 기하와 오류 대조군, 자기 시점 최대 재투영 오차 0.000045px, GT 시간·격자 연계 및 출처 보존 589,824점 저장을 검증했다. GT의 물리적 등록 정확도나 모델 기하 정확도 개선을 의미하지 않는다. [P1 보고서](experiments/pointmap_refinement/P1/tum-freiburg1_desk-P1-20261112-001/report.md).

### Phase 2. Renderer 최소 기능

- [x] PyTorch3D 설치/동작 또는 최소 Soft Point Splat 대안 구현.
- [x] 고정 Point Cloud의 RGB + Depth + Coverage 출력.
- [x] 합성 점·평면의 XY, Z Gradient 유한차분 검증.
- [x] 계산 불가 지점·가림 경계의 Gradient와 마스크 기록.

**완료 기준:** 두 카메라 합성 장면에서 3D 이동 방향을 일관되게 회복. 값만 내려가고 3D 오차가 남는 경우 원인 분석.

**P2 완료 기록(2026-11-12):** 001의 hard visibility 평면 최적화는 실패하여 보존했다. 002에서는 가림 선택을 분리한 합성 평면의 평균 3D 오차 0.204354→0.000003034, 단일 점·평면의 유한차분 검사를 통과했다. E0에서 선택한 36,864점의 3시점 RGB·Depth·Coverage 및 유한한 위치 Gradient를 확인했다. 실제 좌표 최적화와 GT 정확도 평가는 미실행이며 hard visibility 경계는 불연속이다. [P2 보고서](experiments/pointmap_refinement/P2/tum-freiburg1_desk-P2-20261112-002/report.md).

**P2a 추가 비교(2026-11-12):** 별도 환경에서 공식 PyTorch3D 0.7.9를 C++20 빌드 설정 패치로 CUDA 설치하고 동일 입력의 p2/standard/matched를 비교했다. 단일 점·경계 밖 평면 Gradient는 통과했으나 standard의 합성 기하 회복과 경계 Gradient에는 실패가 있었다. matched의 초기 RGB PSNR 상승은 실제 기하 정확도 향상을 뜻하지 않는다. 설치·비교는 완료했으며 기존 P2 기본선을 교체하지 않는다. [P2a 보고서](experiments/pointmap_refinement/P2a/tum-freiburg1_desk-P2a-20261112-001/report.md).

### Phase 3. 공유점 융합·가시성

- [x] F0 단순 연결 Baseline.
- [x] F1 공간·Depth·재투영·Normal 기반 공유점 융합.
- [x] 관측 목록, owner, observation-count, parallax 저장.
- [x] Z-buffer/Depth Agreement 기반 visibility.
- [x] Mask 변화·중복 레이어·융합 위험 진단 시각화(GT로 오탐 여부 확정은 미실행).

**완료 기준:** 공유점이 단지 여러 프레임의 concatenation이 아니라 실제 관측 그룹을 갖고 있음을 디버그 뷰로 확인.

### Phase 4. 실제 장면 최적화

- [ ] 카메라 Pose 및 RGB 고정.
- [x] Ray-depth E3 구현 및 실행·평가(현재 설정의 최적화 효과는 실패).
- [ ] XYZ E4 구현.
- [ ] Anchor/Surface 추가 E5/E6.
- [ ] Cross-view 자기 관측 편향 제거 E7.
- [ ] Optimizer 로그/Checkpoint/NaN 복구 구현.

**완료 기준:** 입력 RGB 손실 감소 외에 **GT Geometry 또는 시점 간 기하 정합성 지표**를 전후 비교할 수 있음.

### Phase 5. 일반화·비교·보고

- [ ] 정적 장면 3종 이상, Seed 3개 이상으로 가능한 범위에서 반복.
- [ ] 2 vs 3 vs 4장, 관측 카메라 수, 시차각별 그룹 실험.
- [ ] GT Depth와 Held-out RGB 정량화.
- [ ] Runtime·Peak VRAM·활성 점수 대비 성능 그래프.
- [ ] 실패 사례(무텍스처, 반사, 가려짐, 오융합) 분류.
- [ ] 변경된 주요 하이퍼파라미터 및 불리한 결과도 공개.

**완료 기준:** 연구 질문 RQ1~RQ5에 대해 근거 있는 답과 미해결 제한을 작성.

---

## 15. 기능별 테스트 명세

| Test | 설정 | 예상 확인 항목 |
| --- | --- | --- |
| T01 | Identity K,R,t + 알려진 평면 | 투영 좌표 오류 없음 |
| T02 | 카메라 이동 + 알려진 3D 점 | 두 카메라 reprojection 일치 |
| T03 | 이미지 crop/resize/pad | Intrinsic/Mask 변경 정확 |
| T04 | 점 1개, 1카메라, 깊이 변화 | 자기 뷰만으로 깊이 불확정 |
| T05 | 점 1개, 2카메라, 깊이 변화 | gradient 방향 일관성 |
| T06 | 두 벽이 공간상 가까움 | 잘못된 Fusion 방지 |
| T07 | 앞점/뒤점이 같은 픽셀 | Occlusion 판정 |
| T08 | 관측 1회 vs 관측 3회 | 선택 정책 차이 |
| T09 | 정답 위치에서 초기점에 perturbation | 3D 회복 가능성 |
| T10 | 순백색 평면 | Photo-only 깊이 모호성 |
| T11 | RGB에 노출 차이 추가 | Photo-only 취약성 |
| T12 | 3장 20k/50k/100k points | VRAM·시간 측정 |
| T13 | seed 반복 | 재현성·분산 |
| T14 | Loss mask를 변경 | Coverage/PSNR 착시 확인 |

기능 테스트와 연구 가설 검증은 별도이다. T04/T10처럼 '복원이 안 되는 것이 예상되는' 시험도 통과 기준을 갖는다.

---

## 16. 주요 실패 모드 및 대응

| 실패 모드 | 징후 | 대응 |
| --- | --- | --- |
| 잘못된 카메라 좌표계 | 영상을 뒤집거나 투영이 크게 이탈 | T01~T03, 축 변환 Adapter |
| 포즈 편향 | 깊이를 비물리적으로 변형해 Loss 감소 | Pose 고정 한계 명시, Pose error 별도 분석 |
| 중복 표면 자기 재현 | Train PSNR↑, Geometry 불변/악화 | F1 융합 + O_k 출처 + E7 |
| Hard visibility 불연속 | gradient 0, 튐, NaN | Soft Splat + 주기적 detached mask |
| 흰 벽·무텍스처 | Depth gradient 거의 없음 | Anchor + Multi-view geometry; 불확실 표시 |
| 가림 경계·반사 | 원본 색상 불일치 | Robust Loss/유효 가시성 마스크 |
| 잘못된 Fusion | 서로 다른 표면 하나로 합침 | 거리+재투영+Normal, 보수적 threshold |
| 모든 점 XYZ 자유 이동 | 표면 찢어짐/떠다님 | Ray/Normal 비교, Anchor/Surface |
| Mask 분모 변경 | 수치 개선만 나타남 | 고정 평가 마스크 + coverage |
| 8GB OOM | Rasterizer 활성화 시 메모리 급증 | 2단계 프로세스, 작은 해상도, top-K 감소 |
| GT 스케일 불일치 | 모든 GT Depth 오차가 큼 | GT alignment protocol 명시 |
| 미분 검증 실패 | 유한차분과 부호/크기 불일치 | Renderer 구현/가림/합성 로직 재검토 |

---

## 17. 로그·산출물·보고 양식

### 17.1 저장 대상

모든 실행은 다음 세 경로를 같은 실험코드와 Run ID로 연결한다.

| 구분 | 경로 | 저장 내용 |
| --- | --- | --- |
| 재현 코드·설정 | `experiments/pointmap_refinement/<experiment_code>/` | 목적, 실행 절차, 설정, 스크립트 |
| 중간·최종 산출물 | `results/pointmap_refinement/<run_id>/stages/<experiment_code>/` | Manifest, 설정 사본, 로그, 추론·최적화·평가 파일 |
| 중간·최종 보고서 | `docs/experiments/pointmap_refinement/<experiment_code>/<run_id>/` | 진행 기록, 결과 보고서, 보고용 그림 |

예를 들어 E3의 첫 실행은 Run ID를 `sceneA-E3-20261112-001`로 두고, 결과는 `results/pointmap_refinement/sceneA-E3-20261112-001/stages/E3/`, 보고서는 `docs/experiments/pointmap_refinement/E3/sceneA-E3-20261112-001/`에 저장한다. 날짜는 실행 시작일의 한국 시간(Asia/Seoul)을 사용한다. 아래 구조는 실험 특성에 따라 필요한 파일을 생성하며, 평가 전용 E0~E2에는 최적화 로그가 필수가 아니다.

~~~text
results/pointmap_refinement/<run_id>/stages/<experiment_code>/
├── manifest.json               # 상태, 입력/출력 경로, 출처, SHA-256
├── config_resolved.yaml
├── environment.json
├── logs/                       # 실행 명령, stdout/stderr, 종료 코드
│   └── training_log.csv
├── artifacts/
│   ├── data/                   # 입력 목록, 분할, 전처리 메타데이터
│   ├── inference/
│   │   └── vggt_omega_raw.npz   # 모델 출력과 전처리된 RGB
│   ├── geometry/
│   │   ├── observations.npz
│   │   ├── shared_map_initial.npz
│   │   ├── shared_map_final.npz
│   │   ├── camera_visibility.npz
│   │   ├── shared_initial.ply
│   │   └── shared_refined.ply
│   ├── optimization/           # 중간 Checkpoint, 변위·Gradient 기록
│   ├── renders/
│   │   ├── before/
│   │   ├── after/
│   │   └── heldout/
│   └── debug/                  # Fusion/Visibility/Depth 잔차 시각화
└── evaluation/
    ├── metrics.json
    └── comparison_geometry/
~~~

Stage A~G는 처리 단계 이름이며 실험코드가 아니다. 동일 실험의 중간 처리는 위의 `artifacts/` 아래에서 구분하고, 각 단계의 입력·출력·완료 상태를 Manifest에 기록한다.

### 17.2 실험별 메타데이터

- Experiment code, Run ID, Scene ID, 목적, 비교 대상 실험코드와 Run ID.
- 모델명/Checkpoint SHA256, 코드 Git Commit, 입력 이미지 파일 목록 및 해시.
- CUDA/PyTorch/PyTorch3D 버전, GPU 드라이버, fp16/bf16/fp32 설정.
- Image preprocess 방식, 실제 H×W, Pixel coordinate 규약.
- 융합 threshold, 카메라 Pair/Visibility threshold, Optimizer 설정.
- 학습/평가 View ID, Fixed/Trainable 변수, Seed.
- 사용한 GT의 정렬 자유도, 단위, 무효 깊이 처리.
- 마지막/최적 Validation Checkpoint와 중단 이유.
- 시작·종료 시각과 시간대, 실행 명령, 종료 코드, 실행 상태(`planned`/`running`/`completed`/`failed`/`stopped`).
- 원본 입력·중간·최종 산출물의 경로와 SHA-256, 중간·최종 보고서 경로.
- 재사용한 상위 실험 산출물의 코드·Run ID·Manifest 경로·해시 및 재사용 이유.

### 17.3 실행 격리 및 중간 결과 보존

1. Run ID 형식은 `<scene_id>-<experiment_code>-<YYYYMMDD>-<NNN>`으로 통일한다. 재실행·Seed 변경·실패 후 재시도는 새 번호를 사용하며, 대상 폴더가 이미 있으면 실행을 중단한다.
2. 실행 전에 설정을 확정하고 사본을 저장한다. 진행 중 조건을 바꿔야 하면 현재 실행의 중단 이유를 남기고 새 Run ID에서 실행한다.
3. 실패·OOM·수동 중단도 로그, 생성된 중간 파일, 마지막 Checkpoint와 함께 보존한다. 완료된 실행의 결과는 덮어쓰지 않는다.
4. E0 추론이나 E2 융합 결과를 후속 실험에서 재사용할 때는 원본을 읽기 전용 입력으로 취급한다. 경로만 암묵적으로 공유하지 않고 17.2절의 출처와 해시를 기록한다.
5. Point Cloud는 점 수, 유한 XYZ 여부와 해시를 검증하고, NPZ/Checkpoint는 로드 가능 여부와 필수 필드를 검사한다. 생성된 파일이 있다는 사실만으로 실행 완료나 기하 개선을 판정하지 않는다.

### 17.4 중간·최종 보고서

- **`progress.md`:** 실행 목적과 조건, 단계별 수행 여부, 중간 지표·그림의 상대경로, 오류·OOM·중단 이유, 다음 확인 항목을 기록한다. 구현 완료·실행 완료·평가 완료를 구분한다.
- **`report.md`:** 실험코드·Run ID, 연구 질문/가설, 데이터와 학습·평가 분할, 재현 명령·설정·환경, 비교 기준, 전후 정량 지표와 시각화, 실행 시간·VRAM, 산출물 검증, 성공/부분 성공/실패 판단 및 한계를 포함한다. 실패한 실행도 보고서를 남긴다.
- **실험별 `README.md`:** 각 Run ID와 보고서 링크, 조건 차이, 실행 상태 및 결과 판단을 표로 정리한다.
- **전체 `index.md`:** P0~P2, E0~E9 및 세부 코드별 목적, 최신 실행·보고서 링크와 진행 상태를 관리한다. 새 실행이 기존 실행의 이력을 대체하지 않도록 한다.

보고서의 그림·표는 산출물 경로와 연결하고, 논문에 인용할 결과는 Run ID·코드 Commit·설정·입력 해시로 역추적 가능해야 한다. GT가 없으면 기하 정확도 개선 여부는 **미검증**으로 적으며, 정성 비교와 관측 일관성 결과로 주장을 제한한다. 실행 상태 `completed`와 연구 결과의 성공 판정은 별개다.

### 17.5 결과표 권장 형태

**실험 완료 후 GitHub 반영:** 매 실험이 완료되면 해당 실행의 코드·설정·중간/최종 보고서와 실험 현황을 검토하고, 실험코드·Run ID가 식별되는 커밋을 만든 뒤 GitHub에 푸시한다. 데이터·가중치·가상환경·대용량 산출물의 기존 제외 정책은 유지한다. 로컬 커밋 성공과 원격 반영 성공을 구분하며, 푸시 후 원격 브랜치의 Commit SHA가 로컬 HEAD와 일치하는지 확인해 보고한다. 푸시가 실패하면 완료된 실험 결과는 보존하고 게시 실패 사유를 별도로 기록한다.

| Scene | Views | Method | #Points | Train PSNR | Heldout PSNR | GT Depth RMSE | Chamfer | Coverage | VRAM | Time |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scene_A | 3 | E0 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| scene_A | 3 | E2 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| scene_A | 3 | E3 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| scene_A | 3 | E7 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

TBD는 측정 이전임을 뜻한다. 수치를 미리 기입하지 않는다.

실제 결과표에는 각 행의 Run ID·Seed·보고서 링크를 추가한다. 전체 비교표를 만들더라도 근거가 되는 실험코드별 보고서와 중간 결과는 해당 폴더에 유지한다.

---

## 18. 구현에서 반드시 지킬 원칙

1. **공유 3D 좌표는 한 번만 저장·학습한다.** 카메라별 Pointmap은 생성/평가에서만 등장하고 서로 독립 최적화하지 않는다.
2. 카메라 i의 원본 RGB는 자기 점의 RGB를 가져온 것일 수 있으므로, 자기 시점 재현은 **Geometry Accuracy 증거가 아니다.**
3. 단일 Point Cloud의 점이 여러 개의 카메라에 보인다는 판정은 **해당 이미지에서 동일한 물리적 점이 관측되었다는 확정 사실이 아니다.**
4. Point position의 자동 미분은 **Local Loss 경사**일 뿐 전역 최적해를 보증하지 않는다.
5. Geometry 향상 평가는 RGB보다 GT 3D/Depth 지표를 우선한다.
6. Pose를 고정한 결과는 기존 BA 전체 기능을 대체했다는 주장으로 확대하지 않는다.
7. 성능·메모리·타당성 주장은 각 실험의 측정값과 환경 정보에 한정한다.
8. 원본 모델의 직접 Output과 우리가 만든 Fusion/Optimization Output을 파일명부터 명확히 구분한다.

## 19. 우선 실행 체크리스트(Minimum Viable Experiment)

**MVE-1 — 합성 환경**
- [ ] 정답이 있는 3D 컬러 평면 구성
- [ ] 카메라 2대, 처음에는 점 100~1000개
- [ ] 일부 점을 수치적으로 오프셋
- [ ] 미분 렌더러로 원본 RGB 재현 + Gradient 확인
- [ ] 위치 오차가 실제로 감소하는지 검증

**MVE-2 — VGGT-Ω 실제 입력 3장**
- [ ] 8GB에서 모델 추론 성공 및 결과 저장
- [ ] Depth, Extrinsic, Intrinsic으로 공통 월드 점 생성
- [ ] 동일 표면 관측을 일부 공유점으로 융합
- [ ] 공유점 20k 기준 3시점 재렌더링
- [ ] Ray-depth와 XYZ의 Loss 및 3D 정확도 비교
- [ ] 가능하면 미사용 카메라/GT Depth로 확인

**MVE-3 — 정합성·과적합 검사**
- [ ] 관측 출처 기반 cross-view 조건 도입
- [ ] Anchor/Surface Prior 적용
- [ ] GT Geometry vs Train PSNR의 변화 방향 비교
- [ ] OOM 없이 동일 설정을 재실행해 결과 재현

**MVE-4 — 확장 판단**
- [ ] MVE-1~3이 정상 동작해야 4장·100k 이상으로 확장
- [ ] 실패 시 단순히 Loss 가중치를 바꾸기보다, 카메라·Renderer Gradient·Fusion·Visibility 순으로 진단

---

## 20. 참고 문헌 및 공식 코드

1. Wang et al., *VGGT-Ω*, 2026. https://arxiv.org/abs/2605.15195  
   공식 GitHub: https://github.com/facebookresearch/vggt-omega  
   카메라 Encoding: https://github.com/facebookresearch/vggt-omega/blob/main/vggt_omega/utils/pose_enc.py  
   이미지 전처리: https://github.com/facebookresearch/vggt-omega/blob/main/vggt_omega/utils/load_fn.py  
   World Point 변환: https://github.com/facebookresearch/vggt-omega/blob/main/demo_gradio.py
2. Rückert, Franke, Stamminger, *ADOP: Approximate Differentiable One-Pixel Point Rendering*, ACM TOG, 2022. https://arxiv.org/abs/2110.06635  
   코드: https://github.com/darglein/ADOP
3. PyTorch3D, PointsRenderer API. https://pytorch3d.readthedocs.io/en/latest/modules/renderer/points/renderer.html
4. Engel, Koltun, Cremers, *Direct Sparse Odometry*, IEEE TPAMI, 2018. https://arxiv.org/abs/1607.02565
5. Delaunoy & Pollefeys, *Photometric Bundle Adjustment for Dense Multi-View 3D Modeling*, CVPR, 2014. https://openaccess.thecvf.com/content_cvpr_2014/html/Delaunoy_Photometric_Bundle_Adjustment_2014_CVPR_paper.html

> **최종 요약:** 본 계획의 핵심은 VGGT-Ω에서 얻은 프레임별 관측을 **단일 공유 3D Point Cloud**로 융합하고, 동일한 3D 점의 위치에 대해 여러 카메라의 원본 RGB 오차를 동시에 역전파하는 것이다. 실험의 성패는 Train RGB Loss의 감소가 아니라 **실제 기하 정확도 및 미사용 시점의 재현성 개선 여부**로 판단한다.
