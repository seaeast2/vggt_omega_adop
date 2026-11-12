# C0 수식·solver 검증

실행: `synthetic-C0-20261112-002`. **TECHNICAL_PASS**.

- 원본 역투영 최대 차이: 1.91e-07 모델 단위.
- 자기 재투영 최대 오차: 2.27e-13 pixel.
- 직접 역투영↔affine 최대 차이: 8.88e-16.
- ±5%/±10% 합성 초점거리 교란 4조건의 6변수 복구·rank·KKT 검사 통과. 10%는 경계 정답 제어다.
- 고정 오매칭 5%·잡음이 있는 IRLS 제어: 수렴=True, 최대 β 오차=0.000129945.
- 1변수 독립 grid, 깊이축 무감각·반복 관측 rank 부족 제어, float32 nearest-neighbor backend의 brute-force 대조 통과.

실제 장면 FoV 보정 효과를 확인한 단계가 아니다. 대응 부족·순수 회전·평면 지원은 C1에서 실제 영상으로 추가 확인한다.


실행 Stage: `results/camera_fov_alignment/synthetic-C0-20261112-002/stages/C0`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
