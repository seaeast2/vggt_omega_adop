# 지상 촬영 야외 LiDAR 샘플

도시 길거리 KITTI와 자연물 중심 ETH3D forest의 RGB/영상·캘리브레이션·공식 깊이 GT를 확보한다. 데이터 준비 단계 O0이며 모델 추론과 정확도 비교는 실행하지 않는다. TUM과 드론 샘플은 사용하지 않는다.

[샘플 목록](catalog.json) · [선정·검증 결과와 미리보기](../../docs/experiments/outdoor_lidar_samples/index.md)

```bash
# 다운로드는 네트워크 접근이 가능한 호스트에서 실행한다. GPU는 사용하지 않는다.
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/outdoor_lidar_samples/acquire.py kitti
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/outdoor_lidar_samples/acquire.py forest
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/outdoor_lidar_samples/prepare.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/outdoor_lidar_samples/verify.py results/outdoor_lidar_samples/O0-20261114-002
```

다운로드는 `data/outdoor_lidar_samples/`, 준비한 깊이·유효 mask·카메라 배열은 `results/outdoor_lidar_samples/O0-*/`에 저장한다. 준비 단계는 실행마다 새 번호를 부여한다. KITTI ZIP은 HTTP byte range로 중앙 디렉터리와 선택한 파일만 받고 CRC를 검사한다. ETH3D 7z는 원본 archive를 보존한다. 입력별 URL·크기·SHA-256을 기록한다.

forest rig의 네 카메라는 같은 timestamp 파일명을 공유한다. 이미지 식별자는 카메라 디렉터리와 파일명을 함께 사용한다. 원본 왜곡 영상의 GT를 공식 카메라 모델로 undistorted 격자에 옮기며 결측 GT는 보간하지 않는다. 반환 NPZ의 `intrinsics`는 픽셀 index 중심 규약이다.

기존 `global_planar_pointmap`의 `eth3d_laser.py`는 DSLR archive와 I14/I15 캐시를 전제한다. 이 두 샘플을 해당 기본 목록에 바로 넣지 않는다. 후속 실험에는 KITTI의 resize/K/pose·동적 물체 처리와 forest의 흑백 입력·결측/경계 처리, 보류 평가 split을 먼저 동결해야 한다.

2026-11-14 후속 실행: 전용 `outdoor.py` adapter로 [I26 야외 전이 시험](../../docs/experiments/global_planar_pointmap/I26/index.md)을 완료했다. 동적 물체를 제거하지 않는 기존 전체 화면 알고리즘의 전이 범위를 명시했다. 숲은 허용 named anchor가 0개라 A1의 동일 출력 조기 종료를 사용했다.

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py prepare
# 다음 두 GPU 명령은 샌드박스 밖 호스트에서 실행한다.
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py infer
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py freeze
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py segment
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py pipeline
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor.py evaluate
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/outdoor_report.py
```

이 명령들은 재실행 시 새 run을 만든다. 실제 첫 실행에서는 숲의 I3 중간에 A1 조건을 확인해 해당 run을 보존·중단한 다음 `outdoor.py no_named --dataset eth3d-forest-rig`로 이어갔다. 현재 `pipeline` 명령은 같은 조기 종료 조건을 처음부터 검사한다.
