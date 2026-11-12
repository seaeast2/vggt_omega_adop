# P1 결과 보고서 — tum-freiburg1_desk-P1-20261112-001

**판정: P1 좌표계·역투영 및 데이터 계약 검증 완료.** 원본 관측 589,824점을 NPZ·PLY로 저장했다. 공유점 융합·최적화·GT 정확도 평가는 수행하지 않았다.

## 입력과 재현 조건

- 실행일: 2026-11-12, Asia/Seoul. 호스트 CPU에서 실행했으며 GPU 추론은 재실행하지 않았다.
- P0 입력: `smoke-P0-20261112-003/stages/P0/artifacts/inference/max_size_n03/vggt_omega_raw.npz`.
- 입력 SHA-256: `d820f18f5bb683efb89d331f82262b68e5cec55a7bbadf379d8091721a26afa4`. 실행 전에 실제 파일과 대조했다. 부모 Manifest도 해시로 연결했다.
- RGB 3장, 모델 해상도 512×384. 원본 RGB는 640×480이며 Crop·Pad가 없는 BICUBIC Resize다.
- 공식 코드 Commit `48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6`, Python 3.11.18 / NumPy 1.26.4. float32 원본 예측을 float64로 변환해 기하 연산을 수행했다. Confidence 필터나 점 샘플링을 하지 않았다.
- 실행 명령: `.venvs/p0-py311/bin/python experiments/pointmap_refinement/P1/scripts/run.py --run-id tum-freiburg1_desk-P1-20261112-001`. 이어 `scripts/verify.py --stage results/pointmap_refinement/tum-freiburg1_desk-P1-20261112-001/stages/P1`를 같은 환경에서 실행했다. 두 명령 모두 종료 코드 0.

## 좌표계 계약과 합성 검증

