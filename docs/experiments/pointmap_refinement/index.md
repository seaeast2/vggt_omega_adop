# Pointmap Refinement 실험 현황

계획은 [실험 계획서](../../vggt_omega_pointmap_refinement_experiment_plan.md)를 따른다. 실행 완료와 연구 결과의 성공은 별도로 판단한다.

| 코드 | 목적 | 실행 상태 | 실행 및 보고서 |
| --- | --- | --- | --- |
| P0 | 호스트 환경·입력·최소 추론 검증 | 완료: 7회 추론·재현성 검증 통과 | [smoke-P0-20261112-003](P0/smoke-P0-20261112-003/report.md), [전체 이력](P0/README.md) |
| P1 | 좌표계·역투영 검증 | 완료: 좌표·GT 격자·관측 출처 검사 통과 | [보고서](P1/tum-freiburg1_desk-P1-20261112-001/report.md) |
| P2 | Renderer·Gradient 검증 | 완료: 최소 렌더·안정 영역 Gradient 통과, 가림 경계 제한 기록 | [보고서](P2/tum-freiburg1_desk-P2-20261112-002/report.md), [실행 이력](P2/README.md) |
| P2a | PyTorch3D 설치·렌더러 비교 | 완료: CUDA 설치·3방식 비교. 기본 Alpha 기하 회복 실패 및 경계 제한 포함 | [보고서](P2a/tum-freiburg1_desk-P2a-20261112-001/report.md) |
| E0 | 보정 전 원본 점군 기준선 | 완료: 589,824점 보존·검증 및 시각화 | [보고서](E0/tum-freiburg1_desk-E0-20261112-001/report.md) |
| E1 | 단순 연결 F0 평가 | 완료: 예측 불일치·층 퍼짐·잠재 중복·출처별 RGB 진단 | [보고서](E1/tum-freiburg1_desk-E1-20261112-001/report.md) |
| E2 | 공유점 융합·가시성 평가 | 미착수 | — |
| E3~E9 | 위치 최적화·제약·선택 비교 | 미착수 | — |
