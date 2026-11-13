# I10 named OR 평면 투영 테스트

각 3-frame 구간 안에서 동일 표면으로 연결된 영역의 named 정보를 OR했다. exact `wall/table/screen`만 허용하고 혼합 태그·다른 이름·대응 미확정은 보류했다. 박스·원통·구, I6 공동 최적화와 구조 prior는 사용하지 않았다.

| 구간 | local 투영점 | OR 투영점 | OR 신규 unknown 점 | 최대 frustum 손실 | retained |
| --- | --- | --- | --- | --- | --- |
| tum-freiburg1_desk | 261,427 | 264,880 | 3,453 | 0.03537% | proposed |
| tum-freiburg1_desk-extra | 194,834 | 194,950 | 116 | 0.58717% | initial |

가시성 기준은 기존의 최대 frustum 손실 0.5%를 유지했다. 주 구간은 proposed를 retained로 선택했고 추가 실내는 initial을 유지했다. 두 구간 모두 local/OR의 고정 보류 대응 상대 3D median은 동일했다. GT 기하·의미 정확도 또는 화면 전체 개선을 입증한 결과는 아니다.

소속 OR는 원본 RGB의 동결 fit 대응 2개 이상을 요구한다. 이는 보수적인 surface association이므로 실제 같은 면이어도 연결하지 못한 부분은 제외될 수 있다. 다른 카메라의 동일 픽셀 좌표를 직접 OR하지 않았다.

초록은 현재 view의 허용 named 후보, 파랑은 다른 view에서 전달된 신규 후보, 붉은 영역은 제외/보류다. 마스크가 다른 물체를 잘못 포함한 경우까지 의미론적으로 보장하지 않는다.

## tum-freiburg1_desk

[실행 보고서](tum-freiburg1_desk-I10-20261113-001/report.md) · [소속 OR 이미지](tum-freiburg1_desk-I10-20261113-001/figures/named_OR_mask.png) · [RGB 비교](tum-freiburg1_desk-I10-20261113-001/figures/rgb_comparison.png)

PLY/pointmap/plane registry: `results/global_planar_pointmap/tum-freiburg1_desk-I10-20261113-001/stages/I10/artifacts/named_or/`의 initial, named_local, named_OR, retained 폴더.

## tum-freiburg1_desk-extra

[실행 보고서](tum-freiburg1_desk-extra-I10-20261113-001/report.md) · [소속 OR 이미지](tum-freiburg1_desk-extra-I10-20261113-001/figures/named_OR_mask.png) · [RGB 비교](tum-freiburg1_desk-extra-I10-20261113-001/figures/rgb_comparison.png)

PLY/pointmap/plane registry: `results/global_planar_pointmap/tum-freiburg1_desk-extra-I10-20261113-001/stages/I10/artifacts/named_or/`의 initial, named_local, named_OR, retained 폴더.

