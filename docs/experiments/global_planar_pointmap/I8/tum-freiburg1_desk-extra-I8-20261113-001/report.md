# I8 pointmap·plane bundle

initial/proposed/retained 각각에 pointmap·확장 PLY 세 종류·CSR tag·소속·plane 정의·지원·버전·유한 경계·교선과 관측 interval을 저장했다. 관측된 per-view rings/holes/분리 성분을 유지하며 convex hull로 미관측 영역을 메우지 않는다. plane-local 경계 round-trip과 상호 state/hash를 검증했다. PLY 추가 속성의 binary 재읽기도 통과했다.

경계는 영상 border·인접 채택 면·원본 depth 가림 증거로 provisional 분류하며 미확정 상태를 보존한다. 실제 mesh와 watertight 보장은 이번 범위에 포함하지 않는다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-extra-I8-20261113-001/stages/I8`. GT_NOT_EVALUATED.
