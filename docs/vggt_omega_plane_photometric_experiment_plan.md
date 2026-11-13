# I12–I13 평면 거리·법선의 다중 시점 RGB 최적화 실험 계획

작성일: 2026-11-14 KST. 아래 규약은 새 최적화 및 GT 평가 전에 고정한다. 이전 I11 결과를 이미 확인한 뒤 설계한 탐색 실험이며 독립 confirmatory 평가라고 부르지 않는다.

## 질문과 비교군

현재 I10의 의미 기반 평면 투영에서 평면 위치·방향을 타 시점 RGB로 조정하면, 평면 고정 및 FoV 초기 점군보다 실제 깊이 오차가 줄어드는가?

| 비교군 | 동작 |
|---|---|
| initial | 현재 I2 FoV 점군 |
| plane_fixed | I10 named_OR의 평면·소속·점군 그대로 |
| plane_distance | 평면당 거리 1자유도 최적화 |
| plane_distance_normal | 평면당 거리 1 + 법선 방향 2자유도 최적화; 사전 지정 주 처치군 |
| retained | RGB 보류·가시성 기준 통과 시 주 처치군, 아니면 기존 I10 retained |

RGB index 30/40/50 및 100/110/120의 두 구간을 같은 규약으로 실행한다. pose, intrinsics, RGB, ID, UV, 의미 태그, 평면 소속을 고정한다. unknown 및 미지원 평면은 유지한다. 새 primitive·Manhattan prior·카메라 보정·마스크 재학습은 하지 않는다. 현재 I10은 구간당 94개 평면이며 다중 view 지지가 있는 ID는 주 구간 1개, 추가 구간 4개다. 새 병합을 하지 않으므로 이번 결과를 완전한 공유 평면 지도 최적화로 해석하지 않는다.

## 변수와 미분

평면의 초기 단위 법선을 n0, 접평면 기저를 u,v, 초기 평면 위의 FIT 중심을 c, FIT 초기 깊이 중앙값을 zref라 한다. w=n0+a*u+b*v, 평면식 w·(X-c)-s*zref=0. 거리 군은 s만, 거리·법선 군은 a,b,s를 최적화한다. 저장할 때 법선과 offset을 함께 정규화한다.

각 관측 광선 X=C+z*q와 평면의 교점 z를 해석적으로 계산한다. z와 타 카메라 투영, RGB bilinear sampling을 연결한 해석 Jacobian으로 scipy least_squares를 실행한다. 중앙 차분과의 Jacobian 검증, 알려진 평면의 합성 영상 복원 검증을 먼저 통과해야 실제 결과를 해석한다. CPU float64 실행이며 GPU를 사용하지 않는다.

## RGB 지원과 손실

