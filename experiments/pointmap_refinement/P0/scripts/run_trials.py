"""Execute isolated P0 processes and compare the repeated three-frame baseline."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--stage', type=Path, required=True)
a = p.parse_args()
stage = a.stage
assert json.loads((stage/'evaluation/checkpoint.json').read_text())['verified']
trials = [('max_size',3,'max_size_n03'),('max_size',2,'max_size_n02'),('max_size',4,'max_size_n04'),('balanced',2,'balanced_n02'),('balanced',3,'balanced_n03'),('balanced',4,'balanced_n04'),('max_size',3,'max_size_n03_repeat')]
rows=[]
def gpu():
    return subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
for mode,n,name in trials:
    before=gpu()
    cmd=[sys.executable,'experiments/pointmap_refinement/P0/scripts/infer.py','--checkpoint','checkpoints/vggt_omega_1b_512.pt','--frames',str(stage/'artifacts/data/frames.json'),'--mode',mode,'--count',str(n),'--output',str(stage/'artifacts/inference'/name)]
    with (stage/'logs'/f'{name}.log').open('x') as f:
        result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    row={'trial':name,'command':cmd,'exit_code':result.returncode,'gpu_before_mib':before,'gpu_after_mib':gpu()}
    path=stage/'artifacts/inference'/name/'metrics.json'
    if path.exists():row.update(json.loads(path.read_text()))
    rows.append(row)
    (stage/'evaluation/trials.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(name,result.returncode,flush=True)
with np.load(stage/'artifacts/inference/max_size_n03/vggt_omega_raw.npz') as x, np.load(stage/'artifacts/inference/max_size_n03_repeat/vggt_omega_raw.npz') as y:
    comparison={k:{'max_abs_difference':float(np.max(np.abs(x[k]-y[k]))),'allclose':bool(np.allclose(x[k],y[k],rtol=1e-5,atol=1e-6))} for k in x.files}
(stage/'evaluation/reproducibility.json').write_text(json.dumps({'rtol':1e-5,'atol':1e-6,'arrays':comparison},indent=2)+'\n')
assert all(row['exit_code']==0 for row in rows)
assert all(row['allclose'] for row in comparison.values())
