# 보조 검증·실행 명세

실행 실패·설계 보완은 원본을 덮어쓰지 않는다. 각 실행 source snapshot과 config가 당시 명세다.

## C0a — 최근접점 보조 지표

C0 최초 실행에서 OpenCV FLANN KD-tree의 checks=-1 결과가 exhaustive 정답과 달랐다. C0a에서 재현하고 정확한 BF L2 방식으로 교체했다. 비용을 제한하기 위해 각 source 프레임의 고정 균등 512 query를 상대 프레임 전체 target에 비교한다. float32 검색 결과의 표본 통계이며 전체 source 통계나 물리적 대응 GT가 아니다. 주 FoV 손실의 float64 고정 영상 대응은 이 검색을 사용하지 않는다.

## C0b — 카메라·장면 제어

순수 회전·평면·평행·동일 관측의 실제 역투영 residual rank와 depth-only rank, 대응 부족 거절을 보조 검증했다. 고정 Depth가 있는 이 문제에서 순수 회전/평면이라는 이유만으로 무조건 불가능하다고 판정하지 않는다.

## C1a — 실내 영상 대응 지원 보완

원래 SIFT C1의 고정 유효 대응은 30/11/16개로 지원 조건에 미달했다. 이 결과와 기준은 보존한다. 대체 특징의 효과를 계산하기 전에 다음 두 방법을 고정한다.

1. ORB: nfeatures=8192, fastThreshold=7, 나머지 설치 버전 기본값.
2. AKAZE: threshold=1e-4, 나머지 설치 버전 기본값.

두 방법 모두 Hamming descriptor, 양방향 ratio 0.75·상호 일치, 같은 F-RANSAC·Depth/confidence gate·track split·지원 기준을 적용한다. ORB→AKAZE 순서에서 **처음 지원 조건을 통과한 방법**만 보완 실험 입력으로 선택하며 기하/validation/GT 점수로 고르지 않는다. 둘 다 실패하면 실제 지원 부족으로 남긴다. 이 사후 보완은 원래 SIFT 계획과 구분한 탐색적 amendment다.
