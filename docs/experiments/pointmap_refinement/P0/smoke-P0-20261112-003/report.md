# P0 결과 보고서 — smoke-P0-20261112-003

**판정: P0 완료.** 고정된 공식 가중치로 7회 추론이 모두 성공했고, 3장 기준선의 별도 프로세스 반복에서 출력 배열이 정확히 일치했다. 이 판정은 실행 가능성에 관한 것이며 기하 정확도·Point Cloud 정렬 개선을 뜻하지 않는다.

## 조건 및 출처

- 실행일: 2026-11-12, Asia/Seoul. 모든 GPU 작업은 호스트에서 샌드박스 밖으로 실행했다.
- GPU: RTX 5060, Driver 595.99.02, PyTorch 2.15.0 / CUDA runtime 13.2, Python 3.11.18. 전체 환경은 실행 폴더의 `environment.json`에 기록했다.
- 공식 코드 Commit: `48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6`.
- 모델: `facebook/VGGT-Omega`, revision `1041e80fc0e911235d3426b0a3d9a81075111a53`, `vggt_omega_1b_512.pt`.
- 체크포인트 SHA-256: `c02da418b18bb01d0392598d3f6147366bcde1bb70fd08a5e3bf7925b0667934`. 다운로드 후 실제 파일을 배포 해시와 대조했다.
- 입력: TUM freiburg1_desk의 RGB 유효 행 30/40/50/60(0 기반). 처음 N장을 사용했다. 이전 회차와 동일 원본이며 GT는 읽지 않았다. 원본 SHA-256과 전처리 정보는 `artifacts/data/frames.json`, `evaluation/preprocessing.json`에 있다.
- resolution=512, Seed=0, float32 모델 파라미터와 공식 내부 autocast를 사용했다. max_size 입력은 512×384, balanced는 592×448이다.
- 이전 회차 001/002는 변경하지 않았다. 최초 Xet 전송이 지연되어 해당 다운로드 프로세스만 종료하고 `HF_HUB_DISABLE_XET=1`로 공식 HTTP 다운로드를 재시도했다. 두 로그를 보존했다.

## 실측 결과

| 실행 | Peak allocated (GiB) | Peak reserved (GiB) | Forward+camera (s) | 모델 로드+추론 (s) | 종료 후 GPU 사용 (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| max_size_n03 | 4.633 | 4.822 | 0.757 | 10.036 | 14 |
| max_size_n02 | 4.511 | 4.639 | 0.382 | 9.335 | 14 |
| max_size_n04 | 4.755 | 5.010 | 0.557 | 9.662 | 14 |
| balanced_n02 | 4.595 | 4.768 | 0.407 | 9.273 | 14 |
| balanced_n03 | 4.760 | 5.035 | 0.516 | 9.671 | 14 |
| balanced_n04 | 4.925 | 5.283 | 0.653 | 9.762 | 14 |
| max_size_n03_repeat | 4.633 | 4.822 | 0.453 | 9.280 | 14 |

각 조건은 별도 프로세스에서 실행했다. Peak는 CUDA 초기화 직후 reset하여 모델 로드와 추론을 포함한 PyTorch 메모리를 측정했다. Forward 시간에는 카메라 변환이 포함되고 CUDA synchronize를 사용했다. 모델 로드+추론에는 CPU 체크포인트 로드와 전처리가 포함되며 NPZ 압축 저장은 제외된다. 조건별 1회 측정이므로 안정적인 성능 벤치마크가 아니며 첫 실행의 초기화·캐시 영향을 포함한다. GPU 프로세스 실행 전후 nvidia-smi 사용량은 모두 14 MiB로 돌아왔다. PyTorch reserved와 GPU 전체 메모리 사용량은 다른 지표다.

## 산출물 검증 및 반복 재현성

7회 모두 모델 strict state-dict 로드, 원본 RGB 전처리, 카메라 world-to-camera extrinsics·intrinsics, pose encoding·depth·depth confidence 출력과 NPZ 저장을 성공했다. 모든 저장 배열의 유한값, 양수 깊이, RGB 입력 수를 검사했다. NPZ를 다시 열어 메모리 배열과 정확히 일치하는지 검증했다.

3장 max_size의 첫 실행과 별도 프로세스 반복을 비교했다. camera_and_register_tokens, pose_enc, depth, depth_conf, images, extrinsics, intrinsics의 **최대 절대 차이는 모두 0**이었다. 사전 코드 허용오차 rtol=1e-5, atol=1e-6도 통과했다. 이는 동일 입력·장비·환경·Seed에서의 2회 비교에 한정한다.

## 경로 및 재현

산출물 루트: `results/pointmap_refinement/smoke-P0-20261112-003/stages/P0/`.

- `artifacts/inference/<trial>/vggt_omega_raw.npz`: 원본 예측, 카메라, 전처리 RGB. 3장 기준선은 `max_size_n03/`다.
- `artifacts/inference/<trial>/metrics.json`: 형상, 시간, 메모리, NPZ SHA-256.
- `evaluation/trials.json`: 정확한 실행 명령, 종료 코드, GPU 전후 사용량.
- `evaluation/reproducibility.json`: 배열별 반복 비교.
- `evaluation/checkpoint.json`: 고정 revision과 체크포인트 검증.
- `logs/`: 접근·전처리·다운로드·추론의 전체 로그.
- `manifest.json`: 설정·스크립트·산출물의 경로와 SHA-256. 프로젝트 기준 Commit과 미커밋 소스 사본으로 실행 코드를 추적한다.

실행 진입점은 [run_trials.py](../../../../../experiments/pointmap_refinement/P0/scripts/run_trials.py)이며 `--stage`로 새 실행 경로를 지정한다. 준비 절차는 [P0 안내](../../../../../experiments/pointmap_refinement/P0/README.md)를 따른다.

## 범위와 다음 단계

P0의 환경, 체크포인트 로드, 2/3/4장과 두 전처리 모드 추론, 저장, 반복 및 프로세스 종료 후 메모리 회수 검증을 완료했다. 4장 성공은 이번 입력·설정에서의 관측이며 일반적인 최대 입력 수를 의미하지 않는다. 출력 기하의 정확도나 후속 렌더러와 동시 실행 가능성은 검증하지 않았다. 다음 작업은 P1 좌표계·역투영 검증이며 이번 회차에서는 시작하지 않았다.
