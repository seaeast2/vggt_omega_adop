# P0 실행 이력

P0는 환경 및 최소 추론의 실행 가능성을 검증한다. 기하 정확도 개선을 평가하지 않는다.

| Run ID | 입력 | 실행 상태 | 판단 | 보고서 |
| --- | --- | --- | --- | --- |
| smoke-P0-20261112-001 | TUM freiburg1_desk RGB 4장 중 첫 2/3/4장 | stopped | 환경·전처리 통과, 체크포인트 인증 차단으로 추론 미완료 | [중간 기록](smoke-P0-20261112-001/progress.md), [보고서](smoke-P0-20261112-001/report.md) |
| smoke-P0-20261112-002 | 동일 RGB·전처리 설정 | stopped | 로그인 확인, HTTP 403 / 모델 접근 승인 대기 | [중간 기록](smoke-P0-20261112-002/progress.md), [보고서](smoke-P0-20261112-002/report.md) |

재현 코드와 명령은 [P0 실행 안내](../../../../experiments/pointmap_refinement/P0/README.md)를 따른다. 공식 모델 접근 승인 후에는 새 Run ID에서 추론을 진행하고, 이전 실행의 입력을 재사용하면 원본 Manifest와 해시를 기록한다.
