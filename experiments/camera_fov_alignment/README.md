# Camera FoV Alignment — C0~C5와 보조 검증

원본 Depth·카메라 중심/회전·RGB를 고정한다. 역초점거리 배율로 FoV를 바꾸고 점을 재생성한다. 고정 영상 대응의 3D 차이를 fit하며, 최종 점군의 압축은 별도 색+깊이 융합으로 평가한다.

[계획서](../../docs/vggt_omega_fov_pointmap_alignment_experiment_plan.md), [실행 현황](../../docs/experiments/camera_fov_alignment/index.md), [보조 검증·amendment](../../docs/experiments/camera_fov_alignment/amendments.md)를 함께 읽는다. 원본 계획의 실패·지원 부족과 탐색적 보완을 구분한다.

## 재실행

저장소 루트에서 기존 `.venvs/p0-py311`을 사용한다. NumPy 1.26.4, OpenCV 4.11.0에서 실행했으며 SciPy·GPU·새 모델 추론은 필요하지 않다. CPU 실행의 기본 명령은 다음과 같다.

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/camera_fov_alignment/C0/run.py
```

각 코드 디렉터리의 `run.py`를 같은 방식으로 호출한다. 실제 단계 순서는 다음과 같다.

| 코드 | 추가 인수 | 역할 |
| --- | --- | --- |
| C0, C0a, C0b | 없음 | 수식·solver·검색·관측성 검증 |
| C1, C1a | 없음 | 실내 기준선 및 대체 특징의 지원 검사 |
| C2, C3 | 없음 | 원래 지원 조건을 유지한 실내 평가 |
| C2a, C3a | 없음 | 원래 sparse 대응의 저지원 수치 진단 |
| C4 | `--dataset hkairport01` 또는 `--dataset amtown01` | 원래 SIFT 절차의 드론 비교 |
| C4a | 같은 `--dataset` | 고정 선분 17개 후보의 탐색적 비교 |
| C5a | 없음 | 깊이 gate 제어와 E0c 완전 재현 |
| C5 | `--dataset tum-freiburg1_desk`, `hkairport01`, `amtown01` | 원래 C3/C4 선택값의 융합 |
| C5b | `--dataset hkairport01` 또는 `amtown01` | C4a 선택값의 보조 융합 |
| C5c | 없음 | 전체 manifest·파라미터·관측 매핑 종합 검증 |

실행마다 날짜·회차를 포함하는 새 Run ID가 만들어진다. 결과를 덮어쓰지 않는다. 후속 단계는 해당 코드/데이터의 최신 **완료** 실행을 읽고 parent manifest를 고정하므로, 다른 순서로 재실행하면 그 parent를 확인한다. 실패 실행은 자동으로 성공 실행으로 바뀌지 않는다.

## 입력·저장

입력은 기존 E0/E0d의 `vggt_omega_raw.npz`, `observations.npz`, `frames.json`이며 SHA-256을 확인한다. 세 RGB가 공동 추론된 원본이다. FoV 보정 전에 융합된 점군을 사용하지 않는다. 데이터 경로·해시는 `common.py`와 각 Run의 config/input record에 있다.

- `results/camera_fov_alignment/{run}/stages/{code}/`: source snapshot, config, 로그, 전체 NPZ/PLY/투영 버퍼, 검증, manifest.
- `docs/experiments/camera_fov_alignment/{code}/{run}/`: 한국어 보고서·그림·수치 JSON·실행 환경·manifest.
- 대형 자료는 기존 `.gitignore` 규칙대로 results에 로컬 보관한다. GitHub에는 코드·보고서·그림·수치·해시를 푸시한다.

source snapshot은 실행 당시 파일을 보존한다. 해당 코드를 재사용하려면 저장소 루트의 같은 상대 위치로 복원해 실행한다. snapshot 디렉터리에서 직접 실행하면 루트 경로 계산이 달라지므로 그대로 실행하지 않는다. 체크포인트나 raw 데이터가 GitHub 보고서에 포함됐다고 가정하지 않는다.

## 해석

FoV fit의 선택은 fit 손실·고정 coverage로만 한다. validation/GT로 checkpoint·threshold를 고르지 않는다. C4a는 원래 결과를 확인한 뒤 추가한 탐색적 amendment다. GT 정확도·새 카메라 일반화·연속 SLAM은 이번 단계의 검증 대상에 포함하지 않았다.

C5의 색은 실제 원본 RGB 조건이며 프레임 팔레트가 아니다. 깊이 평균은 현재 대표점당 가중치 1이고 그룹 관측 수 가중 평균과 다르다. 원본 관측 전체의 RGB와 Z 범위를 확인해 연쇄 융합을 막으며 모든 관측 ID를 보존한다. 대표점 수 감소·전체 자료 크기 감소·SLAM 성능 향상은 별개의 결과다.
