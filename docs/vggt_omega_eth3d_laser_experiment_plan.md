# ETH3D 실내 레이저 GT를 이용한 평면 RGB 최적화 전이 실험

작성일 2026-11-14 KST. 새 장면의 추론·평면 최적화·GT 결과를 보기 전에 규약을 고정한다.

## 데이터 조사와 선택

| 후보 | 표면 GT | 접근성과 선택 |
|---|---|---|
| [ETH3D high-res training](https://eth3d.ethz.ch/datasets) | FARO Focus X 330 레이저 스캔과 가림을 고려한 렌더 depth | 공개 office/pipes 실내 2개 장면 선택 |
| [ScanNet++](https://scannetpp.mlsg.cit.tum.de/scannetpp/) | 고급 레이저 스캔 | 계정·사용 신청 승인·개인 토큰 필요, 이번에는 사용하지 않음 |
| [Tanks and Temples](https://tanksandtemples.org/download/) | 산업용 레이저 스캔, training GT 공개 | Meeting room 등 실내 후보. 현재 depth·보정 대응을 명시한 ETH3D를 우선 |

[ETH3D 공식 규약](https://eth3d.ethz.ch/documentation)에 따르면 제공 depth는 원래 왜곡된 RGB의 4-byte float row-major dump이며 결측은 infinity다. 레이저 스캔에서 occlusion mesh·image mask를 고려해 렌더한 값이다. 따라서 depth가 원시 LiDAR 거리값이거나 왜곡 보정 RGB와 같은 격자라고 가정하지 않는다. 실내 스캔이어도 센서·등록·가림 오차와 결측은 남는다.

## 장면·이미지와 단계

- office, pipes에서 각각 3장 joint 추론. 사전 제공 COLMAP의 RGB 특징 track 공시성을 이용해 최소 pair 공유 track 수가 가장 큰 triple을 결정적으로 선택한다. 카메라 ID가 같고 실제 영상 크기가 같은 조합으로 제한하며 GT depth/오차는 선택에 사용하지 않는다. 공시성이 부족하면 실패를 보존하고 RGB 기준으로만 사유를 기록한다.
- I14: 공식 RGB/보정 다운로드·SHA-256·COLMAP pose 규약·triple 선택·RGB contact sheet. 레이저 depth archive는 캐시만 하고 최적화 완료 전 내용은 평가에 사용하지 않는다.
- I15: 같은 Omega checkpoint·512 long-edge·max_size로 호스트 GPU에서 한 장면당 1회 joint 추론. 새 환경·모델 설치 없이 기존 체크포인트를 사용한다.
- 새 dataset ID의 I0/I1/I2/I3/I4/I10/I12를 순서대로 실행한다. 같은 seed·공간/track holdout·FoV fit·후보·연결·exact wall/table/screen·named OR·RGB 최적화 손실/가중치/bounds/지원 기준을 재사용한다. floor·ceiling 등으로 허용 태그를 추가하지 않는다. 지원 부족도 결과로 남긴다.
- 고해상도 DSLR로 인한 mask 메모리 폭증을 피하려 SAM/DINO 입력은 Omega의 실제 processed RGB로 고정한다. 이전 TUM은 원본 640×480 SAM 입력이었다. 이 해상도 차이는 재현/전이의 제한으로 보고하고 모델 threshold·grid32는 바꾸지 않는다.
- I20: 위 출력이 완료된 뒤 별도 프로세스에서 레이저 depth 평가. initial/plane_fixed/plane_distance/plane_distance_normal/retained 비교. I12 retained 선택은 RGB/가시성만 이용하고 GT로 교체하지 않는다.

## 왜곡과 GT 대응

공식 undistorted RGB(PINHOLE)를 추론 입력으로 사용한다. 처리된 픽셀의 중심 광선을 공식 PINHOLE K와 resize/padding 규약으로 원래 해상도에 대응시키고, 공식 THIN_PRISM_FISHEYE 식으로 왜곡된 원본 센서 격자에 투영한다. 해당 격자에서 유효한 가장 가까운 레이저 depth를 읽는다. 원래와 undistorted 카메라의 pose/파일명 일치, camera center 광선·왜곡 식·픽셀 convention·depth의 camera-Z 규약을 공식 source 및 수치 검증으로 확인한다. 단순히 depth를 RGB 크기로 resize하거나 왜곡 계수를 중복 적용하지 않는다. 필요시 작은 원본 픽셀 위치 차이와 sparse GT에 따른 평가 제한을 함께 기록한다.

I0 FIT AND valid GT에서 initial의 median(GT/initial camera-Z) 공통 scale을 구하고, validation AND valid GT의 동일 관측 집합으로 모든 비교군을 평가한다. scale 외 shift 없음. 각 군 재정렬·평가 마스크 교체 없음. 전체/투영/최적화/태그별/per-frame MAE·RMSE·AbsRel·delta 및 보류 RGB/가시성 기록. smooth GT 보조 mask도 결과와 독립적으로 고정한다. RGB 카메라 보정 오차의 영향을 분리하기 위해 3D 대응 오차는 baseline FIT-only Sim(3) 정렬 후 보조 지표로만 표시한다.

I12와 같은 성공 기준을 유지한다. 주 처치군은 거리·법선이다. initial과 plane_fixed 모두 대비 전체 MAE 1% 이상 개선, RMSE 비증가, 보류 RGB 1% 이상 개선, 최대 frustum 손실 0.5% 이하여야 `GT_IMPROVED`. optimized GT validation 500개 미만이면 `INSUFFICIENT_SUPPORT`; 그 외는 `NO_CONFIRMED_GAIN`. 장면별 결과를 전부 보존한다. 공개 training split은 접근 구분이며 모델 학습에는 사용하지 않는다. 이 소규모 검증을 ETH3D 공식 benchmark 제출/전체 성능으로 부르지 않는다.

## 보존과 완료 조건

각 실행의 실패·parent·코드/모델/입력 hash·다운로드 URL·환경·GPU 실행 맥락·mask·SIFT split·NPZ/PLY/plane registry·오차 이미지를 남긴다. 실제 데이터 다운로드→호스트 추론→분할→평면/RGB 최적화→레이저 GT 평가→결과 보고→커밋·원격 확인까지 수행한다. 기존 TUM 결과 및 사용자 변경은 덮어쓰지 않는다.
