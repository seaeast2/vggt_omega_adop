# H0 실행 실패

`tum-freiburg1_desk-H0-20261113-001`

````text
Traceback (most recent call last):
  File "/home/hlee221212/works/gradresearch/vggt_omega_adop/experiments/c3a_plane_refinement/h0.py", line 39, in run
    shared=fit(X,D3,f);assert shared['valid'];pp=np.array(shared['plane']);td,ag,_=depth_gate(D3,q3,np.zeros_like(q3),pp);assert ag.all();joint=q3*td[:,None]
                              ~~~~~~^^^^^^^^^
AssertionError

````