- source는 해당 평면에 이미 소속된 픽셀이다. target은 다른 두 카메라의 원본 RGB다. 자기 카메라의 색 재투영은 목적함수로 쓰지 않는다.
- 초기 타 view 투영이 영상 안, 같은 허용 named class, 동일 split의 bilinear footprint 안이며 초기 타 view raw depth보다 3% 이상 뒤에 있지 않아야 한다. 이 표본을 최적화 전에 고정한다. target class 일치는 동일 물리 표면을 보장하지 않는 한계가 있다.
- FIT에는 기존 I0 excluded의 바깥만 사용한다. 보류 RGB에는 I0 validation만 사용한다. 목적함수 target 영상의 금지 픽셀은 해당 split의 가장 가까운 허용 RGB로 채워 실제 보류 RGB가 FIT 손실에 유입되지 않게 한다. source 색·raw-depth prior·기준 중심도 FIT만 읽는다. 이동 후 잔차를 삭제하지 않고 고정 표본과 영상/허용 영역 이탈 penalty를 사용한다.
- 평면당 FIT photo 최대 512개, 보류 photo 최대 512개. 초기 RGB gradient norm 0.01 이상을 요구하고 결정적 균등 subsampling을 사용한다. FIT 64개·보류 16개 미만은 최적화하지 않는다. 각 표본은 하나의 source-target 관측이다.
- FIT SIFT 대응의 source가 평면에 속하고 두 view footprint가 FIT이면 재투영 잔차를 추가한다. 이 대응은 기존 I0에 고정된 것이며 새 GT 대응을 만들지 않는다.
- 정규화 손실: photo pseudo-Huber sigma=0.05 RGB[0,1], 대응점 pseudo-Huber sigma=2 px, raw 상대 깊이 prior sigma=0.02·가중치 0.01, 접선 법선 prior sigma=10도·가중치 0.01, 영상 밖/유효 깊이/허용 영역 이탈 penalty. photo와 대응점은 각각 표본수로 정규화한다. 하이퍼파라미터를 GT 결과에 맞춰 재선택하지 않는다.
- 거리 s 범위 ±0.20, a,b 범위 각각 ±tan(10도), 최대 100 함수 평가. 이는 이번 국소 최적화의 명시적 탐색 범위이며 기존 I10 무제한 투영 규약을 소급 변경하지 않는다. 모든 소속 관측의 양의 깊이·유한 교점·자기 투영을 확인하고 수치 실패 평면은 초기로 복원한다. bound 도달 및 Jacobian 특이값도 기록한다.

## 저장·선택·평가

I12는 GT를 읽지 않는 RGB 최적화 실행이다. 모든 비교군의 pointmap·평면·support·손실·가시성·실행 로그·입력/source hash를 별도 run에 저장하고 완료한다. pose·K·RGB·ID·UV·unknown 좌표 동일성을 검사한다. 주 처치군의 고정 보류 photo 손실이 plane_fixed보다 1% 이상 감소하고 기존 최대 frustum loss 0.5% 기준을 통과할 때만 retained로 선택한다. GT는 선택에 사용하지 않는다. 지원 부족이면 그 사실을 보고한다.

I13은 완료된 I12 출력만 읽는 별도 평가다. I11의 frozen GT 배열·FIT baseline scale·공통 validation mask·sensor-edge 보조 mask·Sim(3)를 그대로 재사용한다. 비교군별 재정렬, 새 GT 기반 보정, 결과를 본 뒤 마스크 변경은 금지한다. 전체/최적화 소속/태그별/per-frame MAE·RMSE·AbsRel·대응 3D 오차와 RGB 손실을 보고한다.

주 처치군이 **initial과 plane_fixed 모두에 대해 전체 깊이 MAE를 1% 이상 줄이고 RMSE를 늘리지 않으며**, 보류 RGB와 가시성 기준을 통과하면 해당 구간의 `GT_IMPROVED`로 판정한다. 최적화 소속의 GT validation 500개 미만은 `INSUFFICIENT_SUPPORT`, 그 외는 `NO_CONFIRMED_GAIN`이다. 두 구간 결과를 모두 보존하고 일부 영역의 개선을 전체 성능 개선으로 확대하지 않는다. 색상 손실 감소만으로 성공이라 부르지 않는다.

계획→I12→I13→검증→보고서·경량 결과 커밋/푸시까지 수행한다. 실패와 수정 실행은 삭제하지 않고 이유를 남긴다. 기존 사용자 변경 `docs/research/README.md` 삭제는 건드리지 않는다.

## 실행 중 수정 — GT 확인 전

I12 첫 주 구간은 완료됐고 추가 구간 첫 평면의 미분 검증이 중단됐다. 중앙 차분 간격 1e-6에서 투영 좌표가 bilinear 픽셀 경계를 넘어 비미분점을 가로질렀다. 같은 입력에서 간격 1e-7의 상대 Jacobian 오차는 2.1e-9였다. 검증 간격만 1e-7로 수정한 I12.2로 두 구간을 재실행한다. 목적함수·optimizer·bounds·마스크·표본·GT 판정은 바꾸지 않는다. 첫 완료/실패 실행은 보존하며 I13 GT 평가는 아직 실행하지 않았다.
