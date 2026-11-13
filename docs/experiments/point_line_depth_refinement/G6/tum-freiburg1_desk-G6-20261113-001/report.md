# G6 점·선·깊이 제약 종합 결과

G0~G6 및 G0a/G5a 실행을 마쳤다. **실행 완료와 효과 검증은 구분한다.** 원본 실내의 점 대응과 선 구조가 적어 모든 효과 판정은 탐색적이다.

주 기준선은 사용자가 육안으로 좋게 관찰한 C3a proposed이며 validation 상대 3D median은 0.00886997118721421다.

| 군 | 3D 변화(B1 대비) | Z 변화(B1 대비) | FoV 경계 | 정합 개선 기준 충족 |
| --- | --- | --- | --- | --- |
| G2 F-P | +0.00% | +0.00% | False | False |
| G2 F-PL | -14.53% | -23.83% | True | False |
| G2 F-PZ | +2.28% | +0.71% | False | False |
| G2 F-PLZ | -14.05% | -23.53% | True | False |
| G3 D-P | -10.13% | -13.73% | False | False |
| G3 D-PL | -19.95% | -2.54% | True | False |
| G3 D-PZ | -15.34% | -15.49% | False | False |
| G3 D-PLZ | -20.08% | +0.96% | True | False |
| G4 D-P+E | -11.95% | -5.86% | False | False |
| G4 D-PLZ+E | -15.69% | +19.09% | True | False |

변화의 양수는 오차 감소다. 선 제약 군은 허용 FoV 경계에 도달했고, 이 소수 선·가중치에서 추가 제약의 일관된 우위는 확인하지 못했다. 이는 PLY 전체 표면의 육안 품질이 악화됐다는 판정이 아니다. 제안값을 모두 보존했으므로 같은 시점·단면에서 직접 확인할 수 있다.

G4는 공식 `Ruicheng/moge-2-vitl` 모델을 동일 RGB 3장에 각각 추론한 prior를 사용했다. GT가 아니며 카메라별 독립 scale 정렬은 하지 않았다. G5는 β=1 초기값 8군과 가중치 민감도 12군을 실행했다. G5a는 고정 100/110/120 구간을 새로 공동 추론하고 8군을 비교했다. 새 구간의 벽 ROI는 보이지 않아 벽 정합은 미평가다.

PLY 빠른 비교 디렉토리: `results/point_line_depth_refinement/ply_review/`. 이 경로는 원본 결과를 가리키는 상대 symlink이며 각 파일의 실제 경로·SHA256은 evaluation/ply_inventory.json에 기록했다. RGB·출처색과 initial/proposed/selected/last를 구분한다.

G0a에서 numerical three-point Jacobian을 쓰는 구현 변경과 analytic 투영 Jacobian 검증을 기록했다. 외부 prior의 fixed 4px stride는 scale 동결 후 계산량을 제한하는 변경이다. GT 평가·자유 깊이맵·자세 최적화·융합·연속 SLAM은 실행하지 않았다.


실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G6-20261113-001/stages/G6`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
