# H4f SAM 벽 소속 신뢰·이동 상한 없는 공유 평면 재투영

사용자 지시: H1에서 벽으로 분할된 전체 영역, 특히 이미지 1 top-middle처럼 깊이 추정이 크게 잘못된 점도 해당 공유 평면으로 이동한다. H4e의 자기 이동 5/10%·점 법선·참조 깊이3%·confidence·border/erosion이 큰 오류를 제외하므로 이 gate를 없앤다.

고정: C3a initial, H4d A4 공유 평면 계수, RGB/카메라/ID/점 수. hard 광선-평면 교차의 닫힌 해를 사용한다. SAM 모델은 재추론하지 않는다.

H1 RGB 마스크를 보정 결과 전에 다시 확인했다. camera0 mask0은 벽, mask1은 벽 외에 책상 일부도 포함한다. camera1 mask1은 mask0보다 넓은 벽을 포함하지만 H2d NMS에서 제거됐다. camera2 mask0은 오른쪽 공유 벽 외 왼쪽 다른 면도 포함한다. 주 비교는 camera0 mask0·camera1 mask1 전체를 신뢰한다. camera2는 mask0 중 그 평면의 교차점이 확인된 camera0/1 벽 마스크에 투영되는 부분만 같은 벽으로 연결한다. 이 연결은 평면 공간 범위를 정하는 2D 마스크 전파이며 원래/참조 depth·법선 gate는 없다. 카메라0/1에는 이 전파 조건도 요구하지 않는다.

6군:

- E35_M05_CONTROL: H4e EXP_N35_M05 실제 XYZ/accepted bitwise 재현.
- SAM_NMS_UNCAPPED: 각 프레임에서 H2d NMS가 남긴 H1 원본 mask 전체를 같은 평면으로 강제, 거리·법선·이동 상한 없음. frame2의 다른 면 포함 가능성을 진단한다.
- SAM_SHARED_M05 / SAM_SHARED_M20 / SAM_SHARED_UNCAPPED: 같은 주 SAM 소속으로 이동 5%/20%/상한 없음. 소속/법선/가림깊이/confidence/morphology는 동일하게 제거하여 이동량 효과만 비교한다.
- SAM_ALL_MASKS_UNCAPPED: H1 모든 wall mask union을 전체 프레임에서 같은 평면으로 강제하는 최대 신뢰 군. 다른 벽·책상 false positive를 숨기지 않고 주 군과 구분한다.

uncapped는 None이며 100% 초과 깊이 변화도 허용한다. 원본 광선에서 유한한 양의 Z 교차가 있어야 하고, 평행/수치 발산 방지용 |cos|≥1e-8만 요구한다. 새 최적화 파라미터 학습이 아니라 고정 평면에 정확히 맞추는 큰 hard 재투영이다. 음의 Z나 교차 불능을 억지로 수용하지 않는다.

top-middle의 사전 진단 ROI는 각 camera의 처리좌표 x=[154,358), y=[0,96)로 고정한다. 0-based camera0/1을 모두 보고해 이미지 번호 혼동을 피한다. 원래 mask0/mask1·NMS 누락·H4e 소속/각도/깊이/유효성 제외를 분해하고, source별 이동량/원래 Z/목표 Z·평면 잔차·단면/카메라/PLY를 보존한다. ROI는 SAM pixel과의 교집합이며 순수 벽의 GT annotation은 아니다.

검증: 제어 XYZ bitwise, 공유 평면/카메라/RGB/ID/589824점 고정, 거절·비소속 XYZ bitwise, >100% 합성 이동 수용, 음의 깊이/평행 거절, 5⊆20⊆uncapped, 공통 수용점 XYZ 동일. coverage 기준 실패해도 실제 proposed PLY를 제공하며 retained가 A0이면 명시한다. 판단은 전체 GT 정확도로 확대하지 않는다.
