# E0d — UAVScenes 드론 Omega 공동 추론·색 조건 융합 기준선

사용자가 제공한 `sijieaaa/UAVScenes`의 고정 revision에서 HKairport01·AMtown01을 별도 Run ID로 처리한다. 전체 28.7GB ZIP 대신 HTTP Range로 중앙 목차와 필요한 원본 영상·대응 LiDAR·메타데이터만 받는다. 추출 항목의 ZIP CRC/크기·SHA-256을 검증하며 전체 아카이브 해시를 로컬 검증했다고 주장하지 않는다.

처음의 cache-only 120/124/128 구간은 메타데이터 이동이 작아, 이미지 확인·추론·최적화 전에 선택 규칙을 수정했다. 정렬 인덱스 i≥120 중 `norm(T[i+8].translation−T[i].translation)≥5`인 첫 구간에서 i/i+4/i+8을 사용한다. 두 장면 모두 126/130/134다. 이는 메타데이터 이동 proxy이며 T4x4의 자세 방향과 실제 baseline GT는 아직 검증되지 않았다. 이전 cache-only 다운로드와 선택 변경 사실을 보존한다.

각 장면의 세 원본 이미지를 Omega에 **동시에** 입력한다. 같은 P0 체크포인트·max_size·512·seed=0을 사용한다. Raw 역투영 관측을 저장하고, E0c 코드를 그대로 사용해 원본 RGB 채널별 그룹 범위≤30의 순차 깊이 평균을 수행한다. 거절 점은 보존한다. E3c와 같은 active 선정 정책으로 다중 출처 후보를 만들고 RGB 중앙값·카메라·CSR·학습 마스크를 고정한다. 해상도는 원본 비율을 유지하며 렌더는 그 1/4이다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E0d/fetch_inputs.py --scene HKairport01 --run-id hkairport01-E0d-20261112-001
# 샌드박스 밖 호스트 GPU에서 실행한다.
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python results/pointmap_refinement/hkairport01-E0d-20261112-001/stages/E0d/artifacts/source/infer.py --checkpoint checkpoints/vggt_omega_1b_512.pt --frames results/pointmap_refinement/hkairport01-E0d-20261112-001/stages/E0d/artifacts/data/frames.json --mode max_size --count 3 --output results/pointmap_refinement/hkairport01-E0d-20261112-001/stages/E0d/artifacts/inference
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python results/pointmap_refinement/hkairport01-E0d-20261112-001/stages/E0d/artifacts/source/finalize.py --stage results/pointmap_refinement/hkairport01-E0d-20261112-001/stages/E0d
```

AMtown01에는 `amtown01-E0d-20261112-001`과 해당 장면 이름을 사용한다. 실패·완료 실행은 덮어쓰지 않는다. 다운로드·모델 추론·CPU 융합 로그와 코드·입력 출처·중간/최종 점군을 분리한다. 본 실행은 새 Omega 추론이며 과거 일반 VGGT/MASt3R PLY를 사용하지 않는다.

대응 LiDAR와 카메라/지도 보정 정보는 있으나 interval5 영상의 왜곡 처리와 LiDAR 좌표계 규약을 독립 검증하지 못했다. 따라서 이번에는 GT 깊이·스케일·정확도를 평가하지 않으며 제공되지 않는다고 단정하지도 않는다. 보정과 메타데이터는 후속 검증을 위해 보존한다. 단순 색 팔레트·점 수·RGB 잔차를 기하 정확도로 해석하지 않는다.
