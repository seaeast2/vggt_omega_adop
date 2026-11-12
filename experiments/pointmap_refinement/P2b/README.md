# P2b — E0b 초기 RGB 렌더의 검은 테두리·alpha 진단

E3b가 보존한 E0b 초기 RGB/alpha/target/고정 마스크를 읽어 기하·카메라·가림을 바꾸지 않고 alpha 곱의 영향을 분리한다. 현재 P2의 RGB는 `weighted_color * alpha + black * (1-alpha)`다. alpha>1e-6인 픽셀에서 저장 RGB/alpha로 weighted_color를 복원하고 나머지는 검정으로 남긴다. 이는 저장 버퍼 기반의 색상 진단이며 새 renderer나 미분 가능성·기하 보정을 검증한 실험은 아니다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P2b/run.py \
  --run-id tum-freiburg1_desk-P2b-20261112-001
```

CPU만 사용하며 새 Run ID를 지정한다. 원본 RGB/alpha와 진단 RGB를 별도 저장하고 원본 E3b/P2를 수정하지 않는다. 목표 RGB / 기존 검은 배경 합성 / alpha 곱 제거 진단 / alpha 회색조를 같은 격자에서 비교한다. native 128×96은 최근접 4배 표시만 적용한다.

Reference 평균 RGB>.25, rendered 평균 RGB<.12의 픽셀 수와 해당 alpha, 학습 마스크 포함 여부를 탐색적으로 보고한다. 이는 검은 테두리 전체의 검출기나 GT 정확도 지표가 아니다. E1 고정 마스크 PSNR과 기존 학습 마스크 Charbonnier도 같은 픽셀에서 계산하되 밝기 합성식만 바꾼 수치를 기하 개선으로 해석하지 않는다. Default P2·기존 E3b 결과·Gradient를 변경하거나 새 최적화를 실행하지 않는다.
