# 일반 VGGT 육안 비교

사용자 요청으로 FoV 보정·융합 방법을 종료하고 별도 원본 VGGT 비교 파일을 생성했다. 기존 [C 계열 결과](../camera_fov_alignment/index.md)를 보존한다.

| 코드·실행 | 입력 | 상태·보고서 |
| --- | --- | --- |
| V0 `tum-freiburg1_desk-V0-20261113-001` | 실내 원본 30/40/50, 3장 공동 추론 | [저장 단계 실패·이력 보존](V0/tum-freiburg1_desk-V0-20261113-001/report.md) |
| V0 `tum-freiburg1_desk-V0-20261113-002` | 실내 원본 30/40/50, 3장 공동 추론 | [PLY 생성·검증 완료](V0/tum-freiburg1_desk-V0-20261113-002/report.md) |

주 비교 파일은 `vggt_depth_rgb.ply`, 층 분리 관찰용은 `vggt_depth_frames.ply`다. [전체 PLY 경로·크기·해시](V0/tum-freiburg1_desk-V0-20261113-002/ply_files.json)를 보존했다. 각 geometry 609,168점이다. 일반 VGGT 처리 격자는 518×392, 기존 Omega는 512×384이며 좌표계/scale을 강제로 맞추지 않았다. GT 정확도·모델 우열은 판정하지 않았다.
