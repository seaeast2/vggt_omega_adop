# I22–I25 — 영상 블러의 Omega·FoV·평면 RGB 최적화 영향 분리

작성일: 2026-11-14 KST. 새로운 블러 결과를 보기 전에 조건·평가 규약을 고정한다. 기존 TUM/ETH3D 결과를 이미 본 뒤 설계한 탐색적 원인 진단이다.

## 질문과 개입

TUM 주 구간의 FoV/3D 악화가 영상 품질 때문에 발생했는가? 같은 장면에 직접 블러를 가하면 어떤 단계가 악화되고, TUM에서 관측한 pose/depth scale 불일치가 재현되는가?

ETH3D office/pipes의 기존 3장씩, 같은 checkpoint·512×336 전처리 격자·GT·평가 pixel ID를 사용한다. 새 장면·view 선택·SAM 분할·허용 class·mask/plane 소속을 바꾸지 않는다.

| 조건 | 처리 |
|---|---|
| clean | 원본 processed RGB 그대로 |
| g075 | Gaussian sigma=0.75 px, 세 이미지 |
| g150 | Gaussian sigma=1.5 px, 세 이미지 |
| g300 | Gaussian sigma=3 px, 세 이미지 |
| motion9 | 수평 9-pixel 균일 motion kernel, 세 이미지 |
| frame1_g300 | 중간 frame 1만 Gaussian sigma=3 px |

블러는 기존 processed RGB의 uint8 격자에서 적용한다. 크기·색 채널·노출·압축·camera/GT 좌표를 바꾸지 않는다. OpenCV GaussianBlur sigmaXY 동일, 자동 kernel, BORDER_REFLECT_101; motion은 9×9 중앙 행 1/9 convolution이다. 저장 후 정확히 같은 uint8/255 입력을 모델과 SIFT에 사용한다. clean은 캐시 입력과 bitwise 동일하며 재추론 결과를 기존 clean Omega 출력과 대조한다. 모델은 eval/inference_mode, seed0, 호스트 GPU로만 실행한다.

## 단계와 원인 분리

- I22: 동일 장면 블러 입력 생성·SHA·실제 처리 이미지·quality/contact sheet. Laplacian variance, 평균 Sobel gradient, contrast와 대비 정규화 Laplacian을 기록한다. 서로 다른 장면의 sharpness 수치만으로 실제 TUM 블러 정도를 확정하지 않는다.
- I23: 조건당 3장 joint Omega 재추론. 2장면×6조건=12 forward. depth·K·pose·confidence를 그대로 저장한다. GT는 읽지 않는다.
- I24: RGB/FoV와 평면 RGB 단계의 진단. GT는 읽지 않는다.
- I25: 모든 출력이 완료된 뒤 frozen 레이저 GT와 공식 K/pose로 평가·분석한다. TUM 원본은 비교 참고이며 synthetic blur가 실제 손떨림/노출/노이즈/압축/저텍스처를 완전히 재현한다고 가정하지 않는다.

### Omega와 SIFT/FoV의 2×2 대조

각 블러 조건에서 geometry(depth/K/pose)와 correspondence UV를 독립적으로 바꾼다.

| 군 | Omega geometry | UV 대응 |
|---|---|---|
| F00 | clean 캐시 | clean의 기존 I0 대응 |
| F01 | clean 캐시 | 블러 RGB에서 검출한 대응 |
| F10 | 블러 Omega | 기존 clean 대응 UV 고정, 새로운 depth만 resample |
| F11 | 블러 Omega | F01의 블러 대응 UV 고정, 새로운 depth만 resample |
| native | 블러 Omega | 블러 RGB에서 추출하고 새 confidence/depth 유효성까지 적용한 기존 방식 |

F01의 대응 추출은 clean geometry의 depth/confidence 유효성 규약을 사용해 RGB matching 변화만 분리한다. F10/F11에서는 같은 UV/track를 유지하고 양수·유한 depth를 resample한다. confidence/3% gate 통과율은 별도 기록하고 진단군에서는 표본을 다시 삭제하지 않는다. native는 기존 전체 필터를 포함한다.

FIT는 기존 I0 excluded 바깥의 두 view bilinear footprint만 허용하고 track 전체를 보류로 묶는다. GT validation pixel mask는 모든 조건에서 고정한다. 새 결과를 보고 threshold를 바꾸지 않는다. 대응 부족·rank 부족·condition>1e6이면 기존 정책대로 beta=1을 사용하고 `UNIDENTIFIABLE`로 표시한다. 지원 부족 결과도 버리지 않는다. FoV의 bounds·prior·IRLS는 기존 그대로다. raw와 FoV 비교는 점 수를 유지한다.

