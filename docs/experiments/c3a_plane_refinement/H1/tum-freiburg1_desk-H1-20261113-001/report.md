# H1 원본 영상 벽 분할

원본 640×480 RGB 세 장에서 `wall.` / box 0.25 / text 0.2로 GroundingDINO Swin-T와 SAM ViT-H를 실행했다. 마스크를 nearest-neighbor로 512×384에 옮겼다. 원시 후보·박스·점수·SAM embedding·logit을 동결했으며 보정 점군을 사용하지 않았다.

GroundingDINO는 공식 IDEA-Research HF 변환 가중치를 Transformers 4.57.1의 순수 PyTorch 경로로 실행했다. SAM은 원본 공식 구현과 ViT-H 가중치다. 라이브러리 설치 과정에서 huggingface_hub가 2.4.0에서 0.36.2로 변경되었다. 실제 checkpoint SHA256·버전·시간·GPU peak memory는 model_provenance.json에 있다. 점수는 평면성 확률이 아니다. 자동 누락·과포함은 다음 RGB 검토에 기록한다.

실행 Stage: `results/c3a_plane_refinement/tum-freiburg1_desk-H1-20261113-001/stages/H1`. 대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. GT 기하 정확도는 평가하지 않았다.
