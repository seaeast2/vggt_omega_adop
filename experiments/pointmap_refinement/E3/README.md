# E3 — 원본 RGB 기반 Ray-depth 위치 최적화

E2 초기 공유점 510,427개, 고정 RGB·카메라·반경·관측 그룹을 사용한다. E2의 67,906개 다중 관측·비영 시차·모든 출처 가시성 후보만 owner Ray 방향으로 움직이며 나머지 좌표는 고정한다. 실제 초기점이 변하지 않도록 `xyz0 + ray*d0*expm1(delta)`로 매개변수화한다. d0는 Euclidean Ray 거리이며 Z-depth와 다르다.

실행 전 조건은 `config.json`에 있다. Photo Charbonnier만 사용하며 Anchor·Surface·CrossDepth 손실은 없다. Adam lr=.001, 200회, delta∈[-.05,.05], 초기 고정 train mask, 같은 P2 hard-gate renderer를 사용한다. 매 Forward의 stencil/front 선택은 갱신되지만 그 선택의 변화는 미분하지 않는다. E2의 active set은 고정한다.

호스트 GPU에서 새 Run ID로 실행한다. `train.py`는 GT를 읽지 않는다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3/train.py \
  --run-id tum-freiburg1_desk-E3-20261112-001
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3/diagnose.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E3-20261112-001/stages/E3
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3/evaluate.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E3-20261112-001/stages/E3
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E3-20261112-001/stages/E3
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3/plot.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E3-20261112-001/stages/E3
```

0/20/…/200회 체크포인트를 보존한다. selected는 그 체크포인트 중 학습 Charbonnier가 가장 낮은 상태이며 검증/GT 최적 모델이 아니다. last와 selected를 별도로 저장한다. 기존 상태를 덮어쓰지 않는다.

GT는 선택을 끝낸 뒤 P1의 이미 정렬된 Depth를 평가용으로만 읽는다. Native nearest-pixel front depth에 대해 초기 E2에서만 전 카메라 공통 scale 하나를 맞추고 selected/last에 재적용한다. GT 유효·초기 coverage mask, 모든 출력의 공통 mask 및 누락 coverage를 보고한다. 같은 입력 시점의 scale-aligned Depth 지표이며 독립 시점·전체 3D 정확도가 아니다.

실행 성공과 최적화 효과를 구분한다. 이번 001에서는 손실/PSNR이 악화해 selected=0이었다. 개선된 점군을 얻었다고 처리하지 않으며 이동한 last 점군과 중간 실패 이력을 보존한다. [보고서](../../../docs/experiments/pointmap_refinement/E3/README.md)를 따른다.
