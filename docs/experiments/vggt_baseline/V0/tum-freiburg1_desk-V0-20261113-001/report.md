# V0 실행 실패

```text
Traceback (most recent call last):
  File "/home/hlee221212/works/gradresearch/vggt_omega_adop/experiments/vggt_baseline/V0/run.py", line 126, in main
    official_xyz=unproject_depth_map_to_point_map(depth,es,ks)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/hlee221212/works/gradresearch/vggt_omega_adop/thirdparty/vggt/vggt/utils/geometry.py", line 39, in unproject_depth_map_to_point_map
    depth_map[frame_idx].squeeze(-1), extrinsics_cam[frame_idx], intrinsics_cam[frame_idx]
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ValueError: cannot select an axis to squeeze out which has size not equal to one

```

후속 [tum-freiburg1_desk-V0-20261113-002](../tum-freiburg1_desk-V0-20261113-002/report.md)에서 공식 역투영 함수에 마지막 channel 축을 유지한 Depth를 전달해 PLY 생성·검증을 완료했다. 이 최초 실패와 원본 예측은 보존한다.
