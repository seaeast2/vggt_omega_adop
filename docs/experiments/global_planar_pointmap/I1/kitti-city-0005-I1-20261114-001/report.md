# I1 전체 영상 SAM 후보

고정 semantic prompt와 공식 SAM automatic grid32를 함께 실행했다. 원본 detector query·모든 semantic mask·quality filter 통과 후 NMS 전 automatic RLE와 NMS 후 출력을 별도 보존했다. quality filter 이전의 mask logits는 저장하지 않으며 이 제한을 명시한다. 동일 마스크는 alias로 기록하고 원본 ID는 삭제하지 않았다. 포함/겹침 DAG·uncovered map·원본 관측 ID의 CSR 연결을 저장했다. SAM score는 평면성 확률이 아니다. 수동 camera/ROI/plane 개수 입력은 없다.

Stage: `results/global_planar_pointmap/kitti-city-0005-I1-20261114-001/stages/I1`. GT_NOT_EVALUATED.
