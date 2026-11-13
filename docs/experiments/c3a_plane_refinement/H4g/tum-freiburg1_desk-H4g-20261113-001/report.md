# H4g 꺾인 두 벽 분리와 수직 평면 보정

사용자가 camera1 큰 마스크의 왼쪽이 오른쪽 벽에 수직인 별도 벽이라고 확인했다. **H4f의 큰 마스크 전체→오른쪽 평면 소속은 잘못된 연결이었다.** 기존 H4f를 보존하고 작은 마스크 우선·큰-minus-작은 왼쪽 최대 연결 성분을 분리했다. 왼쪽 주요 성분은 8,290점, 전체 차집합 8,521점 중 나머지 231점은 모호한 경계로 C3a에 복원한다.

오른쪽 plane은 기존 H4d A4 그대로이며 이미 좋아진 오른쪽의 H4f XYZ를 bitwise 보존했다. 왼쪽 plane은 잘못 이동한 H4f가 아니라 원래 C3a의 왼쪽 내부 fit 322점에서 추정했다. confidence/erosion/split은 적합 지원에만 사용하고 이동 대상 8,290점을 잘라내지 않았다. 새 hard 이동은 계속 uncapped다.

자유 적합의 두 평면 각도는 73.1306°, 사용자 수직 prior를 적용한 적합은 90.0000°다. 수직 적합 fit inlier 비율은 73.29%다. 정확히90°는 부과한 제약의 충족이며 실제 각도의 독립 측정 결과가 아니다. L plane은 camera1에서만 적합했고 다른 카메라에는 그 계수를 재사용한다. 왼쪽 offset과 corner 교선의 GT 위치는 미검증이다.

| 군 | world 평면 수 | 왼쪽 이동 | 왼쪽→오른쪽 오소속 | 두 평면 각도 | 기존 오른쪽 보존 | 가시성 포함 보존 | retained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F_CONTROL | 1 | 8290 | 8290 | None | True | True | proposed |
| SPLIT_RESTORE_LEFT | 1 | 0 | 0 | None | True | True | proposed |
| TWO_PLANES_FREE | 2 | 8290 | 0 | 73.13062498738974 | True | True | proposed |
| TWO_PLANES_ORTHO | 2 | 8290 | 0 | 90.0 | True | True | proposed |
| TWO_PLANES_ORTHO_TRANSFER | 2 | 8290 | 0 | 90.0 | True | True | proposed |

F_CONTROL은 의도적으로 기존 오류를 그대로 재현한 군이다. SPLIT_RESTORE_LEFT는 오소속만 해제해 C3a로 복원한 제어다. TWO_PLANES_FREE/ORTHO는 같은 소속에서 평면 제약만 비교한다. TRANSFER는 camera2의 H1 연결 성분을 각 평면의 2D 참조 마스크 지지로 연결하며 pixel>=100·fraction>=50%·R 대비20pp를 만족한 L만 추가한다. 새 frame2 plane을 적합하지 않는다. 연결 근거와 모호 판정은 JSON에 있다. source0/1의 오른쪽 기존 보정은 모두 유지했다.

각 군의 실제 proposed를 모두 보존했다. camera1 왼쪽 mask를 R로 보내는 관측은 수정군에서 0이며 231개 모호한 점은 원래 위치로 복원했다. 원본 RGB/ID/카메라/589,824점·거절점 불변, 자기 재투영, H4f 재현, plane 잔차·수직 제약·오른쪽 bitwise 보존을 검증했다. 가시성 기준 실패 시 retained는 A0이므로 실제 변화는 proposed에서 확인한다. 기존 고정 G6 벽 ROI는 R만 보므로 새 왼쪽 개선 평가를 대신할 수 없다. L holdout의 보정 후 plane 잔차0은 정확도 증거가 아니다.

주 비교 PLY: `artifacts/arms/TWO_PLANES_ORTHO_TRANSFER/proposed/`. 원본 픽셀색·프레임색 외 `plane_colors.ply`는 R=초록/L=주황/미보정=회색이다. 같은 고정 시점 corner 단면 및 camera1 소속 overlay로 꺾임을 확인한다. 실제 기하 정확도와 사용자 prior의 계측 검증은 미평가다.


실행 Stage: `results/c3a_plane_refinement/tum-freiburg1_desk-H4g-20261113-001/stages/H4g`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
