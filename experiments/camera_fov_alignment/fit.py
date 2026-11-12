"""Fit-only coefficient selection; coverage rejection; held-out evaluation."""
from pathlib import Path
import numpy as np
import common as c
import diagnostics as d
import matching


def effect(initial,final,rank_ok,converged,bound_limited,support_ok,coverage_ok):
    if not support_ok:return {'decision':'NOT_ENOUGH_SUPPORT','scientific_improvement':False}
    if not rank_ok:return {'decision':'INCONCLUSIVE_FOV_UNOBSERVABLE','scientific_improvement':False}
    if not converged:return {'decision':'SOLVER_NOT_CONVERGED','scientific_improvement':False}
    if bound_limited:return {'decision':'BOUND_LIMITED','scientific_improvement':False}
    if not initial['validation']['relative_3d']['count']:
        return {'decision':'NO_VALIDATION_SUPPORT','scientific_improvement':False}
    before=initial['validation'];after=final['validation']
    def gain(field):
        a,b=before[field]['median'],after[field]['median']
        return {'absolute':a-b,'fraction':(a-b)/max(a,1e-5),'initial':a,'final':b}
    g3,gz=gain('relative_3d'),gain('relative_z')
    pair3=True;pairz=True
    for a,b in zip(before['pairs'],after['pairs']):
        assert a['pair']==b['pair']
        for field in ['relative_3d','relative_z']:
            worse=(b[field]['median']-a[field]['median'])/max(a[field]['median'],1e-5)>.01+1e-12
            if field=='relative_3d':pair3&=not worse
            else:pairz&=not worse
    pass3=g3['fraction']>=.05 and g3['absolute']>=1e-5 and pair3 and coverage_ok
    passz=pass3 and gz['fraction']>=.05 and gz['absolute']>=1e-5 and pairz and after['z_inlier_1pct']>=before['z_inlier_1pct']-1e-12
    return {'decision':'DEPTH_ALIGNMENT_IMPROVED' if passz else 'INTERNAL_3D_IMPROVED' if pass3 else 'EFFECT_NOT_ESTABLISHED',
        'scientific_improvement':bool(pass3),'depth_axis_improvement':bool(passz),
        'validation_3d_gain':g3,'validation_z_gain':gz,'per_pair_3d_guard_pass':bool(pair3),
        'per_pair_z_guard_pass':bool(pairz)}


