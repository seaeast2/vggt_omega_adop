# P2 — Minimal Soft Splat Renderer 및 Gradient 검증

PyTorch3D가 설치돼 있지 않아 계획서의 대안인 자체 Gaussian Soft Splat을 사용했다. 공식 ADOP나 PyTorch3D의 구현을 재현한 것으로 주장하지 않는다.

호스트 GPU에서 P0 전용 Python/PyTorch 환경으로 실행한다. 새 Run ID가 필요하다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P2/run.py \
  --run-id tum-freiburg1_desk-P2-20261112-002
.venvs/p0-py311/bin/python experiments/pointmap_refinement/P2/verify.py \
  --stage results/pointmap_refinement/tum-freiburg1_desk-P2-20261112-002/stages/P2
```

`renderer.py`는 OpenCV 투영, 고정 픽셀 반경 Gaussian, 최근접 깊이의 hard gate, alpha=`1-exp(-sum(weight))`, 정규화 고정 RGB 합성과 검은 배경을 사용한다. 출력은 RGB·가중 깊이·alpha다. 유효 Coverage는 alpha≥0.5다. 픽셀 후보 선택과 가림 판정은 detached이며, 경계의 변화까지 미분하지 않는다.

001의 hard gate 평면 최적화가 3D 오차 회복에 실패해 보존했다. 002에서는 합성 평면만 깊이 gate를 사실상 비활성화(rtol=1000)하고, 별도 hard gate 검사 및 실제 점군 렌더링에는 rtol=0.03을 사용했다. 001은 성공 설정으로 덮어쓰지 않는다.

합성 단일 점/평면 유한차분, self-ray 퇴화 및 타 카메라 시차, 합성 평면의 3D 회복, hard visibility 불연속, 실제 E0 부분 점군의 고정 마스크 RGB 비교·Gradient를 확인한다. 실제 좌표는 갱신하지 않는다. 유한차분·3D 회복·저장 검사 통과와 실패 기록/보고서 작성 후 완료한다.

실제 입력은 E0 전체 589,824점 중 각 프레임의 u/v가 4로 나눠 나머지 2인 36,864점이다. 같은 점 집합을 모든 카메라가 참조한다. 128×96 참조 RGB는 INTER_AREA로 축소하고 K는 centre-based affine으로 변환한다. PSNR은 초기 alpha 마스크 및 전체 픽셀을 분리해 보고한다. 재현 상세·제한은 [P2 보고서](../../../docs/experiments/pointmap_refinement/P2/README.md)를 따른다.
