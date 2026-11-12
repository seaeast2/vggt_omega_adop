# P2 중간 기록

1. 호스트 CUDA 및 PyTorch3D 미설치를 확인하고 최소 Soft Splat 대안을 구현했다.
2. 001은 단일 점 검사를 통과했으나 hard gate 평면 회복에 실패했다.
3. 001 코드·로그를 보존하고 002에서 평면의 visibility 영향을 분리했다.
4. 단일 점·평면 XYZ 유한차분과 합성 3D 회복을 통과했다.
5. Hard visibility 경계가 불연속임을 별도 검출했다.
6. E0 부분 점군의 3시점 RGB·Depth·Coverage를 저장하고 원본 RGB와 초기 비교했다.
7. 실제 XYZ Gradient는 유한하고 0이 아니었으며 실제 좌표는 갱신하지 않았다.
8. GPU 메모리 반환과 저장 결과 재로딩을 확인했다.

[보고서](report.md) 참조.
