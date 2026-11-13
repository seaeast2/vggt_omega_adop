# H3 평면 재투영 결과

C3a K/pose/RGB/ID/점 수를 고정하고 자기 픽셀 광선의 Z-depth만 이동했다. H3/H4 적합기는 동일하며, 모든 support·gate는 A0에서 판단했다.

| 군 | 유효 평면 | 공유 평면 | 수용점 | 보존 조건 | retained |
| --- | --- | --- | --- | --- | --- |
| A1_FRAME_RAWMASK | 1 | 0 | 7577 | True | proposed |
| A2_FRAME_REFINED | 8 | 0 | 20207 | True | proposed |

자동 마스크의 중복은 모호한 관측으로 제외했으며, 보정에 쓰일 지지가 줄 수 있다. 부족한 군도 A0와 같은 NPZ/PLY·투영을 실제로 저장했다. 실패를 보정 성공으로 세지 않는다. 원시 SAM에 책상 일부가 포함된 사례도 원본 그대로 보존했다. 평면 적합 후 잔차 감소는 기하 정확도 증명이 아니다. 최종 평면·프레임별 지지·양방향 연결 근거·거절 사유·holdout의 보정 전 잔차는 JSON에 있다.



실행 Stage: `results/c3a_plane_refinement/tum-freiburg1_desk-H3-20261113-001/stages/H3`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
