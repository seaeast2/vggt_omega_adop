# P0 — 호스트 환경 및 VGGT-Ω 최소 추론 검증

목표는 원본 RGB 3장으로 카메라·깊이·신뢰도·전처리 RGB를 재현 가능하게 저장하는 것이다. 2/3/4장과 `max_size`/`balanced`를 비교하고, 추론 프로세스 종료 후 GPU 메모리를 확인한다. 기하 정확도 평가는 P0 범위에 포함하지 않는다.

## 고정 조건

- 공식 소스: <https://github.com/facebookresearch/vggt-omega>, Commit `48b23c8ce72c9a8fcf987f0d7f43d8e4870759f6`.
- 모델: `facebook/VGGT-Omega`의 `vggt_omega_1b_512.pt`. 공식 저장소 접근 승인과 CLI 인증이 필요하다.
- 입력: [공식 TUM RGB-D](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download)의 `freiburg1_desk`. `rgb.txt`의 유효 행을 0부터 세어 30/40/50/60번 RGB 원본을 선택한다. 처음 N장을 사용하며 GT는 읽지 않는다. 장면과 프레임 선택의 기하 적합성은 후속 단계에서 검증한다.
- Python 3.11.18 전용 환경: `.venvs/p0-py311/`. 시스템 Python 3.14는 공식 `numpy<2` 조건 때문에 사용하지 않는다.
- 설정: `configs/p0.json`. 의존성은 `requirements.lock.txt`에 기록한다.
- 호스트에서 실행한다. 샌드박스의 CUDA 출력으로 호스트 상태를 판단하지 않는다.

## 재현 절차

저장소 루트에서 실행한다. 아래 `<run_id>`와 `<trial_dir>`는 새 경로로 치환한다. 설정 사본과 `logs/`, `evaluation/`, `artifacts/data/`를 먼저 생성하며, 기존 실행을 덮어쓰지 않는다.

```bash
.venvs/p0/bin/uv pip sync --python .venvs/p0-py311/bin/python experiments/pointmap_refinement/P0/requirements.lock.txt
.venvs/p0/bin/uv pip install --python .venvs/p0-py311/bin/python --no-deps -e thirdparty/vggt-omega
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P0/scripts/preflight.py \
  --stage results/pointmap_refinement/<run_id>/stages/P0
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P0/scripts/prepare_inputs.py \
  --stage results/pointmap_refinement/<run_id>/stages/P0 \
  --archive data/pointmap_refinement/tum/rgbd_dataset_freiburg1_desk.tgz
```

`preflight.py`는 CUDA 계산 검사를 수행하고 환경 및 체크포인트 접근 상태를 JSON으로 저장한다. 모델 접근이 거절되면 종료 코드 2를 반환한다. 토큰 값은 기록하지 않는다. 인증은 호스트의 `.venvs/p0-py311/bin/hf auth login`으로 수행한다.

체크포인트 다운로드 시 Hugging Face revision과 파일 SHA-256을 실행 Manifest에 기록한다. 승인된 공식 가중치를 확보한 후 다음 명령을 별도 프로세스로 실행한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P0/scripts/infer.py \
  --checkpoint checkpoints/vggt_omega_1b_512.pt \
  --frames results/pointmap_refinement/<run_id>/stages/P0/artifacts/data/frames.json \
  --mode max_size --count 3 \
  --output results/pointmap_refinement/<run_id>/stages/P0/artifacts/inference/<trial_dir>
```

3장 `max_size`부터 실행하고, 2/4장 및 `balanced`로 확장한다. OOM이나 오류는 원래 로그와 함께 보존한다. `infer.py`는 기존 출력 폴더를 거절하고 모델의 기본 내부 autocast를 유지한다. PyTorch peak allocated/reserved와 Forward 시간, NPZ 재로딩 검사를 기록한다. 프로세스 종료 후 `nvidia-smi`를 기록하고, 3장 기준선을 새 프로세스에서 반복해 배열별 최대 차이와 허용오차를 보고한다.

## 실행 이력

실제 수행 여부와 수치는 [P0 보고서 목록](../../../docs/experiments/pointmap_refinement/P0/README.md)을 따른다. 실행 코드 작성과 모델 추론 완료는 구분한다.
