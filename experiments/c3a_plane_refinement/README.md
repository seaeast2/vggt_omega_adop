# C3a 고정 카메라 평면 실험

계획: [H0–H6](../../docs/c3a_planargs_plane_refinement_experiment_plan.md).

실행 환경은 `.venvs/p2a/bin/python`, CPU는 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. H1 CUDA는 호스트에서 실행한다. 독립 스테이지 진입점은 각 H 디렉토리의 run.py다. 자동 검출 결과와 실제 보정 결과를 보고 임계값을 바꾸지 않는다.
