# E3b — E0b 융합 점군에서 시작하는 RGB 미분 위치 최적화

E0b의 XYZ·관측 그룹·최신 owner를 초기값으로 재사용하고, 원본 RGB의 Photo Charbonnier 손실을 역전파해 점을 실제 이동시킨다. 기존 E3와 같은 owner 시선 방향 거리 변수·Adam lr=.001·log 이동 ±.05·200회·P2 renderer를 사용한다. 카메라·점 수·관측 그룹·점당 RGB는 고정한다. E0b의 순차 깊이 평균을 다시 실행하지 않는다.

점당 RGB는 E0 원본 관측 색을 E0b CSR 그룹별 채널 median으로 집계한다. 프레임 팔레트는 PLY/출처 진단에만 사용한다. 학습 후보는 서로 다른 2개 이상 source camera, 비영 시차, 모든 출처의 초기 추정 가시성 조건을 통과한 점이다. 가시성은 기존 E2/E3의 front 3%, Depth prior 3%+median Depth×.002, Depth 경계 3%, Confidence 하위 10% 제외 정책이다. 후보 집합은 고정한다.

새 Run ID 예: `tum-freiburg1_desk-E3b-20261112-002`. 순서대로 실행한다.

```bash
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3b/prepare.py --run-id tum-freiburg1_desk-E3b-20261112-002
# GPU 명령은 샌드박스 밖 호스트에서 실행한다.
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E3b/train.py --stage results/pointmap_refinement/tum-freiburg1_desk-E3b-20261112-002/stages/E3b
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3b/evaluate.py --stage results/pointmap_refinement/tum-freiburg1_desk-E3b-20261112-002/stages/E3b
```

`prepare.py`는 CPU에서 부모 해시·원본 출처를 검증하고 고정 RGB·시선·후보·목표 영상을 만든다. `train.py`는 GT를 읽지 않으며 0/20/.../200 체크포인트와 초기/선택/마지막 결과를 보존한다. `evaluate.py`는 선택을 끝낸 뒤 처음 GT를 읽어 초기 E0b에서 단일 스케일을 맞추고 전후의 공통 픽셀 오차와 고정 영역 coverage를 보고한다. selected가 초기라면 개선으로 포장하지 않고 실제 이동된 last도 보존한다. hard stencil/front의 미분 한계는 기존 E3와 같다.

사용자 요청으로 비교만 수행했던 E3b의 코드·보고서·로컬 run `...-001`은 삭제했다. 그 기록은 Git 커밋 `6de932f167f577ddcb7b7b500412da53eb69444e`에서만 확인할 수 있다. 현재 E3b는 위 미분 최적화 실험을 뜻하며 새 run `...-002`로 구분한다. E0b/E3 등 다른 실험은 변경하지 않는다.
