# 야외 LiDAR 전이 실험 — KITTI 도시·ETH3D 숲

2026-11-14. O0에서 동결한 두 샘플의 3장을 그대로 사용한다. 기존 실내 시험과 같은 checkpoint·max_size 512 전처리·FoV/평면/RGB 최적화 설정을 적용한다. 실내·TUM·드론을 새로 실행하지 않는다. GT가 이미 공개·확인된 샘플이므로 탐색적 전이 평가이며 완전 blind 시험으로 주장하지 않는다.

## 비교와 실행 순서

1. I14: O0 이미지 식별자와 카메라·pose·전처리 변환을 동결한다. KITTI의 종횡비가 2를 넘으므로 공식 Omega loader가 중앙 750×375 영역을 crop한 뒤 512×256으로 resize한다. GT/K도 같은 변환을 적용한다. forest는 crop 없이 resize하며 원본과 processed 크기를 기록한다.
2. I15: 기존 Omega checkpoint로 각 3장을 공동 추론한다. raw depth/K/pose/confidence·processed RGB를 보존한다. GT·공식 pose는 모델 입력이나 손실에 사용하지 않는다.
3. I0/I1/I2/I3/I4/I10/I12: 기존 split·GroundingDINO/SAM·FoV·평면 후보·연결·named OR·평면 거리/법선 RGB 최적화를 실행한다. 의미 허용 목록은 기존 wall/table/screen 그대로다. 도로·나무·unknown을 새 평면으로 허용하지 않는다. 평면/RGB 지원이 없으면 무보정 출력을 보존하고 NO_SUPPORT로 구분한다.
4. I26: 최적화 완료 후 별도 평가 프로세스에서 LiDAR GT를 연다. omega_raw / fov / plane_fixed / plane_distance / plane_distance_normal / retained를 동일 유효 GT·보류 mask에서 비교한다. raw는 원래 depth/K/pose의 전체 점군으로 필터링·재정렬하지 않는다.

## 평가 규약

- Depth는 camera Z, 미터 단위다. KITTI는 공식 annotated uint16/256 GT, forest는 원본 왜곡 카메라의 FARO-rendered float32 GT를 공식 렌즈 모델로 processed 픽셀에 대응시킨다. 결측을 보간하지 않는다.
- Raw FIT의 GT/Z 중앙값으로 depth scale 하나를 추정해 모든 군에 공통 적용한다. FIT와 보류 GT는 분리한다. 같은 Z를 유지하는 raw/FoV depth 차이를 FoV 효과로 해석하지 않는다.
- 3D 주 지표는 공식 pose만으로 구한 공통 Sim(3)다. 보조 지표는 raw FIT 표면에서 구한 공통 Sim(3)다. 군별 별도 정렬이나 GT 최적화는 하지 않는다. 두 정렬에서 순위가 다르면 민감도로 그대로 보고한다.
- FoV는 processed GT K 대비 fx/fy 평균 상대 오차와 보류 대응의 GT epipolar 잔차를 추가 보고한다. 전역 depth/3D 정렬에 독립적인 보정 지표다.
- 전체 보류 영역과 실제 투영·RGB 최적화 영역을 구분한다. 사전 개선 기준은 기존과 같이 plane_distance_normal이 raw와 plane_fixed 모두에 대해 MAE 1% 이상 개선하고 RMSE가 증가하지 않으며 RGB/가시성 판정도 통과하는 경우다. 최소 보류 최적화 GT 500개가 없으면 지지 부족으로 판정한다.
- KITTI의 동적 물체, semi-dense GT, OXTS pose 오차와 forest의 흑백·잎 움직임·얇은 가지·결측은 제한으로 남긴다. GT를 보고 ROI나 문턱값을 바꾸지 않는다. 이 시험은 기존 알고리즘의 전체 화면 전이 시험이며 동적 물체 제거·새 도형·새 의미 class를 추가하지 않는다.

실패 run과 원본 O0, 입력·source·checkpoint hash, plane/observation provenance를 보존한다. GPU는 호스트에서 샌드박스 밖 실행한다. 이번 범위는 원본 입력의 기본 비교이며 합성 블러 6조건의 반복은 포함하지 않는다.
