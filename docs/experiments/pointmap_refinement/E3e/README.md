# E3e 실행 이력

| Run ID | 장면 | 상태 | 보고서 |
| --- | --- | --- | --- |
| hkairport01-E3e-20261112-001 | HKairport01 | 완료: 200회·172,265점 실제 이동, selected=초기·광도 개선 기준 실패 | [보고서](hkairport01-E3e-20261112-001/report.md), [native 전후](hkairport01-E3e-20261112-001/figures/rgb_native_comparison.png) |
| amtown01-E3e-20261112-001 | AMtown01 | 완료: 200회·159,177점 실제 이동, selected=초기·광도 개선 기준 실패 | [보고서](amtown01-E3e-20261112-001/report.md), [native 전후](amtown01-E3e-20261112-001/figures/rgb_native_comparison.png) |

[고정 조건·재현](../../../../experiments/pointmap_refinement/E3e/README.md). LiDAR 보정 규약 미검증으로 기하 정확도는 평가하지 않는다.

| 장면 | 초기 RGB 손실 | 실제 last RGB 손실 | 선택 step | 실제 이동점 | Last의 초기 native 영역 coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| HKairport01 | 0.017748732 | 0.034371992 | 0 | 172,265 | 92.358556% |
| AMtown01 | 0.028672801 | 0.042417280 | 0 | 159,177 | 94.575310% |

두 장면 모두 현재 최소 ADOP 방식·고정 조건의 광도 개선을 확인하지 못했다. HKairport01의 초반 매 step 로그에는 약 0.29%의 작은 감소가 있으나 사전 1% 기준과 체크포인트 선택을 바꾸지 않았다. 이 결론은 각 3장 그룹·같은 입력 시점의 한정된 시험이며 야외 전체·ADOP 전체·실제 기하 정확도의 결론이 아니다. [사후 검증 코드](audit.py).
