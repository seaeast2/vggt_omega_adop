"""Publish ONLY requested I-series experiment code and lightweight reports."""
import argparse, subprocess, json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def publish(code):
    paths=['experiments/global_planar_pointmap',f'docs/experiments/global_planar_pointmap/{code}']
    if not (ROOT/paths[1]).exists():return
    subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True)
    changed=subprocess.run(['git','diff','--cached','--quiet','--',*paths],cwd=ROOT).returncode
    if changed:
        subprocess.run(['git','commit','--only','-m',f'Run {code} global planar pointmap experiment and preserve provenance','--',*paths],cwd=ROOT,check=True)
        subprocess.run(['git','push','origin','HEAD'],cwd=ROOT,check=True)
def summary():
    paths=['README.md','docs/vggt_omega_global_planar_pointmap_experiment_plan.md']
    paths += [f'docs/experiments/global_planar_pointmap/{name}' for name in ['index.md','canonical_results.json','excluded_runs.json','holdout_perturbation_audit.json','visual_review.json','environment_snapshot.json','final_audit.json','provenance_amendment.json']]
    subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True)
    if subprocess.run(['git','diff','--cached','--quiet','--',*paths],cwd=ROOT).returncode:
        subprocess.run(['git','commit','--only','-m','Report I0-I9 canonical results, failed visibility and preserved bundles','--',*paths],cwd=ROOT,check=True)
    subprocess.run(['git','push','origin','HEAD'],cwd=ROOT,check=True)
    local=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    remote=subprocess.check_output(['git','ls-remote','origin',f'refs/heads/{branch}'],cwd=ROOT,text=True).split()[0]
    assert local==remote,(local,remote)
    result=dict(local_commit=local,remote_commit=remote,branch=branch,matches=True,verified_at=datetime.now(timezone.utc).isoformat())
    (ROOT/'results/global_planar_pointmap/publication.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('codes',nargs='*');p.add_argument('--summary',action='store_true');args=p.parse_args()
    for code in args.codes:
        if not code.startswith('I') or not code[1:].isalnum():raise ValueError('I-series codes only')
        publish(code)
    if args.summary:summary()
