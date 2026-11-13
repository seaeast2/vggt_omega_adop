# G 계열 구현·검증 기록

원래 계획의 기준을 소급 변경하지 않고 실행 시 선택과 한계를 기록한다.

- G0a: production solver는 SciPy `least_squares(jac="3-point")`다. autodiff 구현으로 부르지 않는다. affine P 미분, pinhole quotient의 analytic 미분, 중앙/전방 차분 비교 및 합성 8변수 복구를 별도 확인했다.
- solver 한도: SciPy `max_nfev=200`은 residual 기준이며 내부 Jacobian 차분 호출은 별도다. `callback`의 수용 iterate와 종료값을 후보로 저장했다. 거절 trial/finite-difference query는 selected 후보가 아니다. 별도 200 iteration 중단 callback은 구현하지 않았으며 실제 nfev/njev를 기록했다.
- 선 대응: 원본 RGB를 보고 LSD 선분의 구조 대응을 annotation했다. 원본 구간 3개/추가 구간 2개 구조로 사전 지원 기준 미달이다. 자동 matcher 교체나 지원 기준 완화는 하지 않았다. 모든 선 관련 효과는 low-support 진단이다.
- G4: fit 타일의 모든 유효 픽셀로 공통 scale을 동결한 뒤, 계산용 prior residual은 고정 4pixel stride로 읽었다. validation 타일은 제외했다. MoGe-2는 metric GT가 아니다.
- G5a: 고정 100/110/120 구간의 실제 존재·rgb.txt index·RGB를 확인해 joint inference했다. 이 구간의 기준 β는 해당 구간의 점 대응으로 C3a 방법을 적용해 구했다. 이전 구간의 β를 복사하지 않았다. 벽이 보이지 않아 벽 평가는 미실시다.
- G6: 실제 wall-camera0 ROI의 B1 평면과 관측 ID를 고정했다. ROI projection은 가림·다른 표면을 포함할 수 있어 벽 전체의 GT 정합으로 해석하지 않는다.
- 이전 실험 종료 이력은 유지한다. 이번 실험은 사용자가 새로 승인한 G 계열이다. 자유 정점/RGB 최적화나 색·깊이 융합을 추가하지 않았다.
