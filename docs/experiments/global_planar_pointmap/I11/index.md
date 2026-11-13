# I11 — 현재 I10의 TUM GT 정확도

**현재 평면 투영은 두 구간 모두 전체 깊이 MAE와 RMSE를 늘렸다.** I10 출력을 바꾸지 않고 별도의 CPU 평가를 실행했다. 주 구간 retained는 named_OR이고, 추가 구간 retained는 기존 가시성 기준에 따라 initial이다.

TUM `freiburg1_desk`의 RGB 30/40/50 및 100/110/120, 총 6장을 평가했다. initial은 현재 I2 FoV 보정 결과이며 원본 raw pointmap과 구분한다. 깊이는 이미 RGB에 등록된 센서 depth를 사용했다. [TUM 공식 데이터 규약](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats)에 따라 PNG/5000을 m 단위로 읽고 추가 undistortion·1.035 재보정을 하지 않았다.

각 구간의 initial FIT 픽셀에서 구한 단일 median-ratio scale을 모든 비교군에 공통 적용했다. 평가에는 겹치지 않는 기존 I0 validation 및 동일한 유효 GT 마스크를 사용했다. GT를 이용해 재구성·평면을 수정하거나 비교군별 scale·shift를 재추정하지 않았다. 아래 수치는 scale 정렬 후의 camera-Z 정확도다.

| 구간 | 출력 | MAE (cm) ↓ | RMSE (cm) ↓ | AbsRel ↓ |
|---|---|---:|---:|---:|
| desk | initial | 5.3767 | 15.4867 | 0.031066 |
| desk | named_local | 5.5017 | 15.7591 | 0.032047 |
| desk | named_OR | 5.5114 | 15.7612 | 0.032147 |
| desk | retained | 5.5114 | 15.7612 | 0.032147 |
| desk-extra | initial | 2.0196 | 4.8160 | 0.016647 |
| desk-extra | named_local | 2.0777 | 4.9718 | 0.017015 |
| desk-extra | named_OR | 2.1514 | 5.4576 | 0.017986 |
| desk-extra | retained | 2.0196 | 4.8160 | 0.016647 |

주 구간 named_OR의 MAE 증가는 **2.5038%**이고 추가 구간은 **6.5233%**다. 주 구간의 wall MAE는 19.1852→17.4890 cm로 줄었지만, table은 1.5934→2.1769 cm, screen은 2.4672→2.5794 cm로 늘었다. 추가 구간 table은 1.3553→1.5060 cm, screen은 7.5983→14.5140 cm로 늘었다. 영역 이름은 예측 태그이며 의미 GT가 아니다.

GT 깊이 경계를 제외한 공통 보조 마스크에서도 두 구간 모두 악화됐다. mocap pose·공식 권장 ROS default K를 이용한 baseline 공통 Sim(3) 정렬의 대응 3D 오차도 같은 추세다. 보조 3D 평가는 K 근사·센서 등록과 timestamp 차이에 영향을 받으므로 깊이 결과와 별도로 보고했다.

평면 투영에서 제외된 unknown 영역은 좌표가 bitwise 동일하고 GT 오차도 동일하다. 다른 view의 named 지지로 새로 포함된 `rescued_OR`의 유효 validation 표본은 주 구간 **2점**, 추가 구간 **6점**뿐이다. OR 전달 자체의 효과를 독립적으로 결론내릴 수 없다. named_local과 named_OR 사이에는 평면 재추정에 따른 기존 named 영역의 변화도 포함된다.

현재 판단은 **평면화·가시성 보존이 GT 정확도 개선으로 이어지지는 않았다**는 것이다. 추가 구간은 initial 유지가 결과적으로 더 낮은 전체 MAE·RMSE를 보였다. 주 구간 retained 선택은 GT 확인 전의 가시성 판정 그대로 보존했으며 이 평가에서 자동 교체하지 않았다.

## 상세 결과와 이미지

- [tum-freiburg1_desk 상세 보고서](tum-freiburg1_desk-I11-20261113-002/report.md) · [RGB·GT 깊이 오차 비교](tum-freiburg1_desk-I11-20261113-002/figures/depth_error.png)
- [tum-freiburg1_desk-extra 상세 보고서](tum-freiburg1_desk-extra-I11-20261113-002/report.md) · [RGB·GT 깊이 오차 비교](tum-freiburg1_desk-extra-I11-20261113-002/figures/depth_error.png)

[정확한 수치](summary.json) · [출처·검증 기록](audit.json)

재현: `OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/evaluate_gt.py`.

대형 GT 배열·FIT/evaluation/영역 마스크·원본 대응 depth PNG·추정 depth·Sim(3) 표본은 각 I11 stage의 `artifacts/gt/`에, 입력 SHA-256와 대응 timestamp·scale·정렬행렬은 stage 및 이 문서의 run별 JSON에 보존했다. 첫 실행 `-001`은 상속된 GT 주석을 명확히 한 `-002`로 대체했으며 모든 평가 수치는 동일하다. 원래 실행은 삭제하지 않았다.

센서 GT 결측부의 정확도, 의미 소속 정확도, 이상적인 평면/직각 형태 정확도, 전체 시퀀스 SLAM 성능은 이번 평가 대상이 아니다. GT를 이용한 공통 scale/Sim(3) 정렬이 필요했으므로 절대 scale 정확도로 해석하지 않는다.
