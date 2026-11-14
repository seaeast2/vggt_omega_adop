# Global planar pointmap I series

2026-11-14부터 TUM은 신규 실험·최적화·GT 평가에서 제외한다. 현재 대상은 ETH3D `office`·`pipes`이며 `Stage` 생성과 `load`에서 TUM 입력을 거부한다. 기존 TUM 데이터와 결과는 보존한다. [실행 정책](dataset_policy.json).

계획: [I0–I9](../../docs/vggt_omega_global_planar_pointmap_experiment_plan.md).

Python 환경은 `.venvs/p2a/bin/python`이다. 모든 geometry는 float64 Omega world/model units다.
기존 실험과 실패 run은 덮어쓰지 않으며 매 실행은 새 sequence를 할당한다.

```bash
# 아래는 과거 TUM 파이프라인의 명령 기록이다. 새 실험은 하단 ETH3D 명령을 사용한다.
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/prepare.py
# 다음 GPU 명령은 반드시 승인된 호스트 실행에서 수행한다.
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/segment.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/solve.py I2
# I3, I4, I5, I6 순서로 같은 CLI 사용
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/export.py I7
# I8, I9 순서로 같은 CLI 사용
```

과거 실험은 추가 실내에 `--dataset tum-freiburg1_desk-extra`를 사용했다. 해당 TUM 실행 경로는 현재 차단된다.
I2는 기존 C3a 역사적 재현과 누출 제거 split의 주 solve를 구분한다. split 변경·최적화의 구체적 식은 각 run의 source/config에 보존한다.
`manifest.status=completed`는 실행 종료이며 `completion_criteria_met` 및 scientific decision을 별도로 읽어야 한다.
소속·이상적 구조 GT는 없다. 최적화 단계는 `GT_NOT_EVALUATED`로 남기고, 별도 평가인 I11/I13의 TUM Kinect depth 및 I20의 ETH3D 레이저-rendered depth를 구분한다. GT 평가는 optimizer가 완료된 뒤 실행하며 공통 baseline 정렬·평가 mask를 고정한다.

ETH3D office/pipes 전이: [계획](../../docs/vggt_omega_eth3d_laser_experiment_plan.md) · [레이저 GT 결과](../../docs/experiments/global_planar_pointmap/I20/index.md).

`blur_report.py --historical`은 저장된 I22–I25/TUM 비교 결과를 재보고하는 전용 명령이다. 새 실험 명령으로 사용하지 않는다. 과거 I0의 동결된 하이퍼파라미터 메타데이터 참조는 유지하며 TUM 이미지·점군은 새 실행에 로드하지 않는다.

```bash
# 네트워크 다운로드와 두 GPU 명령은 샌드박스 밖 호스트에서 실행한다.
.venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser_download.py
.venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser.py prepare
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser.py infer
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser.py freeze
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser.py segment
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser.py pipeline
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser_evaluate.py
.venvs/p2a/bin/python experiments/global_planar_pointmap/eth3d_laser_report.py
```

`prepare/infer/freeze/segment/pipeline`의 `--scene office|pipes|all`로 범위를 지정한다. 기본은 두 장면이다. 모델 체크포인트와 `.venvs/p2a`는 기존 환경을 사용한다. 다운로드 helper는 공식 archive와 pinned camera/GT source를 캐시하고, 새 패키지를 설치하지 않는다. 기존 system libarchive와 g++가 필요하다. ETH3D 전처리는 512×336이며 Stage별 입력/source hash와 실패를 보존한다.

대형 NPZ/PLY/mask는 results에 남기고 manifest의 SHA256/크기/경로만 Git에 저장한다.

블러 원인 분리: [계획](../../docs/vggt_omega_blur_causal_experiment_plan.md) · [I25 결과](../../docs/experiments/global_planar_pointmap/I25/index.md).

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_inputs.py prepare
# 호스트 GPU, 샌드박스 밖
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_inputs.py infer
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_optimize.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_evaluate.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_alignment_diagnostic.py
# 그래프 전용 환경: 모델·GT 계산 환경과 분리. 설치에는 호스트 네트워크 필요.
.venvs/p2a/bin/python -m venv .venvs/blur-report
.venvs/blur-report/bin/python -m pip install -r docs/experiments/global_planar_pointmap/I25/report_requirements.txt
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/blur_report.py
```

I25a는 원래 TUM의 정렬 scale에 대한 **사후 보조 진단**이다. 출력 XYZ·회전·centroid를 고정하며 원래 I21 지표를 덮어쓰지 않는다. 이를 모델 보정이나 새 성능 점수로 해석하지 않는다.
`publish.py`는 계획에서 허가한 단계별 커밋·푸시에만 사용하며 기존 사용자 변경을 staging하지 않는다.