def execute(stage,data,matches,support,dimension,out,diagnostic=False,candidate_policy='irls_only'):
    out.mkdir(parents=True,exist_ok=True)
    train=matching.subset(matches,~matches['validation'])
    a,b,w,ids=c.build_system(data,train)
    rank=c.rank_info(a if dimension==6 else a.sum(-1,keepdims=True))
    support_ok=support['passed']
    baseline=d.geometry(data,matches,np.ones(6))
    reference=d.overlap_reference(data)
    history=[{'iteration':0,'beta':np.ones(dimension).tolist(),'loss':baseline['fit'].get('huber_data_loss',0.),
        'data_loss':baseline['fit'].get('huber_data_loss',0.),'prior_loss':0.}]
    converged=False;attempted=False
    if rank['identifiable'] and (support_ok or diagnostic):
        raw_beta,history,converged=c.solve_irls(a,b,w,dimension)
        attempted=True
    else:raw_beta=np.ones(dimension)
    # Sensitivity is training-only and does not change any setting.
    sensitivity=[]
    aa=a if dimension==6 else a.sum(-1,keepdims=True)
    for variable in range(dimension):
        curve=[]
        for value in np.linspace(c.LOW,c.HIGH,21):
            candidate=np.ones(dimension);candidate[variable]=value
            curve.append({'beta':float(value),'data_loss':float(w@c.huber(np.linalg.norm(aa@candidate+b,axis=1)))})
        sensitivity.append({'variable':variable,'curve':curve})
    c.json_write(out/'sensitivity.json',sensitivity)
    if candidate_policy=='fixed_segment17' and attempted:
        # Pre-fixed alpha grid. It uses fit loss and fixed coverage, never validation/GT.
        for index,alpha in enumerate(np.linspace(0.,1.,17)):
            coefficient=1+alpha*(raw_beta-1)
            data_loss=float(w@c.huber(np.linalg.norm(aa@coefficient+b,axis=1)))
            prior_loss=float(.001*np.mean((coefficient-1)**2))
            history.append({'iteration':100+index,'candidate_kind':'fixed_segment',
                'alpha':float(alpha),'beta':coefficient.tolist(),
                'loss':data_loss+prior_loss,'data_loss':data_loss,'prior_loss':prior_loss})
    else:assert candidate_policy=='irls_only' or not attempted
    candidates=[]
    for row in history:
        beta=np.repeat(row['beta'][0],6) if dimension==1 else np.array(row['beta'])
        cov=d.coverage(data,beta,reference)
        candidates.append(row|{'beta_6':beta.tolist(),'coverage':cov})
    feasible=[r for r in candidates if r['coverage']['passed']]
    assert feasible
    selected=min(feasible,key=lambda r:r['loss'])
    beta=np.array(selected['beta_6'])
    proposed=np.repeat(raw_beta[0],6) if dimension==1 else raw_beta.copy()
    proposed_cov=d.coverage(data,proposed,reference)
    bound_limited=bool(np.any((proposed-c.LOW<1e-4)|(c.HIGH-proposed<1e-4)))
    after=d.geometry(data,matches,beta)
    result=effect(baseline,after,rank['identifiable'],converged,bound_limited,support_ok,selected['coverage']['passed'])
    if diagnostic:
        result['unqualified_decision']=result['decision']
        result['decision']='LOW_SUPPORT_DIAGNOSTIC_ONLY'
        result['scientific_improvement']=False
    metrics=result|{'dimension':dimension,'support':support,'rank':rank,'candidate_policy':candidate_policy,
        'optimization_attempted':attempted,'converged':converged,
        'diagnostic_override':diagnostic,'selected_beta':beta.tolist(),
        'proposed_beta':proposed.tolist(),'selected_iteration':selected['iteration'],
        'proposed_bound_limited':bound_limited,'coverage_rejected':not proposed_cov['passed'],
        'proposed_coverage':proposed_cov,'selected_coverage':selected['coverage'],
        'geometry_before':baseline,'geometry_after':after,'parameter_table':d.parameter_table(data,beta),
        'geometry_proposed':d.geometry(data,matches,proposed),
        'proposed_parameter_table':d.parameter_table(data,proposed),'candidate_history':candidates}
    # Always preserve the actual unconstrained-in-coverage fitted candidate separately.
    before_xyz,before_k=d.export_map(data,np.ones(6),out/'initial',False)
    xyz,k=d.export_map(data,beta,out/'selected')
    if not np.array_equal(proposed,beta):
        proposed_xyz,proposed_k=d.export_map(data,proposed,out/'proposed_not_selected',False)
        proposal_rows,_,_=d.render(data,proposed_xyz,proposed_k,out/'projections_proposed_not_selected')
        c.panel(stage.path/f'artifacts/figures/{dimension}var_proposed_NOT_SELECTED.png',
            [[data['rgb'][i],proposal_rows[i][1],proposal_rows[i][2]] for i in range(3)],
            ['Input RGB native','Proposed RGB NOT SELECTED','Proposed source NOT SELECTED'])
    before_rows,_,_=d.render(data,before_xyz,before_k,out/'projections_initial')
    after_rows,_,projection=d.render(data,xyz,k,out/'projections_selected')
    rgb_rows=[[data['rgb'][i],before_rows[i][1],after_rows[i][1]] for i in range(3)]
    source_rows=[[before_rows[i][2],after_rows[i][2]] for i in range(3)]
    prefix=f'{dimension}var'
    c.panel(stage.path/f'artifacts/figures/{prefix}_rgb_comparison.png',rgb_rows,
        ['Input RGB native','Initial projection','Selected projection'])
    c.panel(stage.path/f'artifacts/figures/{prefix}_source_comparison.png',source_rows,
        ['Initial frame source','Selected frame source'])
    metrics['projection']=projection
    metrics['dense_geometry']=d.dense_geometry(data,xyz,k,out/'dense')
    metrics['nearest_secondary']=d.nearest_secondary(data,xyz)
    # Verify source image, depth, pose and original file identities did not change.
    current=c.load_data(data['dataset'])
    for name in ['depth','rgb','k','e','pose_enc']:
        assert np.array_equal(current[name],data[name]),name
    metrics['frozen_input_arrays_unchanged']=True
    c.json_write(out/'fit.json',metrics)
    np.savez_compressed(out/'parameters.npz',selected_beta=beta,proposed_beta=proposed,
        initial_k=data['k'],selected_k=k,extrinsics=data['e'],centers=data['centers'])
    stage.log('fit_finished',dimension=dimension,decision=metrics['decision'],
        selected_iteration=selected['iteration'],converged=converged,
        selected_beta=beta.tolist(),proposed_beta=proposed.tolist())
    return metrics


