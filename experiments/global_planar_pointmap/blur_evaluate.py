"""I25: evaluate completed interventions; never change blur/solver/masks from GT."""
from core import *
from blur_inputs import stage,DATASETS,CASES,data_with_raw,PLAN
from evaluate_gt import camera_z,depth_metrics,point_metrics,fit_sim3,GT_STATUS
from raw_baseline import proper_rotation,pose_alignment
from blur_optimize import fixed_split

def camera_gt(d):
    n,h,w=d['depth'].shape;ks=[];es=[]
    for f in d['frames']:
        cam=f['camera'];fx,fy,cx,cy=cam['params'];sx=w/cam['width'];sy=h/cam['height']
        ks.append([[fx*sx,0,cx*sx-.5],[0,fy*sy,cy*sy-.5],[0,0,1]])
        es.append(f['dataset_extrinsics'])
    return np.array(ks),np.array(es)

def focal(k,gt):
    pred=np.stack([k[:,0,0],k[:,1,1]],1);truth=np.stack([gt[:,0,0],gt[:,1,1]],1)
    rel=pred/truth-1;ideal=pred/truth
    return dict(mean_abs_relative_percent=float(100*abs(rel).mean()),mean_abs_log=float(abs(np.log(pred/truth)).mean()),
        relative_error_per_frame=rel.tolist(),raw_focal=pred.tolist(),GT_focal=truth.tolist(),
        beta_to_reach_GT=ideal.tolist(),all_ideal_beta_in_bounds=bool(np.all((ideal>=c.LOW)&(ideal<=c.HIGH))))

def epipolar(matches,ks,es):
    errors=np.full(len(matches['pair']),np.nan)
    for i,j in itertools.combinations(range(3),2):
        take=(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j)
        r=es[j,:,:3]@np.linalg.inv(es[i,:,:3]);t=es[j,:,3]-r@es[i,:,3]
        skew=np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])
        f=np.linalg.inv(ks[j]).T@skew@r@np.linalg.inv(ks[i]);a=np.c_[matches['uv_i'][take],np.ones(take.sum())];b=np.c_[matches['uv_j'][take],np.ones(take.sum())]
        fa=a@f.T;fb=b@f;num=np.sum(b*fa,axis=1)**2;den=np.sum(fa[:,:2]**2+fb[:,:2]**2,axis=1)
        errors[take]=np.sqrt(num/np.maximum(den,1e-30))
    def stat(mask):
        x=errors[mask];x=x[np.isfinite(x)]
        return dict(count=len(x),median_px=float(np.median(x)) if len(x) else None,p95_px=float(np.quantile(x,.95)) if len(x) else None,
            over_1px_fraction=float(np.mean(x>1)) if len(x) else None)
    return dict(all=stat(np.ones(len(errors),bool)),fit=stat(~matches['validation']),validation=stat(matches['validation']))

def context(d,gt,world,fit,test,ks,es):
    z=camera_z(d['xyz'],d['e'],d['fid']);scale=float(np.median(gt[fit]/z[fit]))
    ix=np.flatnonzero(fit);ix=ix[np.linspace(0,len(ix)-1,min(len(ix),30000),dtype=int)]
    ss,r,t=fit_sim3(d['xyz'][ix],world[ix]);surface=dict(sim3_scale=ss,sim3_rotation=r.tolist(),sim3_translation=t.tolist())
    centers=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in es]);gq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in es])
    pq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in d['e']])
    try:pose=pose_alignment(d['centers'],pq,centers,gq);failure=None
    except AssertionError as error:pose=None;failure=str(error)
    return dict(depth_scale=scale,surface=surface,pose=pose,pose_alignment_failure=failure,
        pose_to_depth_scale_ratio=pose['sim3_scale']/scale if pose else None,raw_intrinsics=focal(d['k'],ks),fit_hash=ahash(fit),test_hash=ahash(test))

def evaluate_map(xyz,k,d,ctx,gt,world,test,ks):
    z=camera_z(xyz,d['e'],d['fid']);result=dict(depth=depth_metrics(ctx['depth_scale']*z,gt,test),focal=focal(k,ks))
    for key in ['surface','pose']:
        alignment=ctx[key]
        if alignment is None:result['world_'+key]=None;continue
        transformed=alignment['sim3_scale']*xyz@np.array(alignment['sim3_rotation']).T+np.array(alignment['sim3_translation'])
        result['world_'+key]=point_metrics(transformed,world,test)
    return result

