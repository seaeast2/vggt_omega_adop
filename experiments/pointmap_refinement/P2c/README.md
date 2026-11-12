# P2c — 색 합성·지지 범위·가림의 분리 수정과 실제 미분 검증

E3b `...-002`에 보존된 E0b 초기 점군·고정 원본 RGB·135,193개 active 점·목표 RGB·학습 마스크를 그대로 사용한다. 이전 P2/E3b는 수정하지 않는다. 호스트 GPU에서 다음 명령을 샌드박스 밖으로 실행한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P2c/run.py \
  --run-id tum-freiburg1_desk-P2c-20261112-001
```

새 Run ID만 허용한다. 네 변형은 실행 전에 config.json으로 고정한다.

1. `legacy`: 기존 P2 그대로, hard front 3%·alpha 검은 배경 합성.
2. `normalized_hard`: 같은 stencil/가림, alpha 곱만 제거한 정규화 색상.
3. `compact_hard`: 2px 원형 경계에서 값과 1차 미분이 0인 compact Gaussian을 사용하되 hard front 유지.
4. `compact_soft`: 같은 compact kernel, 정규화 색상, 연속 깊이 가중치 exp(-Z/tau). tau는 초기 양수 camera-Z 중앙값×.1로 카메라별 고정한다. 가중치의 log-sum-exp 안정화 상수는 정규화 RGB/Depth에서 상쇄되므로 상수의 미분은 필요하지 않다.

Compact 방식의 alpha는 가림 전 spatial mass의 진단용 지원도다. RGB에 곱하지 않는다. 기존 alpha와 같은 물리적 opacity로 비교하지 않는다. 모든 실제 손실은 기존 E3b의 같은 초기 고정 마스크로 계산한다.

검증은 약한 전경 주변점/강한 전경의 가림 제어, 픽셀 stencil 경계의 float64 미분, 알려진 평면 깊이 회복, 실제 E0b의 float32 방향 유한차분, compact_soft의 float64 방향 유한차분, 네 변형의 10회 Adam 업데이트다. 원본 실제 점군은 보존하며 업데이트는 별도 좌표/PLY에 저장한다.

E3b 재실행 허용 조건은 합성 미분·평면·가림 제어 통과, compact_soft의 실제 float64 방향 미분 오차가 지정 tolerance 이내, float32 epsilon=1e-4/1e-3의 실제 +감소 방향 손실 감소, 10회 후 손실 감소와 고정 영역 spatial-support coverage 감소≤.5%p다. 실행 완료와 이 허용 판정은 구분한다. 합성 GT는 생성된 장면에만 사용하고 실제 GT/독립 시점/벽 두께/전체 3D 정확도는 평가하지 않는다. Soft 깊이 가중치는 엄밀한 불투명 표면 렌더링이 아니며 배경 색 혼합·밀도 의존성이 남을 수 있다.
