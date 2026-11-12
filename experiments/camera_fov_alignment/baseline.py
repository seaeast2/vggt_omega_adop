"""Shared raw baseline preparation used by indoor C1 and outdoor C4."""
from pathlib import Path
import numpy as np
import common as c
import matching
import diagnostics as d


def prepare(stage,data,out):
    out.mkdir(parents=True,exist_ok=True)
    c.json_write(out/'inputs.json',data['inputs'])
    matches,report=matching.extract(data,out/'matches',stage)
    beta=np.ones(6)
    xyz,k=d.export_map(data,beta,out/'maps')
    rows,source_rows,projection=d.render(data,xyz,k,out/'projections')
    c.panel(stage.path/'artifacts/figures/baseline_rgb_source.png',rows,
            ['Input RGB native','Raw projection RGB','Frame source color'])
    c.panel(stage.path/'artifacts/figures/baseline_source_views.png',source_rows,
            ['All sources','Other sources only','Only frame 0','Only frame 1','Only frame 2'])
    metrics={'support':report['support'],'matching':report,'point_count':len(xyz),
        'input_image_shape_wh':[data['depth'].shape[2],data['depth'].shape[1]],
        'geometry':d.geometry(data,matches,beta),'projection':projection,
        'dense_geometry':d.dense_geometry(data,xyz,k,out/'dense'),
        'nearest_secondary':d.nearest_secondary(data,xyz),
        'parameter_table':d.parameter_table(data,beta),
        'coordinates_vs_old_baseline_max_abs':float(np.max(np.abs(xyz-data['reference_xyz']))),
        'wall_roi':'not semantically verified; fixed central spatial ROI only'}
    if len(matches['pair']):
        train=matching.subset(matches,~matches['validation'])
        a,b,w,ids=c.build_system(data,train)
        metrics['rank_6']=c.rank_info(a)
        metrics['rank_1']=c.rank_info(a.sum(-1,keepdims=True))
    else:metrics['rank_6']=metrics['rank_1']={'identifiable':False,'rank':0}
    metrics['decision']='BASELINE_READY' if report['support']['passed'] else 'NOT_ENOUGH_SUPPORT'
    c.json_write(out/'baseline.json',metrics)
    return matches,metrics


def report_text(stage,metrics):
    table='\n'.join(f'| {r["pair"]} | {r["total"]} | {r["fit"]} | {r["validation"]} | {r["occupied_4x4_cells"]} | {r["passed"]} |'
        for r in metrics['support']['pairs'])
    return f'''# {stage.code} 원본 기준선·영상 대응

실행: `{stage.run_id}`. **{metrics['decision']}**.

점 수 {metrics['point_count']:,}, 처리 해상도 {metrics['input_image_shape_wh']}. 카메라·Depth·RGB를 보존하며 융합/최적화하지 않았다.

| 카메라 쌍 | 전체 | fit | validation | 양 영상 4×4 격자 점유 | 지원 통과 |
| --- | --- | --- | --- | --- | --- |
{table}

고정 track·anchor tile 단위 split으로 같은 track이 fit/validation에 동시에 들어가지 않는다. 영상 기반 대응은 대응 GT가 아니다.

- 6변수 rank: `{metrics['rank_6']}`
- 공통 1변수 rank: `{metrics['rank_1']}`
- 원본 저장 좌표와 재역투영 차이: {metrics['coordinates_vs_old_baseline_max_abs']:.3g} 모델 단위.
- nearest 지표는 고정 512 query/프레임과 상대 프레임 전체 target의 정확한 float32 거리다.
- 벽 의미가 검증된 ROI는 확보하지 않았다. 고정 중앙 ROI의 층 통계는 다른 물체/가림도 포함하므로 벽 전용 정확도로 해석하지 않는다.

![원본 RGB·재투영·프레임 출처](figures/baseline_rgb_source.png)

![각 카메라의 출처별 점군](figures/baseline_source_views.png)
'''
