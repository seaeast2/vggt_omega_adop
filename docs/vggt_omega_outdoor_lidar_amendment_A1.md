# A1 — 숲의 의미 지지 0개에 대한 동일 출력 조기 종료

2026-11-14. 원래 전이 규약의 의미 허용 목록과 문턱값을 변경하지 않는다. 숲 I1의 세 영상 전체 grounded registry에서 exact `wall/table/screen`이 0개임을 확인했다. I10은 각 group에 허용 named anchor가 있어야만 평면을 생성하므로, 어떠한 I3/I4 기하 결과가 나오더라도 최종 I10 평면 수는 0개다. 같은 이유로 I12의 최적화 parameter 수도 0개다.

숲 I3의 재귀 geometry 후보 계산을 중단하고 partial log·후보를 `superseded`로 보존한다. I3/I4 전체 기하 탐색을 완료했다고 주장하지 않는다. I10에 직접 명시적 `NO_NAMED_SUPPORT` branch를 기록하며, initial/named_local/named_OR/retained의 점군은 FoV 출력과 bitwise 같게 저장한다. 기존 I12는 이 빈 plane registry를 입력받아 지원 0개임을 기록한다.

이는 unknown을 투영하지 않는 원래 규칙에 대한 동일 출력 조기 종료다. GT 깊이·오차·K 개선 여부에 따른 결정이 아니며, 의미 지지 검사는 GT 평가 전에 수행했다. crop/resize·checkpoint·FoV·평면·RGB 문턱값·GT mask·정렬 규약·성공 기준은 변경하지 않는다. 최종 보고에서 전체 기하 탐색 대신 이 branch를 사용했음을 명시한다.
