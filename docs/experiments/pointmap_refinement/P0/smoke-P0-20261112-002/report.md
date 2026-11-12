# P0 결과 보고서 — smoke-P0-20261112-002

**판정: 호스트 로그인 확인, 모델 접근 승인 대기로 추론 차단. P0 미완료.** 실행 상태는 `stopped`다.

## 목적 및 이전 실행과의 관계

사용자의 호스트 로그인 완료 후 P0 최소 추론을 재시도했다. 이전 실행 `smoke-P0-20261112-001`은 수정하지 않고 보존했다. 장면·프레임 선택·공식 소스·전용 환경은 이전 회차와 같으며, 인증 후 공식 가중치 접근을 다시 확인했다. 실행일은 2026-11-12, 시간대는 Asia/Seoul이다. GPU 검사와 전처리는 호스트에서 샌드박스 밖으로 실행했다.

## 인증 및 체크포인트

| 항목 | 관측 결과 |
| --- | --- |
| CLI 로그인 | 확인됨 |
| `huggingface_hub.get_token()` | 인증정보 존재 확인; 값은 기록하지 않음 |
| 모델 저장소 | `facebook/VGGT-Omega` |
| 모델 revision | `1041e80fc0e911235d3426b0a3d9a81075111a53` |
| 체크포인트 | `vggt_omega_1b_512.pt` |
| API가 제공한 크기 | 4,576,706,117 bytes |
| API가 제공한 SHA-256 | `c02da418b18bb01d0392598d3f6147366bcde1bb70fd08a5e3bf7925b0667934` |
| 파일 요청 | HTTP 403, `GatedRepo` |
| 서버 사유 | 모델 접근 신청 검토 대기 |
| 실제 파일 확보·해시 대조 | 미실행: 다운로드 거부 |

다운로드 예외의 핵심 응답은 “Your request to access model facebook/VGGT-Omega is awaiting a review from the repo authors.”다. 로그인은 확인됐지만 체크포인트 접근은 승인되지 않았다. 공개 모델 메타데이터 조회 성공을 가중치 접근 성공으로 해석하지 않는다. 토큰을 새로 생성하거나 재로그인하면 모델 승인이 완료된다고 판단하지 않는다.

## 환경 및 입력 검증

| 항목 | 관측 결과 |
| --- | --- |
| GPU | NVIDIA GeForce RTX 5060, capability 12.0 |
| Python / PyTorch | 3.11.18 / 2.15.0 |
| CUDA | PyTorch runtime 13.2, Toolkit 13.5, Driver 595.99.02 |
| 공식 소스 Commit | `48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6` |
| CUDA FP32/BF16 행렬 계산 | 통과 |
| BF16 SDPA 유한값 검사 | 통과 |
| 공식 모델 import | 통과; 가중치 로드는 아님 |
| RGB 전처리 | 2/3/4장 × max_size/balanced, 6개 조합 통과 |

TUM `freiburg1_desk` archive를 재사용해 RGB 유효 행 30/40/50/60(0 기반)을 새 실행 폴더에 추출했다. 이전 실행의 원본 RGB 및 전처리 배열과 SHA-256이 일치하는지 대조했다. Archive SHA-256은 `e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c`이며 배포자 체크섬과 대조한 값은 아니다. `max_size` 텐서는 `(N,3,384,512)`, `balanced`는 `(N,3,448,592)`다. GT는 사용하지 않았다.

`preflight.py`는 CUDA 검사를 통과한 후 모델 접근 거부로 종료 코드 2를 반환했다. 체크포인트 다운로드 명령은 종료 코드 1, `prepare_inputs.py`는 0이다. 실제 모델 추론, Pose·Intrinsics·Depth·Confidence 생성, 추론 시간·최대 VRAM 및 추론 반복 재현성은 모두 미실행·미측정이다. 기하 정확도나 Point Cloud 정렬 효과에 대한 결론은 없다.

## 산출물 및 다음 작업

프로젝트 루트 기준 산출물은 `results/pointmap_refinement/smoke-P0-20261112-002/stages/P0/`에 있다.

- `environment.json`, `config_resolved.json`, `manifest.json`: 환경·설정·상태·해시
- `evaluation/checkpoint_access.json`, `checkpoint_attempt.json`: 인증 상태와 배포 메타데이터, 접근 거부
- `artifacts/data/frames.json`, RGB PNG, 전처리 NPY: 새 회차의 고정 입력
- `evaluation/input_reuse_validation.json`: 이전 회차와 입력·전처리 해시 대조
- `logs/download_checkpoint.log`, `preflight.log`, `prepare_inputs.log`: 실행 로그
- `artifacts/source/`: 실행 코드·설정·의존성의 사본

[공식 모델 페이지](https://huggingface.co/facebook/VGGT-Omega)에서 접근 상태가 승인으로 바뀐 뒤 새 Run ID로 재시도한다. 그때 고정 revision에서 파일을 받아 실제 SHA-256을 대조하고, 3장 max_size 추론부터 실행한다. 이후 2/4장과 balanced를 비교하고 저장 파일·반복 실행·프로세스 종료 후 메모리 회수를 검증한다.

모델 접근 승인은 외부 상태이며 현재 실행에서 해결할 수 없다. 기존 기록을 유지하고 P0 완료 판정을 보류한다.
