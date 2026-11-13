# I15 — eth3d-pipes Omega 공동 추론

호스트 CUDA에서 기존 checkpoint와 512 max_size를 사용해 3장 한 번 공동 추론했다. processed shape=[3, 336, 512, 3]. 레이저 GT·공식 카메라 pose를 모델 입력으로 사용하지 않았다.

Stage: `results/global_planar_pointmap/eth3d-pipes-I15-20261114-001/stages/I15`. GT_NOT_EVALUATED.
