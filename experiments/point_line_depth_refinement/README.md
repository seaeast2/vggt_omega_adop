# 실행 방법과 산출물

계획: [실험 계획](../../docs/vggt_omega_point_line_depth_refinement_experiment_plan.md)

CPU: `.venvs/p2a/bin/python experiments/point_line_depth_refinement/run.py G0` 및 G1/G2/G3.
보조: `controls.py`(G0a), `audit.py`(G0b).
MoGe-2 prior 추론: `external_depth.py`를 호스트 GPU에서 실행한 뒤 `followup.py G4`.
안정성: `followup.py G5`.
새 실내 입력: `extra_indoor.py`를 호스트 GPU에서 실행한 뒤 `additional_window.py`(G5a).
종합: `summarize.py`(G6), `finalize.py`(문서·provenance).

`external_depth.py`와 `extra_indoor.py`의 보조 자료 경로는 고정되어 있으므로 재추론 시 기존 출력의 덮어쓰기 대신 새 run 경로로 분리해야 한다. 주 Stage 실행은 새 sequence를 부여한다. 원래 G1 annotation을 변경하려면 새로운 G1a 등으로 구분한다.

18개 주 최적화 비교군과 20개 초기값·민감도 비교를 실행했다. 각 단계의 실행 시작 시점 소스·설정 snapshot과 원본 산출물 hash를 보존했다. `requirements.lock.txt`는 실행 후 실제 환경이다.

PLY는 `results/point_line_depth_refinement/ply_review/`에서 바로 열 수 있다. 빠른 경로는 상대 symlink이고 실제 파일은 실험별 디렉토리에 보존되어 있다. `pixel_rgb`는 원본 관측 픽셀색, `frame_colors`는 프레임 출처색이다. `proposed`는 실제 solver 제안이며 `selected`와 다를 수 있다.

G0b에서 P 손실 구현 일치, 원본 manifest hash, pointmap ID·색상 보존을 검사했다. GT 정확도·SLAM·융합 결과가 아니다. 연구 판정은 [종합 보고서](../../docs/experiments/point_line_depth_refinement/summary.md)를 따른다.
