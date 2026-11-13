# I6 전역 plane·소속 최적화

모든 plane 계수를 하나의 sparse least-squares 문제로 함께 갱신하고 지역 소속 제안을 같은 목적함수로 수용했다. 원본 FoV fit·고정 RGB 대응을 계속 사용하며 보정된 점에 plane을 다시 맞추지 않았다. 목적함수 비증가를 검사했다.

merge/split/revert 제안은 같은 목적함수로 평가하고 신규 ID를 할당하며 이전 ID를 재사용하지 않는다. 관측/변수 역순과 별도 초기값을 반복하고 label permutation 보정 후 안정성을 기록했다. 고정 RGB 대응 재투영과 후보 인접 경계에서 plane 교선의 영상 잔차를 사용하며 관계도 동일 목적함수로 반복 재선택한다. 표면 GT가 없는 국소 최적화이며 전역 최적해나 실제 소속 정확도를 보장하지 않는다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-I6b-20261113-002/stages/I6b`. GT_NOT_EVALUATED.
