# E3e — 드론 초기값의 고정 RGB·카메라 최소 ADOP 방식 정점 이동

HKairport01과 AMtown01의 새 E0d 색 조건 융합 점군을 별도 Run ID로 사용한다. E3d의 1픽셀 정방향·앞면 1% 평균·가시점 이웃 삽입 근사 기울기 구현을 **renderer.py 바이트 그대로** 재사용한다. RGB·카메라·관측 그룹·점 수·후보·학습 마스크를 고정하고, owner 시선 log 거리만 Adam lr=.001·범위±.05·200회 이동한다. ADOP 전체 재현이나 ghost dropout 설정의 재현이 아니다.

장면별 초기값·active set과 E0d 초기 깊이 경계/confidence/coverage 마스크는 E0d에서 정해 고정한다. 입력 비율에 따라 native 512×432, 학습 128×108이며 양쪽 비교 영상의 target도 같은 해상도로 처리한다. 실제 한 픽셀·깊이 평균·이웃 삽입 gradient·투영 chain rule을 먼저 검사한다. 근사 기울기를 이산 정방향의 정확한 미분으로 주장하지 않는다.

```bash
# 샌드박스 밖 호스트 GPU에서 실행한다.
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3e/run.py \
  --config experiments/pointmap_refinement/E3e/hkairport01.json --run-id hkairport01-E3e-20261112-001
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/pointmap_refinement/E3e/run.py \
  --config experiments/pointmap_refinement/E3e/amtown01.json --run-id amtown01-E3e-20261112-001
```

Selected는 사전 체크포인트의 고정 RGB 손실 최소로 고른다. Last의 실제 이동도 따로 보존한다. 원본 해상도의 초기 유효 투영 영역과 학습 픽셀의 coverage 감소도 함께 보고한다. 광도 개선 표시는 selected>0, RGB 감소≥1%, 두 coverage 저하≤0.5%p를 동시에 만족할 때만 한다. 동일 입력 시점의 한 그룹 시험이며 독립 held-out·시퀀스 SLAM·전체 3D 정확도 검증은 아니다.

대응 LiDAR와 보정 메타데이터는 있지만 좌표계/영상 왜곡 규약이 아직 독립 검증되지 않았다. 이 실행은 GT 오차나 미터 스케일을 계산하지 않는다. 기하 개선은 미평가로 표시한다. 기존 실내 실행과 E0d는 변경하지 않으며 실패·완료 실행을 덮어쓰지 않는다.
