# C0a 최근접점 검색 보조 검증

**TECHNICAL_PASS**. C0 최초 실패를 보존하고 원인을 확인했다.

- seed 0, KD-tree 1개, checks=-1에서 exhaustive 정답과 다른 이웃: 1/40.
- 정확한 float32 L2 brute-force 방식으로 대체하고 NumPy 전체 거리 대조 통과.
- 조밀 점군 보조 지표는 프레임별 고정 512개 query와 상대 프레임 전체 target을 사용한다. 전체 source 점의 통계로 부르지 않는다.
- FoV fit은 고정 대응의 float64 affine residual이며 이 검색 방식의 영향을 받지 않는다.


실행 Stage: `results/camera_fov_alignment/synthetic-C0a-20261112-001/stages/C0a`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
