# Pointmap Refinement 실험 현황

계획은 [실험 계획서](../../vggt_omega_pointmap_refinement_experiment_plan.md)를 따른다. 실행 완료와 연구 결과의 성공은 별도로 판단한다.

**현재 상태:** 사용자 요청으로 카메라 고정·개별 정점 RGB 이동 방법은 E3e까지 종료했다. 기존 결과를 보존하고 미착수 E4~E9는 실행하지 않는다. 후속 FoV 보정·원본 Depth 재역투영과 색+깊이 융합은 [별도 계획서](../../vggt_omega_fov_pointmap_alignment_experiment_plan.md)의 C0~C5와 보조 검증까지 실행·평가했다. [C 계열 현황](../camera_fov_alignment/index.md) 및 [종합 결과](../camera_fov_alignment/summary.md)에 실제 효과·지원 부족·미충족 기준을 구분했다.

| 코드 | 목적 | 실행 상태 | 실행 및 보고서 |
| --- | --- | --- | --- |
| P0 | 호스트 환경·입력·최소 추론 검증 | 완료: 7회 추론·재현성 검증 통과 | [smoke-P0-20261112-003](P0/smoke-P0-20261112-003/report.md), [전체 이력](P0/README.md) |
| P1 | 좌표계·역투영 검증 | 완료: 좌표·GT 격자·관측 출처 검사 통과 | [보고서](P1/tum-freiburg1_desk-P1-20261112-001/report.md) |
| P2 | Renderer·Gradient 검증 | 완료: 최소 렌더·안정 영역 Gradient 통과, 가림 경계 제한 기록 | [보고서](P2/tum-freiburg1_desk-P2-20261112-002/report.md), [실행 이력](P2/README.md) |
| P2a | PyTorch3D 설치·렌더러 비교 | 완료: CUDA 설치·3방식 비교. 기본 Alpha 기하 회복 실패 및 경계 제한 포함 | [보고서](P2a/tum-freiburg1_desk-P2a-20261112-001/report.md) |
| P2b | E0b 초기 렌더 검은 테두리·alpha 진단 | 완료: 동일 버퍼의 alpha 곱 제거로 검은 띠 감소. 가림/미분 수정·재학습은 미실행 | [보고서](P2b/tum-freiburg1_desk-P2b-20261112-001/report.md), [비교 그림](P2b/tum-freiburg1_desk-P2b-20261112-001/figures/comparison.png) |
| P2c | 색 합성·compact 지지·연속 가림과 미분 검증 | 완료: compact_soft 합성·실제 미분/10회 감소 통과, E3b 재실행 허용. 실제 GT 미평가 | [보고서](P2c/tum-freiburg1_desk-P2c-20261112-001/report.md), [초기 렌더 비교](P2c/tum-freiburg1_desk-P2c-20261112-001/figures/initial_ablation.png) |
| E0 | 보정 전 원본 점군 기준선 | 완료: 589,824점 보존·검증 및 시각화 | [보고서](E0/tum-freiburg1_desk-E0-20261112-001/report.md) |
| E0a | 원본 점군의 프레임별 색상·카메라 투영 | 완료: 빨강/초록/파랑 PLY·3개 카메라의 전체/타 출처/단독 출처 투영·버퍼 검증 | [보고서](E0a/tum-freiburg1_desk-E0a-20261112-001/report.md), [전체 패널](E0a/tum-freiburg1_desk-E0a-20261112-001/figures/overview.png) |
| E0b | 다음 카메라 픽셀의 깊이 평균·이전 점 치환 | 완료: 341,325점, 순차 평균·삭제·출처 추적 검증. GT 정확도 미평가 | [보고서](E0b/tum-freiburg1_desk-E0b-20261112-001/report.md), [전후 패널](E0b/tum-freiburg1_desk-E0b-20261112-001/figures/comparison.png) |
| E0c | E0b에 원본 RGB 유사도 조건 추가 | 완료: 419,864점·색 범위 ≤30 검증. E0b 대비 coverage 증가·GT 공통 오차 증가 | [보고서](E0c/tum-freiburg1_desk-E0c-20261112-001/report.md), [RGB 비교](E0c/tum-freiburg1_desk-E0c-20261112-001/figures/median_rgb_comparison.png) |
| E1 | 단순 연결 F0 평가 | 완료: 예측 불일치·층 퍼짐·잠재 중복·출처별 RGB 진단 | [보고서](E1/tum-freiburg1_desk-E1-20261112-001/report.md) |
| E2 | 공유점 융합·가시성 평가 | 완료: 510,427점 F1 생성·검증. RGB 소폭 저하·기하 개선 미확인 | [보고서](E2/tum-freiburg1_desk-E2-20261112-001/report.md) |
| E3 | Photo Ray-depth 위치 최적화 | 실행·평가 완료, 효과 실패: selected=초기 0회, last 악화 | [보고서](E3/tum-freiburg1_desk-E3-20261112-001/report.md) |
| E3b | E0b 초기값의 Photo Ray-depth 최적화 | 완료: 200회 실제 이동, 손실 악화·selected=초기, 효과 실패 | [보고서](E3b/tum-freiburg1_desk-E3b-20261112-002/report.md), [RGB 전후](E3b/tum-freiburg1_desk-E3b-20261112-002/figures/rgb_comparison.png) |
| E3c | E0c 색 조건 융합 초기값의 RGB 미분 정점 이동 | 완료: 양쪽 200회·E0c 106,464점 이동, RGB −2.333%·GT 깊이 악화 | [보고서](E3c/tum-freiburg1_desk-E3c-20261112-001/report.md), [RGB 전후](E3c/tum-freiburg1_desk-E3c-20261112-001/arms/treatment_E0c/figures/rgb_comparison.png) |
| E3d | ADOP 방식 1픽셀·깊이 제한·근사 위치 기울기 | 완료: selected=초기, last 78,434점 이동·RGB/GT 악화. 실내 튜닝 중단 | [보고서](E3d/tum-freiburg1_desk-E3d-20261112-001/report.md), [원본 해상도 전후](E3d/tum-freiburg1_desk-E3d-20261112-001/figures/rgb_native_comparison.png) |
| E0d | 드론 공동 추론·색 조건 융합 | 완료: HKairport01 285,825점 / AMtown01 340,732점, raw/색 조건/CSR 검증 | [실행 이력·보고서](E0d/README.md) |
| E3e | 드론 초기값의 최소 ADOP 방식 정점 이동 | 완료: 두 장면 각 200회, selected=초기·last RGB/coverage 악화. 기하 정확도 미평가 | [비교·보고서](E3e/README.md) |
| E4~E9 | 위치 최적화·제약·선택 비교 | 사용자 요청으로 미실행·종료 | — |
