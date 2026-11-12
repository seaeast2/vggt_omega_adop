# E3c — 색 조건 융합 초기값의 RGB 미분 정점 이동

E0c의 419,864점에서 시작해 원본 RGB 손실을 역전파한다. E0b 초기값의 대조군도 같은 P2c `compact_soft` 렌더러·공통 학습 픽셀·온도·최적화 설정으로 실행한다. 두 arm은 같은 E3c Run ID 아래 독립 폴더에 보존한다. 기존 E3b 결과와 혼합하지 않는다.

카메라·그룹별 원본 RGB 중앙값·점 수·관측 CSR·active set은 고정한다. 기존 E3b 정책으로 선정한 다중 출처 정점만 owner 시선 방향 log 거리로 이동한다. 픽셀 위치는 이동한 3D 정점을 각 카메라로 투영한 결과다. 자유 XYZ 이동이나 직접 2D 픽셀 변수를 이번에 추가하지 않는다. 단일 출처·초기 가시성 탈락 점도 렌더에는 포함하되 이동시키지 않는다.

공통 학습 마스크는 E1 고정 마스크와 두 초기 점군의 compact spatial support(alpha≥.5)의 교집합이다. 카메라별 깊이 온도는 초기 E0b의 양의 Z 중앙값×.1로 한 번 정해 두 arm에 동일 적용한다. Alpha는 지원도 진단이며 RGB에 곱하지 않는다. 모든 학습/선택에서 GT를 읽지 않는다.

두 arm 각각 실제 전체 점군 FP64 방향 미분·FP32 감소 방향·독립 10회 최적화를 검사한다. 모두 통과하면 초기 delta=0과 새 Adam으로 정식 200회를 실행한다. 사전 체크포인트의 고정 학습 손실만으로 selected를 고르고 실제 last도 보존한다. 지원도 저하·실패를 숨기거나 GT로 선택하지 않는다.

```bash
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3c/prepare.py --run-id tum-freiburg1_desk-E3c-20261112-001
# 아래 GPU 명령은 샌드박스 밖 호스트에서 실행한다.
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3c/train.py --stage results/pointmap_refinement/tum-freiburg1_desk-E3c-20261112-001/stages/E3c
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3c/evaluate.py --stage results/pointmap_refinement/tum-freiburg1_desk-E3c-20261112-001/stages/E3c
```

재실행에는 새 Run ID를 쓴다. `prepare.py`는 입력 해시·관측 분할과 E0b 기존 초기값 재현을 검사한다. `train.py`는 미분/사전 검사·체크포인트·실제 좌표와 렌더를 저장한다. `evaluate.py`는 그 이후에만 기존 고정 스케일로 GT 깊이를 평가하고 initial/selected/last PLY·RGB/출처 패널을 생성한다. 두 arm의 공통 픽셀 GT 오차와 coverage를 함께 보고한다. 색 조건의 효과에는 그룹·점 수·이동 후보 집합의 변화가 함께 포함되며 동일 물리점 대응의 정답은 없다. 같은 입력 시점의 RGB 감소를 전체 3D 정합 성공으로 판단하지 않는다.
