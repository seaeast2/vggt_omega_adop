# G5 초기값·가중치 안정성

β=1 초기값 8군과 L/Z 가중치 0.1/0.25/1.0 민감도를 한 항씩 비교했다. 주 결과 선택에는 사용하지 않았다. 새 실내 구간은 G5a로 별도 기록한다.

| 비교군 | validation 3D median | validation Z median | coverage(raw) | 수렴 |
| --- | --- | --- | --- | --- |
| F-P_start_raw | 0.008872788 | 0.002695714 | 1.15196% | True |
| F-PL_start_raw | 0.010161252 | 0.003337774 | 1.45001% | True |
| F-PZ_start_raw | 0.008672215 | 0.002676447 | 1.09285% | True |
| F-PLZ_start_raw | 0.010113974 | 0.003329890 | 1.44837% | True |
| D-P_start_raw | 0.009768572 | 0.003065967 | 1.20533% | True |
| D-PL_start_raw | 0.010637935 | 0.002764007 | 1.43688% | True |
| D-PZ_start_raw | 0.010232388 | 0.003113561 | 1.18234% | True |
| D-PLZ_start_raw | 0.010650722 | 0.002669630 | 1.41963% | True |
| sensitivity_False_L_0.1 | 0.011067973 | 0.003246649 | 1.57646% | True |
| sensitivity_False_L_0.25 | 0.010116561 | 0.003329834 | 1.44837% | True |
| sensitivity_False_L_1.0 | 0.009931889 | 0.003579151 | 1.34370% | True |
| sensitivity_False_Z_0.1 | 0.010142117 | 0.003334572 | 1.44919% | True |
| sensitivity_False_Z_0.25 | 0.010116561 | 0.003329834 | 1.44837% | True |
| sensitivity_False_Z_1.0 | 0.010000586 | 0.003290266 | 1.42784% | True |
| sensitivity_True_L_0.1 | 0.010175510 | 0.002637733 | 1.54526% | True |
| sensitivity_True_L_0.25 | 0.010651032 | 0.002669610 | 1.41881% | True |
| sensitivity_True_L_1.0 | 0.010959700 | 0.002604542 | 1.35336% | True |
| sensitivity_True_Z_0.1 | 0.010634034 | 0.002720359 | 1.42949% | True |
| sensitivity_True_Z_0.25 | 0.010651032 | 0.002669610 | 1.41881% | True |
| sensitivity_True_Z_1.0 | 0.010944856 | 0.002532955 | 1.37705% | True |


실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G5-20261113-001/stages/G5`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
