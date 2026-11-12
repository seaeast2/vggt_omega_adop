"""Frozen original-SIFT protocol on each pre-existing UAVScenes raw bundle."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import baseline
import fit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',required=True,
        choices=['hkairport01','amtown01']);args=parser.parse_args()
    data=c.load_data(args.dataset)
    stage=c.Stage('C4',data['dataset'],parents=[data['parent']],extra={
        'transfer_protocol':'original SIFT C1/C2/C3 frozen; no indoor-specific alternative features'})
    try:
        matches,base=baseline.prepare(stage,data,stage.path/'artifacts/baseline')
        one=fit.execute(stage,data,matches,base['support'],1,stage.path/'artifacts/arms/C2')
        six=fit.execute(stage,data,matches,base['support'],6,stage.path/'artifacts/arms/C3')
        metrics={'decision':six['decision'],'baseline':base,'common_1var':one,
            'per_camera_6var':six,'scientific_improvement':six['scientific_improvement'],
            'transfer_not_unseen_generalization':True}
        report=baseline.report_text(stage,base)+'\n\n'+fit.report_text(stage,one)+'\n\n'+fit.report_text(stage,six)
        stage.finish(metrics,report)
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
