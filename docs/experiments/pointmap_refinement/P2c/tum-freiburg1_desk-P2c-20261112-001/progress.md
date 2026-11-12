# P2c 중간 기록

- 실행 전 네 렌더 변형·temperature·유한차분 tolerance·10회 Adam·E3b 재실행 허용 조건을 고정했다.
- 기존 E3b의 E0b 초기점·원본 RGB·active 135,193개·고정 마스크를 재사용한다. 실제 GT와 기존 결과는 변경하지 않는다.
- 합성 가림·stencil 경계·평면 회복과 실제 전체 점군 방향 미분 및 짧은 실제 이동을 단계별 저장한다.

- 호스트 GPU에서 실행 완료. 약한 주변 전경·강한 전경 가림 제어, float64 정수 stencil 경계 미분과 평면 미분·깊이 회복을 통과했다. 평면 평균 3D 오차는 0.204354→0.000765로 감소했다.
- 실제 E0b 341,325점·active 135,193개에서 compact_soft의 float64 방향 유한차분은 Autograd와 상대 오차 3.26e-9~3.60e-7로 일치했다. float32의 세 epsilon에서도 실제 +감소 방향 손실이 감소했다.
- 10회 Adam 후 legacy 0.059157→0.071562, normalized_hard 0.053513→0.055449, compact_hard 0.047410→0.047693, compact_soft 0.042625→0.042087이었다. compact_soft는 10회 모두 손실이 감소했고 고정 마스크 spatial-support 감소가 없었다.
- compact_soft에서 실제 133,555점이 이동했으며 별도 PLY/NPZ에 보존했다. 실제 GT·200회 E3b 학습은 수행하지 않았다. ready_for_E3b=true는 이번 제한된 검증의 통과 판정이다.
- 초기 네 변형과 compact_soft 10회 전후 패널을 직접 확인했다. 코드·설정·보고서·소규모 그림을 커밋·푸시하며 기존 P2/E3b는 유지한다.
