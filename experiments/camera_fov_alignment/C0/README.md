# C0 — 역투영·affine 식·bounded solver 제어

CPU float64로 실제 raw 역투영 불변성, 합성 정답 복구, QR 기반 active-bound 열거 solver와 robust IRLS를 검증한다. GT나 실제 영상의 validation으로 계수를 선택하지 않는다.

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p0-py311/bin/python experiments/camera_fov_alignment/C0/run.py
```

실행마다 새 Run ID를 자동 생성한다. 실패도 보존한다. 공통 코드는 각 실행 Stage에 스냅샷으로 보관한다.