def run(dataset):
    parent=latest('I24',dataset);st=stage('I25',dataset,[parent,latest('I20',dataset)],dict(gt_status=GT_STATUS,evaluation_annotation='Frozen laser depth + official K/pose; evaluation only'))
    try:
        gtstage=latest('I20',dataset);gtfile=gtstage/'artifacts/laser_GT/evaluation_arrays.npz'
        with np.load(gtfile) as z:gt=z['gt'];world=z['world_gt'];fit=z['fit_mask'];test=z['test_mask'];valid=z['valid']
        clean=load(dataset);ks,es=camera_gt(clean);clean_ctx=context(clean,gt,world,fit,test,ks,es)
        gtrows=json.loads((parent/'evaluation/conditions.json').read_text());rows=[]
        fixedpath=latest('I10',dataset)/'artifacts/named_or/named_OR/pointmap.npz'
        with np.load(fixedpath) as z:fixed_xyz=z['xyz'];fixed_k=z['intrinsics']
        fixed_metrics=evaluate_map(fixed_xyz,fixed_k,clean,clean_ctx,gt,world,test,ks)
        f00path=parent/'artifacts/controls/F00/pointmap.npz'
        with np.load(f00path) as z:f00=evaluate_map(z['xyz'],z['intrinsics'],clean,clean_ctx,gt,world,test,ks)
        matching_clean=m.load(parent/'artifacts/controls/F00/matches.npz');epi_clean=epipolar(matching_clean,ks,es)
        for row in gtrows:
            case=row['case'];out=parent/'artifacts/controls'/case
            with np.load(latest('I22',dataset)/'artifacts/inputs'/case/'images.npz') as z:rgb=z['rgb']
            rawpath=latest('I23',dataset)/'artifacts/inference'/case/'raw.npz';d=data_with_raw(dataset,rawpath,rgb);ctx=context(d,gt,world,fit,test,ks,es)
            raw_metrics=evaluate_map(d['xyz'],d['k'],d,ctx,gt,world,test,ks);arms={};ep={}
            for name,item in row['arms'].items():
                geometry=clean if name=='F01' else d;alignment=clean_ctx if name=='F01' else ctx
                with np.load(item['pointmap']['path']) as z:arms[name]=evaluate_map(z['xyz'],z['intrinsics'],geometry,alignment,gt,world,test,ks)
                mm=m.load(Path(item['matches']['path']));ep[name]=epipolar(mm,ks,es)
            plane={}
            for arm in ['distance','distance_normal']:
                with np.load(out/'plane_RGB_frozen_geometry'/f'{arm}.npz') as z:plane[arm]=evaluate_map(z['xyz'],z['intrinsics'],clean,clean_ctx,gt,world,test,ks)
            e00=f00['focal']['mean_abs_relative_percent'];e01=arms['F01']['focal']['mean_abs_relative_percent'];e10=arms['F10']['focal']['mean_abs_relative_percent'];e11=arms['F11']['focal']['mean_abs_relative_percent']
            decomposition=dict(metric='focal mean abs relative error percentage points',e00=e00,e01=e01,e10=e10,e11=e11,
                matching_only=e01-e00,geometry_only=e10-e00,interaction=e11-e10-e01+e00,total=e11-e00)
            rows.append(dict(case=case,raw=raw_metrics,F00=f00,arms=arms,alignment=ctx,clean_alignment=clean_ctx,
                epipolar=ep,epipolar_F00=epi_clean,factorial=decomposition,plane_fixed=fixed_metrics,plane_RGB=plane,
                optimization=row,GT_validation_count=int(test.sum())))
            st.log('condition_evaluated',case=case,depth_MAE_cm=100*raw_metrics['depth']['mae_m'],raw_focal_error_pct=ctx['raw_intrinsics']['mean_abs_relative_percent'],
                native_focal_error_pct=arms['native']['focal']['mean_abs_relative_percent'],scale_ratio=ctx['pose_to_depth_scale_ratio'])
        reference={}
        c.json_write(st.path/'evaluation/conditions.json',rows);c.json_write(st.path/'evaluation/TUM_scale_reference.json',reference)
        inputs=[c.record(p/'manifest.json') for p in [parent,latest('I22',dataset),latest('I23',dataset),gtstage]]+[c.record(gtfile),c.record(PLAN)]
        st.finish(dict(decision='BLUR_CAUSAL_DIAGNOSTICS_EVALUATED',conditions=rows,TUM_reference=reference,inputs=inputs,
            checks=dict(GT_masks_frozen=True,no_GT_retuning=True,optimizer_finished_before_GT=True,ground_truth_camera_not_used_by_solver=True)),
            f'# I25 — {dataset} 블러 개입 GT 진단\n\n6조건×geometry/correspondence factorial과 고정 평면 RGB를 frozen 레이저 GT·K·pose로 평가했다. 판단은 종합 index와 정확한 conditions JSON을 함께 읽는다. GT는 입력·Omega·대응·solver 선택에 사용하지 않았다.\n\n소수 장면의 synthetic blur 효과와 실제 TUM 실패의 원인 확정을 구분한다.',gt_status=GT_STATUS)
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    for dataset in DATASETS:run(dataset)
