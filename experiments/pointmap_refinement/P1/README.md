# P1 — 좌표계·역투영 및 관측 데이터 계약

P0의 3장 max_size 결과를 읽기 전용으로 사용해 CPU에서 실행한다. 공식 소스의 camera-from-world, 카메라 Z-depth, 정수 픽셀 규약을 따른다. 공유점 융합과 위치 최적화는 수행하지 않는다.

고정 입력·허용오차는 `config.json`에 있다. 기존 Python 3.11 환경과 P0에서 고정한 의존성을 사용한다. 아래 Run ID는 매번 새 이름으로 지정해야 한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P1/scripts/run.py \
  --run-id tum-freiburg1_desk-P1-20261112-001
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P1/scripts/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-P1-20261112-001/stages/P1
```

`run.py`는 합성 기하의 정상·오류 대조군, 공식 역투영과의 일치, 실제 자기·타 시점 투영, GT Depth의 시간·격자 연계 및 관측 NPZ·PLY 저장/재로딩을 검사한다. `verify.py`는 원본 RGB 해시와 전처리 재생성, 관측의 frame/pixel별 RGB·Depth 일치 및 Resize Intrinsics 계약을 추가 확인한다. 둘 다 종료 코드 0이어야 완료할 수 있다. 실행 결과를 Manifest로 봉인하고 보고서를 작성한 뒤 커밋·푸시한다.

GT는 격자 확인 전용이며 모델 입력이나 최적화에 사용하지 않는다. TUM Depth와 RGB의 물리적 등록 정확도나 모델의 GT 정확도를 재검증한 결과가 아니다. 타 시점 깊이 잔차는 예측 간 진단이다.

실제 수치와 한계는 [P1 보고서 목록](../../../docs/experiments/pointmap_refinement/P1/README.md)을 따른다.
