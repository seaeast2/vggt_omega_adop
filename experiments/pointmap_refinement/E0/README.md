# E0 — 보정 전 원본 점군 기준선

P0의 max_size 3장 예측과 P1의 검증된 관측을 읽기 전용으로 재사용한다. 모델 추론·융합·위치 최적화·GT 정확도 평가 없이, 후속 비교에 사용할 기준선과 원본 출처를 고정한다. E1의 F0 평가를 완료한 것으로 취급하지 않는다.

설정은 `config.json`, 환경은 P0의 Python 3.11 및 고정 의존성을 사용한다. 호스트 CPU에서 다음 명령을 실행하며 Run ID는 새 이름으로 지정한다.

```bash
.venvs/p0-py311/bin/python experiments/pointmap_refinement/E0/scripts/run.py \
  --run-id tum-freiburg1_desk-E0-20261112-001
```

부모 Manifest의 완료 상태와 모든 산출물 해시, 원본 예측 해시를 확인한 뒤 원본 NPZ를 복사한다. 프레임별 NPZ·PLY와 전체 관측 PLY를 저장하고 재로딩을 검사한다. 좌표는 임의 모델 월드 스케일이며 미터가 아니다. frame_id/u/v를 보존하며 점의 중복은 제거하지 않는다.

RGB·Depth·Confidence 패널과 orthographic scatter는 정성 진단용이다. 0.5~99.5 분위수 표시 범위는 그림에만 적용한다. 원본 데이터는 자르거나 정규화하지 않는다. Scatter는 마지막 쓰기 순서로 점이 가려지며 실제 카메라 가시성을 구현한 렌더러가 아니다. 해상도·카메라를 맞춘 원본 RGB 대 재렌더링 영상 비교는 P2 이후 범위다.

생성 후 로그·소스 사본·산출물 해시를 Manifest에 기록하고 [E0 보고서](../../../docs/experiments/pointmap_refinement/E0/README.md)를 작성한다. 코드·설정·보고서·소규모 그림을 커밋·푸시하며 모델·데이터·대용량 NPZ/PLY는 기존 Git 제외 정책을 따른다.
