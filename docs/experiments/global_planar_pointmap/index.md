# 화면 전체 자동 평면 정렬·Pointmap 실험

> 상태: **계획 작성 완료 · 전 단계 미실행**

[전체 실험 계획](../../vggt_omega_global_planar_pointmap_experiment_plan.md) · [앞선 H 계열 결과](../c3a_plane_refinement/summary.md)

원본 이미지 → VGGT-Ω raw pointmap → SAM 전체 영상 분할·관측 tag → FoV 최적화 → 평면 후보 분리 → 전역 plane 연결 → 구조 관계 추론 → 소속/평면 공동 최적화 → 전체 재투영 → pointmap/plane registry 보존 순서다.

| 코드 | 목적 | 상태 |
| --- | --- | --- |
| I0 | 데이터·좌표·tag·평가 split·합성·objective 계약 | 계획 |
| I1 | 전체 영상 SAM 분할·tag·중첩 계층 | 계획 |
| I2 | FoV 최적화·tag 유지 | 계획 |
| I3 | 여러 대상의 평면 후보 분리·평면성 판단 | 계획 |
| I4 | 모든 frame의 전역 plane ID·관측 소속 연결 | 계획 |
| I5 | 평행·수직·인접 관계 자동 추론 | 계획 |
| I6 | 전역 소속/평면 공동 최적화 | 계획 |
| I7 | 전체 frame·확정 소속 무제한 hard 재투영 | 계획 |
| I8 | 점군/plane 계수·경계·관계·이력 bundle 및 round-trip | 계획 |
| I9 | 전체 화면·추가 실내·지표/육안·비용 종합 평가 | 계획 |

첫 실행 단계는 I0다. 현재 코드 구현·설치·모델 추론·새 PLY 생성은 수행하지 않았다. 보조 검증은 I1a 등으로 구분하고 기존 H 및 실패 결과를 덮어쓰지 않는다.

평면·관측 소속·유한 경계·교선·인접 관계는 후속 폴리곤 재구성을 위해 보존한다. plane 후보가 병합/분할/탈락해도 이전 ID와 version을 삭제하지 않는다. 실제 mesh 생성은 이번 범위에 포함하지 않는다.
