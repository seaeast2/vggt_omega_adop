"""Auxiliary coverage-feasible candidate sampling, after original C4 is preserved."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import fit
import matching


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',required=True,
        choices=['hkairport01','amtown01']);args=parser.parse_args()
    data=c.load_data(args.dataset);parent=fit.latest('C4',args.dataset)
    base=parent/'artifacts/baseline'
    support=json.loads((base/'baseline.json').read_text())['support']
    matches=matching.load(base/'matches/matches.npz')
    stage=c.Stage('C4a',args.dataset,parents=[parent],extra={
        'exploratory_amendment':True,'candidate_policy':'fixed_segment17',
        'alphas':[i/16 for i in range(17)],'selection':'fit loss plus original coverage only; no GT/validation selection'})
    try:
        metrics=fit.execute(stage,data,matches,support,6,stage.path/'artifacts/fit',candidate_policy='fixed_segment17')
        metrics['exploratory_amendment']=True
        metrics['original_C4_preserved']=str(parent)
        report=fit.report_text(stage,metrics)+'''

## C4a 해석

원래 C4를 보존한 뒤 추가한 탐색적 실행이다. 초기값→solver 제안의 선분을 α=0,1/16,…,1의 고정 17개 값으로 평가했다. 선택은 같은 fit 목적함수와 같은 coverage 기준만 사용했다. 기존 대응/split·손실·범위·허용 coverage는 변경하지 않았다. validation을 보고 후보를 고르지 않았지만 원래 결과 확인 후의 보완이므로 독립적인 확인 실험으로 해석하지 않는다.
'''
        stage.finish(metrics,report)
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
