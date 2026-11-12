# Camera FoV Alignment 실험 현황

[실험 계획서](../../vggt_omega_fov_pointmap_alignment_experiment_plan.md)를 따른다. 카메라 중심·회전·원본 Depth를 고정하고 FoV 보정 후 재역투영한 프레임 간 점 차이를 최소화한다.

C5에서는 고정된 보정값에서 원본 RGB 유사도·깊이 근접 조건으로 점 수를 줄인다. 실제 연속 SLAM 검증과 구분한다. [기존 Pointmap Refinement 이력](../pointmap_refinement/index.md)은 보존한다.

실행 완료와 과학적 효과는 각각 기록한다. 최신 상태는 아래 실제 manifest를 기준으로 한다.

| 코드 | 목적 | 실행 상태 |
| --- | --- | --- |
| C0 | 역투영·solver·합성 복구 검증 | 완료 1회 / 실패 기록 1회 |
| C0a | 최근접 검색 실패 진단·정확한 BF 방식 검증 | 완료 1회 / 실패 기록 0회 |
| C0b | 관측 퇴화·순수 회전·평면 합성 제어 | 완료 1회 / 실패 기록 0회 |
| C1 | 실내 raw 기준선·고정 대응·split·식별 가능성 | 완료 1회 / 실패 기록 0회 |
| C1a | 실내 ORB/AKAZE 대체 대응 지원 보조 검증 | 완료 1회 / 실패 기록 0회 |
| C2 | 공통 β 1개 보정 | 완료 1회 / 실패 기록 0회 |
| C2a | 원래 실내 sparse 대응의 저지원 공통 보정 진단 | 완료 1회 / 실패 기록 0회 |
| C3 | 프레임별 수평·수직 FoV 6개 보정 | 완료 1회 / 실패 기록 0회 |
| C3a | 원래 실내 sparse 대응의 저지원 6변수 진단 | 완료 1회 / 실패 기록 0회 |
| C4 | HKairport01·AMtown01 비교 | 미실행 |
| C5 | 색+깊이 융합·점 수 축소·표면 보존 | 미실행 |
| C5a | 융합 경계·연쇄 방지·기존 E0c 정확 재현 | 완료 1회 / 실패 기록 0회 |

| 실행 | 상태 | 판정·보고서 |
| --- | --- | --- |
| `synthetic-C0-20261112-001` | failed | [FAILED](C0/synthetic-C0-20261112-001/report.md) |
| `synthetic-C0-20261112-002` | completed | [TECHNICAL_PASS](C0/synthetic-C0-20261112-002/report.md) |
| `synthetic-C0a-20261112-001` | completed | [TECHNICAL_PASS](C0a/synthetic-C0a-20261112-001/report.md) |
| `synthetic-C0b-20261112-001` | completed | [TECHNICAL_PASS](C0b/synthetic-C0b-20261112-001/report.md) |
| `tum-freiburg1_desk-C1-20261112-001` | completed | [NOT_ENOUGH_SUPPORT](C1/tum-freiburg1_desk-C1-20261112-001/report.md) |
| `tum-freiburg1_desk-C1a-20261112-001` | completed | [NOT_ENOUGH_SUPPORT](C1a/tum-freiburg1_desk-C1a-20261112-001/report.md) |
| `tum-freiburg1_desk-C2-20261112-001` | completed | [NOT_ENOUGH_SUPPORT](C2/tum-freiburg1_desk-C2-20261112-001/report.md) |
| `tum-freiburg1_desk-C2a-20261112-001` | completed | [LOW_SUPPORT_DIAGNOSTIC_ONLY](C2a/tum-freiburg1_desk-C2a-20261112-001/report.md) |
| `tum-freiburg1_desk-C3-20261112-001` | completed | [NOT_ENOUGH_SUPPORT](C3/tum-freiburg1_desk-C3-20261112-001/report.md) |
| `tum-freiburg1_desk-C3a-20261112-001` | completed | [LOW_SUPPORT_DIAGNOSTIC_ONLY](C3a/tum-freiburg1_desk-C3a-20261112-001/report.md) |
| `synthetic-C5a-20261112-001` | completed | [TECHNICAL_PASS](C5a/synthetic-C5a-20261112-001/report.md) |

대형 NPZ/PLY와 source snapshot은 `results/camera_fov_alignment/`의 각 Run ID/Stage에 보관한다. 이 목록은 새 실행이 끝날 때 갱신한다.
