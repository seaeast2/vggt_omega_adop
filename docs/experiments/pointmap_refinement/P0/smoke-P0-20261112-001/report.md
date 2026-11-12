# P0 결과 보고서 — smoke-P0-20261112-001

**판정: 환경·입력 전처리 검증 통과, 공식 체크포인트 인증 문제로 P0 미완료.** 실행 상태는 `stopped`다. VGGT-Ω 모델 추론이나 Point Cloud 생성에 성공했다는 결과는 없다.

## 목적 및 실행 범위

졸업논문 실험의 첫 단계로, RTX 5060에서 공식 VGGT-Ω를 실행할 수 있는 환경과 고정 RGB 입력을 준비했다. 목표는 3장 추론 결과를 저장하고 2/4장 및 전처리 모드를 비교하는 것이지만, 이 실행에서는 가중치 접근 이전의 환경·전처리까지만 검증했다. GT, 최적화 손실, 기하 정확도는 사용·측정하지 않았다.

실행일은 2026-11-12, 시간대는 Asia/Seoul이다. CUDA 검사와 입력 전처리는 모두 샌드박스 밖 호스트에서 실행했다.

## 환경 및 소스

| 항목 | 확인 결과 |
| --- | --- |
| OS | Ubuntu 26.04.1 LTS, Linux 7.0.0-43-generic |
| GPU | NVIDIA GeForce RTX 5060, nvidia-smi 총 메모리 8151 MiB |
| Driver | 595.99.02 |
| CUDA | 드라이버 표시 13.2 / Toolkit nvcc 13.5 / PyTorch runtime 13.2 |
| Python | 전용 환경 3.11.18; 시스템은 3.14.4 |
| PyTorch / torchvision | 2.15.0 / 0.29.2 |
| NumPy / OpenCV | 1.26.4 / 4.11.0.86 |
| Compute capability | 12.0; 설치된 PyTorch에 sm_120 포함 |
| 공식 소스 Commit | `48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6` |
| 프로젝트 기준 Commit | `57b7fbd050189071e686aac9fdadf02a86827eaa` + 미커밋 P0 코드·문서 |
| 난수 Seed | 0 |

시스템 Python 3.14 대신 공식 `numpy<2`를 지원하는 Python 3.11 환경을 프로젝트 내부에 설치했다. OpenCV는 NumPy 2 요구와 충돌하지 않도록 4.12 미만을 선택했다. 전체 의존성은 `experiments/pointmap_refinement/P0/requirements.lock.txt` 및 실행 폴더의 `logs/pip_freeze.txt`에 기록했다. 공식 코드는 수정하지 않았다.

## 수행 결과

| 확인 항목 | 결과 | 범위 |
| --- | --- | --- |
| 호스트 GPU·드라이버 접근 | 통과 | nvidia-smi 정상 |
| CUDA FP32 행렬 연산 | 통과 | 64×64 항등행렬 곱 결과 일치 |
| CUDA BF16 행렬 연산 | 통과 | 64×64 항등행렬 곱 결과 일치 |
| BF16 SDPA attention | 통과 | 출력에 NaN/Inf 없음 |
| 공식 모델 import | 통과 | `VGGTOmega`; 가중치 로드는 아님 |
| RGB 전처리 | 6개 조합 통과 | 유한값 및 [0,1] 범위 검사 |
| 체크포인트 접근 | 실패 | HTTP 401, `GatedRepo`, credential_present=false |
| 실제 모델 추론 | 미실행 | 가중치 미확보 |
| 카메라·Depth·Confidence 저장 | 미실행 | 모델 출력 없음 |
| 추론 VRAM·시간·반복 재현성 | 미측정 | 프로브 결과를 추론 측정값으로 사용하지 않음 |

CUDA 프로브 종료 후 nvidia-smi 메모리 사용량은 14 MiB였다. 이는 프로브 종료 확인이며, 추론 프로세스 종료 후 메모리 회수 검증을 대체하지 않는다. `preflight.py`의 종료 코드는 2(가중치 접근 거부), `prepare_inputs.py`는 0이다. `infer.py`는 문법 확인만 수행했으며 모델 실행은 검증하지 못했다.

## 입력 및 전처리

[공식 TUM RGB-D 다운로드 페이지](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download)의 `freiburg1_desk` archive에서 640×480 RGB 4장을 선택했다. 입력 분할은 P0 부하 확인용이며 학습·검증 분할이나 기하 관측 가능성 검증을 의미하지 않는다. 2/3/4장 조건은 아래 순서의 처음 N장을 사용한다.

