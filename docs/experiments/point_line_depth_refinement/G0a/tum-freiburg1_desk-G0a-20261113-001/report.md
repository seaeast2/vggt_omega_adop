# G0a 비선형·깊이 퇴화 보조 검증

합성 8변수 복구, 투영 미분, 공통 scale 비관측, 단일 선 퇴화, 음의 Z 제어를 통과했다.

```json
{
  "decision": "TECHNICAL_CHECKS_PASSED",
  "synthetic_depth_fov_recovery_max_abs": 2.55351295663786e-15,
  "data_rank": {
    "rank": 8,
    "dimension": 8,
    "singular_values": [
      55.79837141054709,
      32.47844144438067,
      13.379484344390963,
      9.573966635331637,
      5.5990057957062875,
      5.354276926411069,
      5.303987787960135,
      0.6303203516289473
    ],
    "condition": 88.52382961512576,
    "identifiable": true
  },
  "central_vs_forward_max_abs": 1.5003306863548005e-07,
  "analytic_line_projection_jacobian_max_abs": 2.3763074841198772e-12,
  "pure_rotation_common_scale_projection_derivative": 4.693571664001317e-09,
  "single_line_rank": 1,
  "nonpositive_Z_rejected": true,
  "amendment": "Production uses numerical three-point Jacobian, analytically checked projection derivative; not claimed autodiff implementation."
}
```

실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G0a-20261113-001/stages/G0a`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
