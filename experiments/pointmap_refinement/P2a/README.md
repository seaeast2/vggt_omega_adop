# P2a — PyTorch3D 설치 및 P2 비교

기존 P0/P2 환경은 유지하고 `.venvs/p2a`를 별도로 사용한다. 공식 PyTorch3D Commit은 `config.json`에 고정했다. PyTorch 2.15가 C++20을 요구하므로 `setup.py`의 두 C++17 플래그만 C++20으로 바꾼 패치를 제공한다. 최초 오류 로그는 실행 폴더에 보존한다.

## 설치 재현

프로젝트 루트, 호스트에서 실행한다. `thirdparty/pytorch3d`가 없는 새 환경 기준이며 기존 소스를 덮어쓰지 않는다.

```bash
git clone https://github.com/facebookresearch/pytorch3d.git thirdparty/pytorch3d
git -C thirdparty/pytorch3d checkout fdd657494ea5151cd66e19a1594494f1e1d592a1
git -C thirdparty/pytorch3d apply ../../experiments/pointmap_refinement/P2a/pytorch3d-cxx20.patch
.venvs/p0/bin/uv venv --python .python/cpython-3.11.18-linux-x86_64-gnu/bin/python3.11 .venvs/p2a
.venvs/p0/bin/uv pip install --python .venvs/p2a/bin/python -r experiments/pointmap_refinement/P2a/requirements.lock.txt
MAX_JOBS=2 TORCH_CUDA_ARCH_LIST=12.0 FORCE_CUDA=1 \
  .venvs/p0/bin/uv pip install --python .venvs/p2a/bin/python \
  --no-build-isolation --no-deps ./thirdparty/pytorch3d
```

실행 당시 전체 버전은 `requirements.lock.txt`에 고정한다. 위 추가 의존성 설치의 새 해석 결과보다 실측 시점의 lock을 우선한다.

## 比較条件

새 Run ID의 `results/pointmap_refinement/<run_id>/stages/P2a/`에 `logs/`, `evaluation/`, `artifacts/{source,renders,synthetic}/`를 만들고 초기 Manifest를 기록한 뒤 실행한다.

```bash
.venvs/p2a/bin/python experiments/pointmap_refinement/P2a/run.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-P2a-20261112-001/stages/P2a
.venvs/p2a/bin/python experiments/pointmap_refinement/P2a/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-P2a-20261112-001/stages/P2a
.venvs/p2a/bin/python experiments/pointmap_refinement/P2a/plot_history.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-P2a-20261112-001/stages/P2a
```

비교 대상은 `p2`(기존 구현), `standard`(PyTorch3D의 원형 거리 가중치와 alpha_composite), `matched`(PyTorch3D rasterization에 P2와 가까운 Gaussian·합성·3% gate)다. standard는 PointsRenderer의 가중치·AlphaCompositor 규칙을 사용하며, 카메라 좌표는 검증 가능한 직접 OpenCV→NDC adapter로 전달한다. 공식 PointsRenderer 클래스를 그대로 호출하는 것은 아니다.

동일 점·RGB·카메라·해상도·검은 배경을 사용한다. 표준 방식의 반경은 2px, 후보 수는 16이며, P2의 정사각 stencil과 원형 footprint 및 top-K는 완전히 같지 않다. matched 결과도 순수한 라이브러리 교체 효과로 해석하지 않는다. 렌더 시간은 warmup 2회 뒤 5회 중앙값으로 보고하며, 메모리는 forward+backward 범위다.

합성 입력은 P2에 저장된 같은 GT/초기 좌표·색상이다. 각 렌더러의 GT 이미지는 해당 렌더러로 생성하여 렌더러 자체의 회복을 검사한다. P2/matched의 평면 gate는 사실상 해제하고 standard는 본래의 깊이순 합성을 유지한다. 합성 회복 실패도 비교 결과로 기록하며 실제 기하를 갱신하지 않는다. [실험 보고서 목록](../../../docs/experiments/pointmap_refinement/P2a/README.md)을 따른다.
