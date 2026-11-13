# H4g 꺾인 두 벽: 중첩 SAM 마스크 분리와 수직 평면

사용자는 camera1 작은 경계가 오른쪽 벽, 큰 경계의 왼쪽 부분이 오른쪽 벽에 수직인 다른 벽이라고 확인했다. H4f에서 camera1의 큰 마스크 전체에 오른쪽 평면을 적용한 소속 오류를 수정한다. 이는 사용자 제공 구조 prior이며 계측 GT는 아니다.

사전 RGB/마스크 진단: 작은 H1 mask0=23,584px, 큰 mask1=32,089px, 교집합=23,568px. 큰 것에서 작은 것을 뺀 8,521px 중 최대 8-connected 성분 8,290px(bbox x0..145,y0..88)이 왼쪽 벽이다. 나머지 231px 경계/작은 성분은 모호로 남긴다. 작은 mask0에 우선권을 주며 마스크를 하나로 union하지 않는다.

오른쪽 평면은 H4d A4 계수 그대로 고정한다. 왼쪽 plane은 C3a의 원래 XYZ에서 추정하고 H4f로 잘못 이동한 XYZ는 적합에 사용하지 않는다. 왼쪽 전체 마스크는 uncapped 이동 대상으로 쓰되 fit만 erosion3px·원본 confidence 하위10% 제외·H2d strict holdout을 적용한다. 사전 진단 fit support는 322점으로, 단일 프레임의 저지원 추정이다.

두 적합기를 비교한다.

- 자유 평면: 기존 seed0 RANSAC/SVD-Huber 적합기. original Z로 정규화한 0.5% inlier, >=70% 및 >=100 fit 지지.
- 수직 평면: 오른쪽 단위 법선 nR의 nullspace U(3x2)에 nL=U[cos(theta),sin(theta)]로 두어 nL·nR=0을 정확히 강제한다. 원본 fit 점의 (nL·X+d)/D0를 Huber delta0.005로 최소화한다. 자유 법선의 nullspace 투영 초기각, 그 각+pi/2, 0, pi/2의 4개 초기값에서 max2000 evaluations/tolerance1e-12로 실행하고 training loss로 고른다. offset은 원본 점에서 추정한다. 최소70%/100 fit 지원은 유지하고 수직 prior·실제 잔차·holdout은 별도 보고한다.

5개 군: H4f bitwise 재현, 왼쪽 오소속 해제 후 C3a 복원, 왼쪽 자유 평면, 왼쪽 수직 평면, 수직 평면의 camera2 전파. camera0/1 오른쪽 기존 소속의 XYZ는 H4f와 bitwise 동일해야 한다. camera1의 큰-minus-작은 마스크 8,521px를 오른쪽 소속에서 모두 제거하고, 왼쪽 주요 성분만 L plane에 배치한다. 작은 경계나 모호 성분은 R로 강제로 넘기지 않는다.

camera2 전파는 H1 mask0의 connected components별로 각 plane의 광선 교차를 참조 RGB 마스크에 투영한 공간 지지를 비교한다. L 참조는 camera1 왼쪽 주요 성분, R 참조는 camera0 mask0 및 camera1 작은 mask0이다. L 지지 >=100px, 성분의 >=50%, R 대비 >=20 percentage points일 때만 L을 적용한다. source depth/point normal/이동량을 gate로 쓰지 않는다. 모호하면 새 L 보정을 하지 않고 기존 R 소속을 보존한다. camera0은 확정된 R 마스크를 그대로 유지한다. 전파된 L은 같은 global L 계수를 재사용하며 frame2에서 새 평면을 적합하지 않는다.

모든 새 평면 이동은 상한 없음/finite-positive intersection/cos1e-8이고 RGB·카메라·점 수·ID 고정이다. 실패 적합은 실패와 실제 A0 보존으로 남긴다. 전후 mask/소속/원본 픽셀색/프레임색/plane 색/카메라·corner 단면/개별 plane 잔차·이동·모호/비대상 복원을 저장한다. 90°는 부과한 제약의 충족이지 독립 정확도 증거가 아니다. corner 교선 위치·왼쪽 offset은 GT로 확인되지 않았다.
