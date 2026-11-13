# Global planar pointmap I series

계획: [I0–I9](../../docs/vggt_omega_global_planar_pointmap_experiment_plan.md).

Python 환경은 `.venvs/p2a/bin/python`이다. 모든 geometry는 float64 Omega world/model units다.
기존 실험과 실패 run은 덮어쓰지 않으며 매 실행은 새 sequence를 할당한다.

```bash
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/prepare.py
# 다음 GPU 명령은 반드시 승인된 호스트 실행에서 수행한다.
I_HOST_GPU=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/segment.py
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/solve.py I2
# I3, I4, I5, I6 순서로 같은 CLI 사용
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/export.py I7
# I8, I9 순서로 같은 CLI 사용
```

추가 실내에는 `--dataset tum-freiburg1_desk-extra`를 사용한다. I0는 두 구간을 함께 동결하고 I1도 두 구간에서 모델을 순차 실행한다.
I2는 기존 C3a 역사적 재현과 누출 제거 split의 주 solve를 구분한다. split 변경·최적화의 구체적 식은 각 run의 source/config에 보존한다.
`manifest.status=completed`는 실행 종료이며 `completion_criteria_met` 및 scientific decision을 별도로 읽어야 한다.
소속/표면 GT는 없으며 `GT_NOT_EVALUATED`를 유지한다.

대형 NPZ/PLY/mask는 results에 남기고 manifest의 SHA256/크기/경로만 Git에 저장한다.
`publish.py`는 계획에서 허가한 단계별 커밋·푸시에만 사용하며 기존 사용자 변경을 staging하지 않는다.
