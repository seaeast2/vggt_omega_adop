# H4f SAM 마스크 전체·이동 상한 없는 공유 평면 재투영

사용자 지시에 따라 H1 SAM 벽 마스크를 주 소속 근거로 사용하고 큰 깊이 오류도 고정 H4d A4 월드 평면으로 hard 재투영했다. 원래 589,824점·RGB·ID·카메라와 평면 계수는 보존했다. 점별 법선·confidence·영상 border·mask erosion·원본/참조 depth 차이 gate를 제거했다. uncapped는 100% 초과 변화도 허용하며 finite·양의 교차 Z·수치 평행 방지 cos≥1e-8만 남겼다. 평면을 바꾸거나 gradient 학습을 한 것은 아니다.

주 SAM_SHARED 군은 camera0 mask0, camera1의 더 넓은 mask1을 전체 사용한다. camera1 mask1은 H2d에서 NMS로 제외됐던 H1 원본이다. camera2는 mask0 중 이 평면의 교차점이 확인된 camera0/1 벽 범위에 투영되는 부분만 같은 벽에 연결한다. 이때 참조 깊이는 확인하지 않는다. camera0/1은 그 전파 조건도 없이 자기 SAM 마스크 전체를 대상으로 한다. SAM_ALL_MASKS는 책상/다른 면까지 포함된 모든 wall mask union을 한 평면으로 강제하는 별도 stress 비교다. 마스크를 수동 수정하거나 모델을 재추론하지 않았다.

| 군 | 소속 | 이동 frame0/1/2 | 최대 자기 깊이 변화 | 20% 초과 이동 | 고정 벽 두께 변화 | 가시성 포함 보존 | retained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E35_M05_CONTROL | 56160 | 32262 / 18643 / 5255 | 3.84% | 0 | -21.28% | True | proposed |
| SAM_NMS_UNCAPPED | 79502 | 40065 / 23584 / 11094 | 195.84% | 397 | -24.37% | True | proposed |
| SAM_SHARED_M05 | 80770 | 39863 / 23481 / 7967 | 5.00% | 0 | -24.37% | True | proposed |
| SAM_SHARED_M20 | 80770 | 40050 / 25457 / 8496 | 19.99% | 0 | -24.37% | True | proposed |
| SAM_SHARED_UNCAPPED | 80770 | 40065 / 32089 / 8616 | 581.66% | 6767 | -24.37% | True | proposed |
| SAM_ALL_MASKS_UNCAPPED | 103759 | 55801 / 32105 / 11094 | 581.66% | 21432 | -24.37% | True | proposed |

최대 이동은 원본 자기 카메라 Z-depth 대비 변화이며 world 거리나 오차의 정답이 아니다. selected/retained가 A0로 돌아가도 요청한 큰 이동의 실제 결과는 각 군 **proposed/**에 보존한다. 색과 점 수/카메라 불변은 가시성 조건과 따로 지표에 있다.

top-middle은 모든 camera의 처리좌표 x=[154,358), y=[0,96)와 자기 SAM 마스크 교집합으로 보정 전에 고정했다. 번호 혼동을 피하도록 camera0/1 모두의 before/after 깊이·이동량·H4e 미수용을 기록했다. RGB의 순수 벽 정답 annotation은 아니다. 원래 H1 mask별 audit에 NMS·법선·유효성·참조 범위·이동량의 제외를 따로 센다.

- camera0: top-middle 선택 17640 / 이동 17640, 상대 깊이 이동 최대 72.50%.
- camera1: top-middle 선택 8751 / 이동 8751, 상대 깊이 이동 최대 70.11%.
- camera2: top-middle 선택 757 / 이동 757, 상대 깊이 이동 최대 118.61%.

평면은 하나로 고정하고 각 점은 자기 카메라 광선을 따라 그 평면까지 이동한다. 거절·비소속 XYZ bitwise, 원본 RGB/ID/점 수, 자기 투영, 이전 H4e control bitwise, 5⊆20⊆uncapped, 공통점 XYZ 동일성 검사를 통과했다. 가시성·프레임 간 matching은 실제 큰 이동의 영향을 별도로 기록했다. SAM wall이라는 이름만으로 같은 벽·완전한 평면임이 증명되는 것은 아니므로 모든 mask 강제군을 주 군과 섞지 않는다. GT 정확도 개선은 미평가다.

주 실험 PLY: `artifacts/arms/SAM_SHARED_UNCAPPED/proposed/{pixel_rgb,frame_colors}.ply`. 비교 편의를 위해 실제 경로·hash를 inventory와 `results/c3a_plane_refinement/ply_review/H4f_*.ply`에 제공한다. 확대 단면·같은 크기 카메라 비교·마스크·top-middle crop을 저장했다.


실행 Stage: `results/c3a_plane_refinement/tum-freiburg1_desk-H4f-20261113-001/stages/H4f`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
