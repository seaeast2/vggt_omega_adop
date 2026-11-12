# E2 — 공유점 융합·가시성 검증

원본 E1 F0는 읽기 전용으로 보존한다. CPU에서 원본 관측을 서로 다른 프레임의 그룹으로 집계하며, E1 고정 마스크와 기존 P2 렌더러로 F0/F1을 비교한다. 융합으로 대표 좌표·색상·점 집합이 달라지지만 RGB 손실 기반 최적화는 수행하지 않는다.

호스트의 기존 `.venvs/p0-py311` 환경에서 새 Run ID로 실행한다. `evaluate.py`의 렌더링은 샌드박스 밖 GPU에서 실행한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E2/fuse.py \
  --run-id tum-freiburg1_desk-E2-20261112-001
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E2/evaluate.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E2-20261112-001/stages/E2
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E2/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E2-20261112-001/stages/E2
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E2/handoff.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-E2-20261112-001/stages/E2
```

## 고정 조건

`config.json`에 실행 전 조건을 기록한다. 후보는 알려진 카메라의 투영 대상 최근접 픽셀에서 찾는다. i<j인 각 프레임 쌍에서 후보를 얻고, 역방향 투영도 원래 픽셀의 1px 이내인지 확인한다. Voxel 전체 이웃을 탐색한 구현이나 모든 대응을 찾았다는 보장은 아니다.

공간 반경은 median depth의 1%, 깊이 허용차는 median depth의 0.2%+대상 깊이의 2%, 법선 방향은 30도 이내다. Depth 경계 3%와 신뢰 가능한 유한차분 법선도 검사한다. 거리가 작은 edge부터 집계하되 그룹의 모든 쌍이 후보 gate를 통과하고 프레임이 유일해야 한다. 연쇄·동일 프레임 중복은 금지하며 매칭되지 않은 관측은 단독점으로 보존한다.

대표 XYZ는 프레임별 Confidence 10/90분위로 정규화·[0.1,1] clipping한 상대 가중 평균, RGB는 채널별 median이다. Confidence는 확률이 아니다. 원본 관측 index·camera·pixel·깊이·Confidence·원본 RGB sample 좌표를 CSR과 부모 해시로 연결한다.

Visibility는 현재 공유점의 native-resolution nearest-pixel z-buffer, 양수 Z/frustum, 초기 Depth agreement, 초기 경계·Confidence 조건으로 추정한다. 1/3/5% 상대 prior gate를 비교하며 기본은 3%다. 렌더러의 5×5 splat visibility와 완전히 같지는 않다. O(실제 원본 출처를 갖는 추정 그룹)와 V(투영상 보일 가능성)를 혼동하지 않는다.

고정 마스크 밖으로 누락된 픽셀을 숨기지 않고 별도로 집계한다. 각 source가 같은 대표점을 참조하면 층 퍼짐이 0이 되는 부분은 구조적으로 생긴 것이므로 독립 기하 개선의 증거로 삼지 않는다. 점 수 감소·RGB 변화도 GT 정확도 향상을 뜻하지 않는다.

`handoff.py`는 향후 E3를 위한 후보와 초기점을 통과하는 owner Ray를 저장한다. 이는 Euclidean ray length이며 카메라 Z와 다르다. 원본 owner 픽셀의 Ray를 그대로 쓰면 융합 초기점을 옮길 수 있으므로 fused xyz0를 통과하는 Ray로 초기화한다. E3 최적화는 별도 실행이다.

완료 결과·수치·제한은 [E2 보고서](../../../docs/experiments/pointmap_refinement/E2/README.md)를 따른다.
