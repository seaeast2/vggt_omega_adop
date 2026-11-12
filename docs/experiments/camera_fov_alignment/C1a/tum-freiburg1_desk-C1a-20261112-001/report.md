# C1a 실내 관측 지원 보조 검증

**NOT_ENOUGH_SUPPORT**. 원래 SIFT C1은 변경하지 않았다. 보정/GT 효과를 보기 전에 ORB→AKAZE 순서와 설정을 등록했다.

| 특징 | 쌍 | 전체 | fit | validation | 4×4 점유 | 지원 통과 |
| --- | --- | --- | --- | --- | --- | --- |
| ORB | [0, 1] | 203 | 182 | 21 | [9, 10] | True |
| ORB | [0, 2] | 53 | 50 | 3 | [5, 5] | False |
| ORB | [1, 2] | 89 | 74 | 15 | [9, 9] | False |
| AKAZE | [0, 1] | 148 | 121 | 27 | [10, 11] | True |
| AKAZE | [0, 2] | 52 | 48 | 4 | [6, 5] | False |
| AKAZE | [1, 2] | 85 | 67 | 18 | [9, 7] | False |

선택된 대체 특징: `None`. 선택은 기하 오차가 아닌 고정 지원 조건만으로 수행한다. 사후 지원 보완에 해당하므로 원래 SIFT 계획의 확인 실험과 구분한다.


실행 Stage: `results/camera_fov_alignment/tum-freiburg1_desk-C1a-20261112-001/stages/C1a`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
