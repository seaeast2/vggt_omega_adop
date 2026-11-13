# 점·선·깊이 제약 실험 실행 현황

2026-11-13. **G0~G6 및 G0a/G0b/G5a 실행 완료. 효과 판정은 탐색적/미확인.**

[실험 계획](../../vggt_omega_point_line_depth_refinement_experiment_plan.md) · [종합 보고서](summary.md)

| 코드 | 실행 | 판정·보고서 |
| --- | --- | --- |
| G0 | `tum-freiburg1_desk-G0-20261113-001` | [TECHNICAL_CHECKS_PASSED](G0/tum-freiburg1_desk-G0-20261113-001/report.md) |
| G0a | `tum-freiburg1_desk-G0a-20261113-001` | [TECHNICAL_CHECKS_PASSED](G0a/tum-freiburg1_desk-G0a-20261113-001/report.md) |
| G0b | `tum-freiburg1_desk-G0b-20261113-001` | [ARTIFACT_AND_OBJECTIVE_AUDIT_PASSED](G0b/tum-freiburg1_desk-G0b-20261113-001/report.md) |
| G1 | `tum-freiburg1_desk-G1-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G1/tum-freiburg1_desk-G1-20261113-001/report.md) |
| G2 | `tum-freiburg1_desk-G2-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G2/tum-freiburg1_desk-G2-20261113-001/report.md) |
| G3 | `tum-freiburg1_desk-G3-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G3/tum-freiburg1_desk-G3-20261113-001/report.md) |
| G4 | `tum-freiburg1_desk-G4-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G4/tum-freiburg1_desk-G4-20261113-001/report.md) |
| G5 | `tum-freiburg1_desk-G5-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G5/tum-freiburg1_desk-G5-20261113-001/report.md) |
| G5a | `tum-freiburg1_desk-G5a-20261113-001` | [LOW_SUPPORT_DIAGNOSTIC_ONLY](G5a/tum-freiburg1_desk-G5a-20261113-001/report.md) |
| G6 | `tum-freiburg1_desk-G6-20261113-001` | [COMPLETED_EFFECT_NOT_ESTABLISHED](G6/tum-freiburg1_desk-G6-20261113-001/report.md) |

주 입력 30/40/50과 추가 실내 100/110/120에서 총 18개 주 최적화 비교군, 20개 초기값·민감도 비교를 실행했다. 주 비교군은 RGB/출처색 PLY와 initial/proposed/selected/last를 보존했다. G4는 실제 공식 MoGe-2 추론 결과를 사용했다.

PLY 빠른 비교 경로: `results/point_line_depth_refinement/ply_review/`

G0a는 numerical Jacobian 검증 보조 실행이다. G5a는 사전 지정한 추가 실내 구간이다. GT·pose 공동 최적화·융합·연속 SLAM은 미평가다.
