# P2-001 실패 보고서

2026-11-12, 호스트 GPU에서 실행. 자체 Gaussian Soft Splat의 단일 점 유한차분 검사는 통과했으나, hard front-depth gate(rtol=0.03)를 적용한 81점 평면의 Ray-depth 최적화에서 평균 3D 오차가 **0.2043544930 → 0.2525276896**으로 증가했다. 사전 완료 기준은 초기 오차의 20% 미만이며 이를 충족하지 못했다. 실행 종료 코드 1, 상태 failed다.

실제 E0 렌더링은 이 회차에서 실행되지 않았다. 당시 코드·config 사본과 로그는 `results/pointmap_refinement/tum-freiburg1_desk-P2-20261112-001/stages/P2/artifacts/source/`와 `logs/`에 보존했다. 수치가 감소하지 않은 회차를 성공 결과로 덮어쓰지 않았다. 단계별 history는 이 버전에서 assertion 뒤에 저장하도록 되어 있어 남지 않았으며, 시작/종료 오차는 assertion 로그에서 확인했다.

후속 002는 합성 평면만 gate를 사실상 해제(rtol=1000)하여 RGB 미분과 가림 변경의 영향을 분리했다. 성공 결과는 이 변경 조건에 한정되며, gate가 유일한 실패 원인임을 완전히 증명한 ablation은 아니다. 실패 회차는 [후속 보고서](../tum-freiburg1_desk-P2-20261112-002/report.md)와 함께 해석한다.
