# V0 — 원본 VGGT 실내 RGB 3장 PLY

종료한 C 계열 방법과 별도의 육안 비교다. 공식 원본 VGGT-1B checkpoint와 공식 VGGT 소스 commit `a288dd0f14786c93483e45524328726ab7b1b4ce`를 사용한다. Omega 모델/체크포인트를 사용하지 않는다.

저장소 루트에서 기존 `.venvs/p0-py311`을 사용한다.

```bash
HF_HOME=.cache/hf-vggt .venvs/p0-py311/bin/python experiments/vggt_baseline/V0/download.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/vggt_baseline/V0/run.py
```

다운로드는 공식 HF revision과 LFS SHA-256/크기를 검증한다. 추론은 샌드박스 밖 호스트 GPU에서 실행한다. 기존 PyTorch를 오래된 upstream requirements 버전으로 재설치하지 않는다. 소스 import와 CUDA 지원은 실제 환경에서 먼저 확인한다.

SDK Xet 다운로드가 정체되면 해당 다운로드 프로세스를 중지한 뒤 `download_range.py`로 재개할 수 있다. 기존 partial을 보존하고 byte-range 응답의 status·Content-Range·크기 및 완성 파일의 LFS SHA-256을 검증한다. SDK partial에 빈 구간이 있으면 기존 prefix도 다시 내려받아 전체 해시가 일치할 때만 체크포인트로 채택한다.

원본 실내 index 30/40/50을 hash 확인 후 복사하고 3장을 한 번에 넣는다. 공식 전처리는 518×392이며 기존 Omega 512×384와 다르다. 기본 모델의 단일 forward에서 Depth/카메라와 직접 point-head 출력을 모두 보존한다. 주 비교 파일은 Depth 역투영 `vggt_depth_rgb.ply`, 출처별 비교는 `vggt_depth_frames.ply`다. point-head 파일은 별도 이름으로 구분한다.

confidence 필터·융합·위치/FoV 보정·GT 정렬은 적용하지 않는다. 새 Run ID/Stage에 raw NPZ, PLY, 카메라별 투영, source snapshot, config, 로그, manifest를 저장하고 보고서·그림·해시를 GitHub에 보존한다. 다른 모델의 좌표계와 scale이 같다고 가정하지 않는다.
