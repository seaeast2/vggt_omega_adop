# HKairport01 E3e 중간 기록

- 실행 전 E0d 초기점·고정 RGB/카메라/CSR/후보/마스크, E3d와 같은 renderer 바이트·Adam .001·log 이동±.05·200회·체크포인트를 등록했다.
- Native 512×432 / 학습 128×108. RGB≥1% 감소·selected>0·초기 native/학습 영역 coverage 저하≤0.5%p를 광도 개선 기준으로 고정했다.
- 보정 규약이 미검증된 LiDAR/pose를 학습·선택·GT 정확도에 사용하지 않는다. 기하 개선은 미평가다.
