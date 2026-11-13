# G3 제약별 비교

주 비교군을 모두 실행하고 실제 proposed와 자동 selected를 분리 보존했다. 지원 부족으로 효과 확정은 보류한다.

| 비교군 | validation 3D median | validation Z median | coverage(raw) | 수렴 |
| --- | --- | --- | --- | --- |
| D-P | 0.009768391 | 0.003065694 | 1.20615% | True |
| D-PL | 0.010639658 | 0.002763970 | 1.43688% | True |
| D-PZ | 0.010230916 | 0.003113059 | 1.17906% | True |
| D-PLZ | 0.010651032 | 0.002669610 | 1.41881% | True |


실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G3-20261113-001/stages/G3`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