[공식 pose_enc.py](https://github.com/facebookresearch/vggt-omega/blob/48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6/vggt_omega/utils/pose_enc.py)는 OpenCV camera-from-world 행렬을 정의한다. [공식 demo_gradio.py](https://github.com/facebookresearch/vggt-omega/blob/48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6/demo_gradio.py)의 역투영은 정수 `(u,v)`와 카메라 Z 깊이를 사용한다.

`P_c = R P_w + t`, `P_w = Rᵀ(P_c − t)`를 구현했다. 오른쪽 +X, 아래쪽 +Y, 앞쪽 +Z를 사용하며, Ray 거리와 Z 깊이를 구분했다. 합성 회전·이동 카메라와 알려진 평면의 왕복 변환을 1e-10 기준으로 검사했다. 회전 방향을 의도적으로 바꾼 대조군은 최대 73.4184px 오차로 검출됐고, 0.5 픽셀을 임의로 더한 대조군도 검출했다. 음수 깊이·화면 밖·합성 패딩 마스크 제외 검사가 통과했다.

원본 RGB의 Resize 샘플 위치는 `((u+0.5)×640/512−0.5, (v+0.5)×480/384−0.5)`로 기록한다. 이는 공식 카메라의 정수 픽셀 규약과 구별한다. 일반적인 centre-based Resize의 Intrinsics affine 변환도 독립 검사했다. 이를 이유로 모델이 출력한 K의 주점을 임의 보정하지 않았다.

## 실제 3장 자기 시점 재투영

공식 함수 AST만 추출해 동일 입력으로 실행한 결과, 로컬 역투영과 최대 좌표 차이는 **0**이었다. 회전행렬 직교성의 최대 오차는 `7.0155235e-08`였다. 실제 자기 시점 재투영 허용오차는 실행 전에 **0.001px**로 고정했다.

| Frame | 오차 중앙값 (px) | P95 (px) | 최대 (px) |
| --- | ---: | ---: | ---: |
| 0 | 7.919098e-06 | 1.4338286e-05 | 1.557862e-05 |
| 1 | 1.5491486e-05 | 2.4613954e-05 | 2.6395548e-05 |
| 2 | 2.1849324e-05 | 3.6991712e-05 | 4.4996007e-05 |

모두 기준을 통과했다. 원본 float32 카메라 회전의 수치 오차가 남으며, 이 왕복 검사는 좌표 변환 일관성에 대한 근거다. 모델이 실제 장면의 깊이를 정확히 예측했다는 증거는 아니다.

## 타 시점 투영·깊이 진단

양수 카메라 깊이와 `[0,W−1]×[0,H−1]` 범위를 검사하고 가장 가까운 정수 픽셀에서 대상 예측 깊이를 샘플링했다. 소스 점들의 z-buffer 최소 깊이에서 1% 이내인 후보를 별도로 집계했다. 다음 상대 잔차·5% 동의율은 **모든 in-frustum 후보**에서 산출한 값이며 front 후보만의 지표가 아니다. 가림·가장자리·관측 가능성의 영향이 포함된다.

| Source→Target | 화면 내 양수 깊이 후보 | 소스 z-buffer front 후보 | 상대 깊이 잔차 중앙값 | 상대 잔차 ≤5% |
| --- | ---: | ---: | ---: | ---: |
| 0→1 | 125,730 | 121,937 | 0.010891 | 92.04% |
| 0→2 | 58,980 | 57,308 | 0.011614 | 78.43% |
| 1→0 | 113,654 | 112,455 | 0.010980 | 94.15% |
| 1→2 | 121,509 | 119,646 | 0.015782 | 93.15% |
| 2→0 | 54,521 | 53,824 | 0.011257 | 78.85% |
| 2→1 | 121,239 | 119,298 | 0.013146 | 93.38% |

한 source당 전체 점은 196,608개다. 이 수치들은 예측 간 진단이며 GT 정확도·확정된 대응점·융합 성공을 의미하지 않는다. Frame 0↔2는 0↔1, 1↔2보다 화면 내 겹침이 적다. 후속 융합에서는 이 조건과 가림·깊이 경계를 별도로 처리해야 한다.

## GT Depth와 전처리 RGB 격자 검사

[TUM 공식 형식 설명](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats)에 따라 제공 Depth는 RGB 격자에 등록된 자료로 취급하고, PNG/5000을 미터로 변환하며 0은 무효 처리했다. 추가 Depth 보정이나 재등록은 적용하지 않았다. RGB별 가장 가까운 Depth를 20ms 이내에서 연계하고, 평가용 GT만 nearest로 같은 512×384 격자에 옮겼다. Centre mapping으로 직접 구한 인덱스와 PIL 결과의 정확한 일치를 확인했다.

| Frame | Depth timestamp | 시간 차이 (ms) | 유효 GT 비율 |
| --- | --- | ---: | ---: |
| 0 | 1305031453.805041 | 13.325 | 81.54% |
| 1 | 1305031454.141030 | 13.329 | 73.31% |
| 2 | 1305031454.470741 | 10.828 | 73.15% |

원본 RGB 파일 해시와 P0 저장 RGB의 BICUBIC 재생성 일치, 저장 관측의 frame/pixel→색상·깊이 일치를 추가 확인했다. GT 검사 범위는 시간 연계·제공 등록 규약·격자 변환·유효 마스크다. 센서 보정 정확도를 재검증하거나 영상 내용만으로 물리적 등록을 증명하지 않았으며 10.8~13.3ms 시간차의 영향은 남는다. 모델 기하는 임의 스케일이고 GT와의 공통 정렬 프로토콜도 아직 없으므로 GT Depth RMSE는 계산하지 않았다.

## 산출물과 보존

루트: `results/pointmap_refinement/tum-freiburg1_desk-P1-20261112-001/stages/P1/`.

- `artifacts/geometry/observations.npz`: world_xyz_initial, frame_id, pixel_uv, original_rgb_sample_uv, depth_initial, depth_conf_raw, RGB.
- `artifacts/geometry/observations.ply`: RGB와 frame_id/u/v를 포함한 binary little-endian 점군. 융합되지 않은 원본 관측이며 좌표 단위는 모델 스케일이다.
- `artifacts/geometry/frames.json`: 원본 프레임·타임스탬프·해시 연결.
- `artifacts/gt/`: 추출한 GT PNG와 같은 격자로 변환한 평가 전용 깊이·마스크.
- `evaluation/metrics.json`, `artifact_validation.json`: 전체 수치와 검증 상태.
- `artifacts/source/`, `config_resolved.json`, `environment.json`, `manifest.json`, `logs/`: 소스·설정·환경·실행 로그·SHA-256.

총 **589,824점**, 무효 관측 **0점**이다. NPZ·PLY를 다시 읽어 저장 전 배열과 정확히 일치함을 확인했고, frame/pixel ID의 유일성과 XYZ 유한값을 검사했다. 원본 데이터·모델·부모 실행은 변경하지 않았다. 이 파일은 P1 계약 검사용 원본 점군이며 E0 비교 실험 완료로 처리하지 않는다.

다음 작업은 E0의 정식 원본 점군 기준선 정리와 P2 Renderer·Gradient 검증이다. P1은 위치 최적화나 실제 기하 정확도 향상을 주장하지 않는다.
