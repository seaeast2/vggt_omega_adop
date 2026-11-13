# I7 전체 frame 재투영

확정 소속 전체를 같은 world plane과 자기 픽셀 광선의 교차로 이동했다. 최대 이동 한도는 없으며 수치 평행·음의 깊이·비유한 교차만 거절한다. plane 식·자기 투영·unit normal·unknown XYZ bitwise 보존을 검사하고 initial/proposed/retained PLY를 모두 생성했다. B1 기준 frustum loss가 0.5 percentage point를 넘으면 retained는 initial이다. proposed는 삭제하지 않는다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-I7-20261113-002/stages/I7`. GT_NOT_EVALUATED.
