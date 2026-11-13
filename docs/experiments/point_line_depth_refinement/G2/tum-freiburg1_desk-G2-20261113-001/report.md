# G2 제약별 비교

주 비교군을 모두 실행하고 실제 proposed와 자동 selected를 분리 보존했다. 지원 부족으로 효과 확정은 보류한다.

| 비교군 | validation 3D median | validation Z median | coverage(raw) | 수렴 |
| --- | --- | --- | --- | --- |
| F-P | 0.008869971 | 0.002695597 | 1.15196% | True |
| F-PL | 0.010158531 | 0.003337891 | 1.45001% | True |
| F-PZ | 0.008667775 | 0.002676573 | 1.09285% | True |
| F-PLZ | 0.010116561 | 0.003329834 | 1.44837% | True |


실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G2-20261113-001/stages/G2`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
