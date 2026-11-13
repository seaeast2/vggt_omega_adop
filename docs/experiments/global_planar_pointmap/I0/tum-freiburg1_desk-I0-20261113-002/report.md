# I0 입력·좌표·split 동결

기존 C3a의 같은 solver·fit split을 재실행하여 실제 proposed β/XYZ를 검증했다. 주/추가 실내 입력 hash와 고정 관측 ID를 동결했다.

계획 보완: 기존 C3a split 재현은 역사적 audit로 보존한다. 새 타일 보류 영역 및 알려진 전체 track의 3px 주변과 겹치는 fit 대응을 제거한 I2 주 solve를 별도 수행한다. 따라서 주 I2 β는 historical C3a와 다를 수 있다. 역사적 B1은 별도 비교로 남긴다. 이는 동일한 fit/validation 분리를 FoV와 plane에 적용하기 위한 변경이며 실제 validation 점수로 설정을 고르지 않는다.

합성 λ grid는 평면/곡면 제어를 통과한 후보 중 사전 기본값에 가장 가까운 조합을 선택했다. 나머지 λ와 scale은 사전 설정이며 최적값이라고 주장하지 않는다. 관계·순서·lineage 통합 제어는 해당 구현 단계에서 검사한다. 수동 평가 annotation은 없으므로 소속 정확도는 평가할 수 없다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-I0-20261113-002/stages/I0`. GT_NOT_EVALUATED.
