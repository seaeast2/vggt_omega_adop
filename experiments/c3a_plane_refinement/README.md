# C3a 고정 카메라 평면 실험

계획: [H0–H6](../../docs/c3a_planargs_plane_refinement_experiment_plan.md).

실행 환경은 `.venvs/p2a/bin/python`, CPU는 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. H1 CUDA는 호스트에서 실행한다. 독립 스테이지 진입점은 각 H 디렉토리의 run.py다. 자동 검출 결과와 실제 보정 결과를 보고 임계값을 바꾸지 않는다.


H0~H6 실행 완료. 실패·보완 전 결과를 유지하고 최종 기본 군은 H2c/H3c/H4c/H5c, 중복 마스크 정리 보조 군은 H2d/H3d/H4d/H5d를 사용한다. H6a는 E0 참고 수치와 고정 축 확대 표시만 추가한다.

기존 E0/C1/C3a/G1 결과와 모델이 준비된 환경에서 전체 이력을 다시 실행하려면 다음 순서를 쓴다. 각 진입점은 새 seq로 저장하며 기존 결과를 덮어쓰지 않는다. H0 진입점은 합성 제어를 수정한 H0a를 실행한다. H1은 반드시 호스트 GPU에서 실행한다.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venvs/p2a/bin/python experiments/c3a_plane_refinement/H0/run.py
# 호스트 GPU에서 실행
.venvs/p2a/bin/python experiments/c3a_plane_refinement/H1/run.py
for code in H2 H3 H4 H5 H2b H3b H4b H5b H2c H3c H4c H5c H2d H3d H4d H5d H6 H6a; do
  .venvs/p2a/bin/python experiments/c3a_plane_refinement/$code/run.py || break
done
```

[종합 결과](../../docs/experiments/c3a_plane_refinement/summary.md). PLY는 `results/c3a_plane_refinement/ply_review/`에 색상별 symlink로 제공한다. checkpoint·raw 결과는 Git에 포함하지 않는다.


후속 H4e는 기존 H4d A4 평면을 고정한 전체 프레임 재소속과 점 법선/이동 제한 완화 12군이다. [사전 설정](H4e/plan.md). 실행: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venvs/p2a/bin/python experiments/c3a_plane_refinement/H4e/run.py`. GPU 재추론은 없다. 기존 기본값 2%는 유지하고 새 한도는 각 군의 인자로만 전달한다.


H4f는 H1 SAM 전체 마스크를 기반으로 이동 상한·법선·confidence·경계·참조 깊이 gate를 제거하는 6군이다. [사전 설정](H4f/plan.md). 실행: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venvs/p2a/bin/python experiments/c3a_plane_refinement/H4f/run.py`. uncapped는 `max_relative_move=None`이며 양의 유한 교차와 수치 평행 방지 `minimum_ray_cosine=1e-8`만 유지한다. 기존 실험 기본값 2%/cos0.2는 유지한다.


H4g는 중첩 SAM mask의 서로 다른 두 벽을 분리한다. [사전 설정](H4g/plan.md). 실행: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venvs/p2a/bin/python experiments/c3a_plane_refinement/H4g/run.py`. H4f 재현/왼쪽 복원/자유 L/수직 L/수직 L 전파의 5군이다. 기존 오른쪽 plane·camera0/1 XYZ는 유지하고 사용자 수직 prior를 적용한 새 왼쪽 plane을 비교한다. PLY는 pixel_rgb/frame_colors 외 plane_colors도 제공한다.
