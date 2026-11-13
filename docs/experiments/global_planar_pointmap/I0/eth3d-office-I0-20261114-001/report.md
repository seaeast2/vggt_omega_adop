# I0 실패

실패 보존: `eth3d-office-I0-20261114-001`

```text
Traceback (most recent call last):
  File "/home/hlee221212/works/gradresearch/vggt_omega_adop/experiments/global_planar_pointmap/eth3d_laser.py", line 155, in freeze
    result=freeze_split(load(dataset),out/dataset,st)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/hlee221212/works/gradresearch/vggt_omega_adop/experiments/global_planar_pointmap/prepare.py", line 49, in freeze_split
    rec=c.record(p);assert rec['sha256']==frame['sha256'];rows.append(rec)
                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError

```