def report_text(stage,metrics):
    d3=metrics['geometry_before']['validation']['relative_3d']
    d3after=metrics['geometry_after']['validation']['relative_3d']
    z=metrics['geometry_before']['validation']['relative_z']
    za=metrics['geometry_after']['validation']['relative_z']
    table='\n'.join(f'| {r["camera"]} | {r["beta_xy"]} | {r["fx_fy_before"]} | {r["fx_fy_after"]} | {r["fov_wh_after_degree"]} |'
        for r in metrics['parameter_table'])
    return f'''# {stage.code} FoV {metrics['dimension']}변수 보정

실행 `{stage.run_id}`. **{metrics['decision']}**.

- 지원 조건 통과: {metrics['support']['passed']}; 데이터 rank: `{metrics['rank']}`.
- 실제 최적화 실행: {metrics['optimization_attempted']}; 수렴: {metrics['converged']}.
- 선택 iteration: {metrics['selected_iteration']}; 제안값 경계 제한: {metrics['proposed_bound_limited']}; 제안값 coverage 거절: {metrics['coverage_rejected']}.
- 최종 선택 β: `{metrics['selected_beta']}`.
- 실제 solver 제안 β: `{metrics['proposed_beta']}`. 선택되지 않은 제안도 별도 PLY/NPZ로 보존한다.
- 입력 원본 Depth/RGB/pose 및 원본 K 불변 검사 통과. 보정 K는 별도로 저장했다.

| 고정 validation 지표 | 초기 | 선택 결과 |
| --- | --- | --- |
| 양방향 상대 3D median | {d3.get('median')} | {d3after.get('median')} |
| 양방향 상대 Z median | {z.get('median')} | {za.get('median')} |

| camera | βx/βy | 초기 fx/fy | 보정 fx/fy | 보정 수평/수직 FoV degree |
| --- | --- | --- | --- | --- |
{table}

![동일 해상도 RGB 전후](figures/{metrics['dimension']}var_rgb_comparison.png)

![프레임 출처 전후](figures/{metrics['dimension']}var_source_comparison.png)

지원 부족의 원래 계획에서는 β=1을 유지하며 효과를 주장하지 않는다. diagnostic_override가 true인 보조 실행은 관측 부족의 탐색적 수치 진단이다. 동일 입력 3장의 일부 대응을 보류했으며 새로운 카메라나 실제 3D 정확도의 검증은 아니다.
'''


def latest(code,dataset):
    candidates=sorted((c.ROOT/'results/camera_fov_alignment').glob(f'{dataset}-{code}-*/stages/{code}'))
    completed=[p for p in candidates if (p/'manifest.json').exists() and __import__('json').loads((p/'manifest.json').read_text())['status']=='completed']
    assert completed,(code,dataset)
    return completed[-1]


def run_indoor(code,dimension,diagnostic=False):
    import json
    data=c.load_data('tum-freiburg1_desk');parent=latest('C1',data['dataset'])
    baseline_path=parent/'artifacts/baseline'
    matches=matching.load(baseline_path/'matches/matches.npz')
    support=json.loads((baseline_path/'baseline.json').read_text())['support']
    stage=c.Stage(code,data['dataset'],parents=[parent],extra={'diagnostic_override':diagnostic,
        'dimension':dimension,'matching_parent':str(baseline_path)})
    try:
        metrics=execute(stage,data,matches,support,dimension,stage.path/'artifacts/fit',diagnostic)
        stage.finish(metrics,report_text(stage,metrics))
    except Exception as error:
        stage.fail(error);raise
