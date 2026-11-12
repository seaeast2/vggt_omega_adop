# E3b — E0b 순차 평균 융합과 기존 E3 결과 비교

저장된 E0/E0b/E3 selected/E3 last를 같은 예측 카메라·해상도·GT 깊이 스케일·평가 영역으로 비교한다. E0b를 시작점으로 새 E3 학습을 수행하는 실험은 아니다. E3 selected=step 0(E2 초기)임을 좌표로 검증하며, 실제 이동된 last=step 200을 별도로 평가한다.

```bash
OPENBLAS_NUM_THREADS=2 .venvs/p0-py311/bin/python \
  experiments/pointmap_refinement/E3b/run.py \
  --run-id tum-freiburg1_desk-E3b-20261112-001
```

호스트 CPU만 사용하며 새 Run ID를 지정한다. 입력과 소스 도우미를 해시로 연결한다. E1의 native front_map으로 깊이를 다시 투영하고 E3의 저장된 native 깊이·기존 공통 마스크 RMSE/AbsRel을 먼저 재현한다. 기존 E3의 GT 스케일 1개를 그대로 적용하며 E0b에 새로 맞추지 않는다. E3 초기 GT 고정 영역에서 결과별 누락/coverage를 보고하고, 네 결과 모두 유효한 공통 영역에서 RMSE/AbsRel을 같은 분모로 계산한다. 결과별 covered-only 지표는 서로 다른 표본이므로 주 비교에 사용하지 않는다.

색상 비교에는 E0a의 같은 최근접 픽셀 z-buffer와 원본 출처 팔레트를 사용한다. 실제 관측→대표점 매핑으로 출처 비트맵을 다시 만들고, 서로 다른 원본 프레임 색의 동일 가중치 평균으로 PLY/2D를 저장한다. owner 팔레트 PLY도 별도 저장하지만 E0b는 최신 카메라, E3는 E2에서 선택한 owner여서 같은 의미로 평가하지 않는다. 이미지 색을 점에 부여하거나 RGB 재현 오차를 새로 비교하지 않는다.

GT 깊이/오차 그림은 동일 표시 범위를 쓴다. 점 수·그룹 출처 수·누락 영역을 같이 보고하며 색 혼합이나 점 수 감소를 기하 정확도 증거로 쓰지 않는다. 동일 입력 영상의 GT 깊이는 독립 시점·전체 3D·벽 ROI/두께 검증이 아니다. 새 보정이나 모델 선택에 GT를 사용하지 않는다.
