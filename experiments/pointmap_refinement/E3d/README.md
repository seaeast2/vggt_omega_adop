# E3d — ADOP 방식 1픽셀·깊이 제한·근사 위치 기울기

E0c의 색 조건 융합 초기값과 E3c의 고정 색·카메라·CSR·이동 후보 106,687개·학습 픽셀·owner-ray 변수·Adam/200회 설정을 유지한다. 정방향을 최근접 1픽셀+앞면 깊이 1% 이내 평균으로 바꾸고, 역방향은 ADOP 논문 §3.1 및 원본 코드 mode 4의 이웃 픽셀 가상 삽입 기울기를 구현한다. 별도 깊이 혼합의 미분은 사용하지 않는다.

이는 ADOP 아이디어의 로컬 구현이며 ADOP 전체 재현이 아니다. 신경망·특징 학습·톤매퍼·카메라 최적화·환경맵·법선 culling·다중 해상도·무작위 point/ghost dropout은 생략했다. 공식 코드의 `ghost_gradients=false`에 해당하는 가시 점의 근사 기울기를 사용한다. 원본의 SGD 대신 기존 E3c의 Adam을 유지해 변경 범위를 제한한다. RGB와 카메라를 학습하지 않는다.

작은 연속 이동에서는 이산 정방향의 미분이 0이므로, 정확한 유한차분 일치를 근사 기울기의 성공 조건으로 삼지 않는다. 알려진 1픽셀 투영·앞/뒤/유사 깊이 평균·각 이웃 삽입 사례·perspective Jacobian을 독립 수식으로 검사하고 실제 장면의 유한 이동 손실을 기록한다. 실제 장면의 방향이 불리해도 고정된 200회 시험을 보존하며 결과를 보고 조건을 튜닝하지 않는다.

```bash
# GPU 작업은 샌드박스 밖 호스트에서 실행한다.
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3d/run.py \
  --config experiments/pointmap_refinement/E3d/config.json \
  --run-id tum-freiburg1_desk-E3d-20261112-001
```

선택은 사전 체크포인트의 고정 RGB 손실만 사용한다. 선택 후 기존 스케일로 GT 깊이를 평가한다. 실내 개선 기준은 RGB≥1% 감소, GT RMSE≥1% 감소, AbsRel 비증가, 고정 GT 영역 coverage 저하≤0.5%p, selected>0을 모두 만족하는 것이다. 미충족이면 사용자 요청에 따라 실내 추가 튜닝을 중단하고 HKairport01/AMtown01 드론 원본 영상으로 별도 시험한다. 현재 환경의 드론 입력 경로는 확인 중이다. GT가 없는 후속 장면에서는 RGB 감소를 기하 개선으로 판정하지 않는다.

실행별 코드·입력 해시·체크포인트·초기/selected/실제 last·원본 해상도/학습 해상도 RGB·native 출처 색·PLY를 독립 폴더에 보존한다. 재실행에는 새 Run ID가 필요하다.