| 0 기반 행 번호 | RGB timestamp | SHA-256 |
| ---: | --- | --- |
| 30 | 1305031453.791716 | `2885cac2cd00afdba5b09d03f074efaec066c2b980f7ba8e32c99d80549abe0b` |
| 40 | 1305031454.127701 | `e7d9ebe77a418b083cad3d775cc8470ad3cb3fc99d3b8485f40e6c26ba60ad96` |
| 50 | 1305031454.459913 | `0e3d7dd5458823f7236b630597e059d680de28f2412ee2ac0e1494a7423734ce` |
| 60 | 1305031454.791641 | `13c3e26c431ffa6e58d2f03bf3ce9f69fd52455a7215a27fece7b7f1c1601c9c` |

Archive SHA-256: `e983d6830916e66dc4a46a71368046b149b283de87769690e7aa4e0b9483530c`. 이 값은 수신 파일의 관측 해시이며 배포자가 제공한 체크섬과 대조한 값은 아니다.

| 전처리 모드 | 입력 수 | 실제 텐서 형상 (N,C,H,W) |
| --- | --- | --- |
| max_size, resolution=512 | 2 / 3 / 4 | (N, 3, 384, 512) |
| balanced, resolution=512 | 2 / 3 / 4 | (N, 3, 448, 592) |

원본 종횡비가 지원 범위 안이고 크기가 모두 같아 Crop·Pad는 없었다. Resize는 고정된 공식 로더의 BICUBIC을 사용했다. 각 전처리 텐서 `.npy`와 SHA-256을 보존했다. 전처리된 RGB는 모델에 입력할 텐서이며 모델의 `predictions["images"]` 출력으로 간주하지 않는다.

## 저장 위치와 재현

모든 상대경로의 기준은 프로젝트 루트다.

- 산출물 루트: `results/pointmap_refinement/smoke-P0-20261112-001/stages/P0/`
- 설정·상태: `config_resolved.json`, `manifest.json`, `environment.json`
- 원본·전처리 입력: `artifacts/data/frames.json`, RGB PNG, `rgb_<mode>_n<NN>.npy`
- 공식 소스 근거: `artifacts/source/`의 Commit, 라이선스, 원본 requirements
- 평가 기록: `evaluation/checkpoint_access.json`, `preprocessing.json`, `commands.json`
- 설치·명령 로그: `logs/`; 종료 후 GPU 메모리는 `logs/nvidia_smi_after.csv`
- 재현 절차: [P0 실행 안내](../../../../../experiments/pointmap_refinement/P0/README.md)

실행 Manifest에는 산출물, 실행 스크립트·설정의 해시와 체크포인트 차단 상태를 보존한다. 데이터·가중치·외부 소스·가상환경·대용량 결과는 Git에서 제외하고 코드·설정·이 보고서는 Git으로 관리한다. 현재 작업은 미커밋 상태다.

## 미완료 사유와 다음 작업

[공식 VGGT-Ω 안내](https://github.com/facebookresearch/vggt-omega/blob/48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6/README.md)는 Hugging Face의 모델 접근 승인을 요구한다. 사용자가 승인·로그인 완료를 알렸지만, 이번 실험 프로세스는 `/home/hlee221212`의 기본 캐시 경로와 `huggingface_hub.get_token()`에서 인증정보를 확인하지 못했다. 다른 터미널·호스트 또는 사용자 지정 인증 경로 여부는 미확인이다. 승인 자체가 없다고 단정하지 않는다.

동일 호스트의 승인 계정으로 `.venvs/p0-py311/bin/hf auth login`을 완료하거나 올바른 인증 경로를 전달하면 다음 작업을 이어갈 수 있다. 토큰은 채팅·로그·저장소에 기록하지 않는다.

1. 새 Run ID에서 체크포인트 접근을 확인하고 revision·SHA-256과 함께 다운로드한다.
2. 이 실행의 RGB 출처·해시를 기록해 재사용하고 3장 max_size 추론을 실행한다.
3. 2/4장, balanced를 별도 프로세스에서 실행하고 OOM도 보존한다.
4. 저장된 카메라·깊이·신뢰도의 필수 필드와 유한값을 검증한다.
5. 3장 기준선을 반복하고 수치 차이 및 프로세스 종료 후 메모리 회수를 기록한다.

P0의 최소 완료 기준인 3장 추론 산출물 확보는 충족하지 못했다. 기하 정확도나 RGB 기반 Point Cloud 정렬의 효과에 대한 결론은 내리지 않는다.
