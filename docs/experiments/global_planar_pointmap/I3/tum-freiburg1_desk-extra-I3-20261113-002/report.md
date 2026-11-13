# I3 자동 평면 후보

semantic 전체 마스크와 공식 automatic NMS 출력·포함 차집합·교집합·연결 성분을 후보로 만들고 fit만으로 0/1/2/3 plane의 robust 잔차와 복잡도를 비교했다. 7/21px normal은 보류점을 moment에서 제외한 고정 prior로 저장했다. 채택된 plane의 이동 영역에는 0.5% 잔차 gate를 적용하지 않는다.

잔여 연결 성분을 재귀 후보로 만들고 quadratic 곡면 대안을 training score로 비교했다. 해결되지 않은 영역은 unknown이다. 곡면/동적 물체의 실제 의미론적 정답은 없으므로 자동 판정의 오류율은 확정할 수 없다. 전체 후보·탈락 근거를 로컬에 보존했다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-extra-I3-20261113-002/stages/I3`. GT_NOT_EVALUATED.
