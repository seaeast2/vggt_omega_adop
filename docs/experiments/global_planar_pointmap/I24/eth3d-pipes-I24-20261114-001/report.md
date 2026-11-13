# I24 — eth3d-pipes 블러 원인 분리 최적화

6조건의 geometry×correspondence 2×2 FoV 및 native 제어군을 실행했다. 기존 mask·plane·support를 고정한 split-safe RGB 평면 진단도 실행했다. GT는 사용하지 않았다.

F00은 bilinear footprint까지 동결 FIT 구역 안인 clean 대응으로 재계산했다. 이전 I2 beta 차이는 JSON에 기록했다. 지원/rank 부족은 beta1 fallback이며 성공으로 간주하지 않는다.

Stage: `results/global_planar_pointmap/eth3d-pipes-I24-20261114-001/stages/I24`. GT_NOT_EVALUATED.
