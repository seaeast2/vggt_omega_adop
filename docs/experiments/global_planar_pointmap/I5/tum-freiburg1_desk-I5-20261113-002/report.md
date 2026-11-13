# I5 자동 구조 관계

원본 depth plane과 RGB line의 두 소실방향에서 얻은 별도 방향 증거가 함께 맞는 경우에만 soft 관계를 활성화했다. 증거가 부족하면 uncertain/free를 유지하며 사용자가 지정한 벽·90도 prior는 없다. training의 방향 likelihood와 자유도 비용으로 자유/평행/수직 모델을 직접 비교했다. 영상/원본 depth의 독립 증거가 없으면 제약을 비활성화한다. line family 추정의 불확실성을 완전히 적분한 확률 모델은 아니다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-I5-20261113-002/stages/I5`. GT_NOT_EVALUATED.
