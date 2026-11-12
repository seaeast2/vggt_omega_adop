"""Pre-registered alternative image features after original C1 support failure."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import matching
import diagnostics as d
import numpy as np


def main():
    data=c.load_data('tum-freiburg1_desk')
    stage=c.Stage('C1a',data['dataset'],extra={'amendment':'ORB then AKAZE; first support-passing method only; no geometry/validation-score selection',
        'alternative_detectors':[{'name':'ORB','nfeatures':8192,'fastThreshold':7},
            {'name':'AKAZE','threshold':1e-4}], 'binary_descriptor_norm':'Hamming'})
    try:
        results=[];selected=None
        for detector in ['ORB','AKAZE']:
            out=stage.path/'artifacts'/detector
            matches,report=matching.extract(data,out/'matches',stage,detector)
            support=report['support']
            result={'detector':detector,'matching':report,'support':support,
                'geometry':d.geometry(data,matches,np.ones(6))}
            if len(matches['pair']):
                train=matching.subset(matches,~matches['validation'])
                a,b,w,ids=c.build_system(data,train)
                result['rank_6']=c.rank_info(a)
            c.json_write(out/'baseline.json',result)
            results.append(result)
            if selected is None and support['passed']:selected=detector
        decision='ALTERNATIVE_SUPPORT_READY' if selected else 'NOT_ENOUGH_SUPPORT'
        metrics={'decision':decision,'selected_detector':selected,'alternatives':results,
            'selection_rule':'first support-passing detector in fixed ORB,AKAZE order; geometry not used',
            'original_SIFT_result_preserved':True,'inputs':data['inputs'],
            'scientific_improvement':False,'exploratory_amendment':True}
        table='\n'.join(f'| {r["detector"]} | {p["pair"]} | {p["total"]} | {p["fit"]} | {p["validation"]} | {p["occupied_4x4_cells"]} | {p["passed"]} |'
            for r in results for p in r['support']['pairs'])
        stage.finish(metrics,f'''# C1a 실내 관측 지원 보조 검증

**{decision}**. 원래 SIFT C1은 변경하지 않았다. 보정/GT 효과를 보기 전에 ORB→AKAZE 순서와 설정을 등록했다.

| 특징 | 쌍 | 전체 | fit | validation | 4×4 점유 | 지원 통과 |
| --- | --- | --- | --- | --- | --- | --- |
{table}

선택된 대체 특징: `{selected}`. 선택은 기하 오차가 아닌 고정 지원 조건만으로 수행한다. 사후 지원 보완에 해당하므로 원래 SIFT 계획의 확인 실험과 구분한다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
