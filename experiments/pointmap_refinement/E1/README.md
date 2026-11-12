# E1 — F0 단순 연결 상태 평가

E0의 원본 전체 관측 589,824점을 동일 좌표계 그대로 사용한다. 입력 NPZ·PLY는 해시가 같은 사본으로 보존한다. 모델 추론·융합·좌표 보정은 하지 않는다. 조건은 `config.json`에 실행 전에 고정했다.

호스트의 기존 `.venvs/p0-py311` 환경에서 새 Run ID로 실행한다. geometry/verify는 CPU, render는 샌드박스 밖 호스트 GPU에서 수행한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E1/geometry.py \
  --run-id tum-freiburg1_desk-E1-20261112-001
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E1/render.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E1-20261112-001/stages/E1
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E1/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E1-20261112-001/stages/E1
```

6개 방향에서 nearest-pixel source z-buffer와 target 초기 깊이를 비교한다. target의 4-neighbor 상대 깊이 변화가 3%를 넘는 양쪽 픽셀과 바깥 테두리를 제외한다. source edge를 따로 제외하지는 않는다. 상대 잔차 3% 초과를 예측 불일치로 집계하며 실제 오류 판정으로 사용하지 않는다.

각 target 픽셀에 투영된 프레임별 최근접 Z의 max−min을 layer spread로 측정한다. 같은 표면이라고 확정된 점들의 두께가 아니다. Target 깊이와 모두 5% 이내인 하위집합도 따로 기록하며 이 부분집합은 임계값으로 검열된 표본이다.

Voxel은 median depth의 0.25/0.5/1% 크기, 두 grid origin을 사용한다. 서로 다른 프레임의 co-occupancy는 잠재 중복이며 대응점 확정이 아니다. 원본을 voxel로 줄이거나 융합하지 않는다.

렌더러는 변경 없는 P2 Gaussian(5×5, σ=.65px, depth gate=.03)이다. 이번에는 부분 샘플 대신 전체 all/own/cross를 사용한다. 128×96, target INTER_AREA, centre-based K affine, alpha≥.5이며 F0 고정 마스크와 세 조건 공통 마스크를 분리한다. cross는 지도 작성에 사용된 타 프레임 관측이며 held-out 데이터가 아니다.

세 실행의 종료 코드 0, 저장 지표·마스크 재로딩, 부모 해시·원본 보존 검증 뒤 보고서와 Manifest를 확정하고 커밋·푸시한다. [결과 보고서 목록](../../../docs/experiments/pointmap_refinement/E1/README.md).
