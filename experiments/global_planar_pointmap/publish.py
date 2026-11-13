"""Publish ONLY requested I-series experiment code and lightweight reports."""
import argparse, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def publish(code):
    paths=['experiments/global_planar_pointmap',f'docs/experiments/global_planar_pointmap/{code}']
    if not (ROOT/paths[1]).exists():return
    subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True)
    changed=subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode
    if changed:
        subprocess.run(['git','commit','-m',f'Run {code} global planar pointmap experiment and preserve provenance'],cwd=ROOT,check=True)
        subprocess.run(['git','push','origin','HEAD'],cwd=ROOT,check=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('codes',nargs='+');args=p.parse_args()
    for code in args.codes:
        if not code.startswith('I') or not code[1:].isalnum():raise ValueError('I-series codes only')
        publish(code)