### RGB 평면 단계 단독 대조

clean I10의 평면·소속, clean I2 K/pose/depth, 기존 I12의 active plane·FIT/validation source-target 표본, clean SIFT 대응과 prior를 고정한다. 오직 RGB만 블러 처리하고 기존 거리 1자유도/거리·법선 3자유도를 최적화한다. 마스크나 gradient 기준을 다시 선택하지 않는다.

블러 convolution이 보류 RGB를 FIT로 섞지 않도록, 각 split의 금지 픽셀을 가장 가까운 허용 RGB로 대체한 뒤 각 split 영상에 독립적으로 같은 kernel을 적용한다. source 색과 target 색 모두 해당 split 영상에서 읽는다. 모델/SIFT용 전체 이미지 블러와 이 split-safe 평면 진단을 구분한다. clean 결과가 기존 I12와 재현되는지 검사한다.

## GT 평가와 진단 지표

- 모든 조건에 기존 I20의 laser GT valid/FIT/validation pixel mask를 그대로 사용한다. GT로 correspondence/plane/blur 강도/모델/retained를 선택하지 않는다.
- depth는 각 Omega geometry의 raw FIT에서 median(GT/Z) scale을 한 번 구해 그 geometry의 모든 FoV 군에 공통 적용한다. FoV가 Z를 바꾸지 않는 것도 검증한다.
- 3D는 각 geometry의 camera pose만으로 한 번 구한 공통 Sim(3), 별도로 raw 표면 FIT 공통 Sim(3)를 보고한다. 한 geometry의 F00/F01 또는 F10/F11/native 사이에는 정렬을 재추정하지 않는다. 고정 평면 RGB 진단은 clean 정렬을 공통 사용한다. 정렬별 순위와 scale 민감도를 숨기지 않는다.
- camera pose scale / depth scale 비율, camera center 및 orientation residual을 기록한다. 이 비율을 metric depth 정확도나 실제 불일치의 유일한 원인으로 단정하지 않는다.
- **FoV의 직접 지표**로 공식 undistorted K를 실제 processed pixel-center 격자로 변환해 fx/fy 상대 오차·log 오차·beta 이상값을 보고한다. 이것은 3D Sim(3) 기준에 의존하지 않는다. 모델/solver에는 공식 K를 넣지 않는다.
- SIFT 수·mutual/RANSAC/track/FIT 수·공간 분포·rank/condition/bound 도달과, 사후 공식 카메라 fundamental matrix에 대한 Sampson residual을 기록한다. epipolar 일치만으로 정확한 대응을 보장하지 않는다.
- raw/FoV/고정 plane/거리/거리·법선의 depth MAE·RMSE·AbsRel·3D 오차, FIT/보류 RGB, 가시성·수치 실패를 함께 보고한다. plane RGB 손실의 절댓값은 blur로 신호 자체가 줄 수 있으므로 같은 blur의 fixed 대비 변화 및 parameter 이동·GT를 함께 읽는다.

## 해석·완료 조건

같은 geometry에서 F01−F00은 RGB 대응 변화의 조건부 영향, 같은 clean UV에서 F10−F00은 Omega geometry 변화의 조건부 영향, F11−F10−F01+F00은 상호작용을 나타낸다. 비선형 정렬/필터링의 영향은 직접 focal 오차와 함께 해석한다. 단조 악화를 성공 조건으로 강제하지 않는다. 두 장면에서 악화 양상이 다르면 그대로 보고한다.

인위적 블러의 인과 효과와 **실제 TUM 실패의 원인 확정**을 구분한다. TUM의 큰 scale gap이 합성 블러에서 재현되는지, 부족한 baseline/카메라 추정/정렬 선택이 더 큰 설명인지 기록한다. 근거가 부족한 원인은 미확인으로 남긴다. 악조건 TUM 구간을 삭제하지 않는다.

기술 검증→입력 생성→호스트 GPU 추론→대조 최적화→독립 GT 평가→수치/그림/원인 분석 보고→커밋·원격 확인까지 진행한다. 실패와 수정 실행은 별도 run으로 보존한다. 기존 결과·사용자 변경은 덮어쓰지 않는다.
