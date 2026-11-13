# I25a — tum-freiburg1_desk-extra 정렬 scale 사후 진단

이 진단은 블러 결과 확인 후 추가한 보조 분석이다. 모델 XYZ, 평가 mask, 전역 회전, 카메라 중심의 anchor를 고정하고 두 scale만 비교한다. 원래 지표/출력은 바꾸지 않는다.

카메라 baseline scale=1.1168058147, depth FIT scale=1.2031863643, 비율=0.928207.

| 출력 | pose-scale 3D mean(cm) | depth-scale 3D mean(cm) |
|---|---:|---:|
| omega_raw | 11.71566 | 6.22297 |
| fov | 9.74912 | 3.48416 |
| plane_fixed | 9.82753 | 3.61036 |

scale은 고정된 카메라 centroid 주위에서만 바꿨고 회전/translation을 표면에 재최적화하지 않았다. 큰 3D 오차 중 정렬 scale 선택에 민감한 부분을 보여준다. pose/depth scale 추정이 왜 달랐는지, 실제 blur가 원인인지는 이 진단만으로 확정할 수 없다. depth FIT scale에는 이미 평가용 surface GT가 쓰이므로 이를 새로운 우수 성능 결과로 선택하지 않는다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-extra-I25a-20261114-002/stages/I25a`. GT_DEPTH_AND_REGISTERED_POINTMAP_EVALUATED.
