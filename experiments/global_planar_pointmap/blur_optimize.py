"""I24: no-GT factorial FoV and isolated frozen-plane RGB interventions."""
from core import *
from blur_inputs import stage,DATASETS,CASES,apply_blur,data_with_raw
import photometric_planes as photo
import export as ex

def fixed_split(matches,split,shape):
    result={k:v.copy() for k,v in matches.items()};train=(~split['excluded']).reshape(shape)
    held=result['validation'].copy()
    for a,b in itertools.combinations(range(3),2):
        take=(result['pair'][:,0]==a)&(result['pair'][:,1]==b)
        held[take]|=~photo.footprint(train[a],result['uv_i'][take])|~photo.footprint(train[b],result['uv_j'][take])
    for tid in np.unique(result['track_id']):
        ids=result['track_id']==tid;held[ids]=held[ids].any()
    result['validation']=held
    assert not(set(result['track_id'][held])&set(result['track_id'][~held]))
    return result

def resample(matches,d):
    result={k:v.copy() for k,v in matches.items()};good=np.ones(len(result['pair']),bool)
    for f in range(3):
        for side,field,uvkey in [(0,'di','uv_i'),(1,'dj','uv_j')]:
            take=result['pair'][:,side]==f
            dep,ok,threshold=m.depth_samples(d,f,result[uvkey][take]);result[field][take]=dep;good[take]&=ok
    assert np.isfinite(result['di']).all() and np.isfinite(result['dj']).all() and (result['di']>0).all() and (result['dj']>0).all()
    return result,dict(count=len(good),quality_gate_fraction=float(good.mean()) if len(good) else None,
        policy='UV/pair/track/validation frozen; resample positive finite depth; log gate without dropping rows')

def fov_state(d,matches,out):
    out.mkdir(parents=True);fit=m.subset(matches,~matches['validation']);count=len(fit['pair'])
    rank=dict(rank=0,dimension=6,identifiable=False,condition=None,singular_values=[]);hist=[];converged=False
    if count:
        a,b,w,_=c.build_system(d,fit);rank=c.rank_info(a)
        if rank['identifiable']:beta,hist,converged=c.solve_irls(a,b,w)
        else:beta=np.ones(6)
    else:beta=np.ones(6)
    xyz=c.points(d,beta);k=c.corrected_k(d['k'],beta.reshape(3,2))
    np.savez_compressed(out/'pointmap.npz',xyz=xyz,intrinsics=k,extrinsics=d['e'],beta=beta,observation_id=d['ids'],frame_id=d['fid'],pixel_uv=d['uv'])
    np.savez_compressed(out/'matches.npz',**matches)
    support=m.pair_support(matches,*d['depth'].shape[1:])
    status='UNIDENTIFIABLE_BETA1' if not rank['identifiable'] else ('FOV_SOLVED' if support['passed'] else 'FOV_SOLVED_LOW_SUPPORT')
    result=dict(status=status,beta=beta.tolist(),rank=rank,support=support,fit_correspondences=count,total_correspondences=len(matches['pair']),
        converged=bool(converged),bound_hit=bool(np.any((beta<=c.LOW+1e-8)|(beta>=c.HIGH-1e-8))),history=hist,
        fixed_UV_hash=ahash(np.c_[matches['pair'],matches['uv_i'],matches['uv_j']]),pointmap=c.record(out/'pointmap.npz'),matches=c.record(out/'matches.npz'))
    c.json_write(out/'solve.json',result);return result

def frozen_plane_trial(dataset,case,root):
    d=load(dataset,True);n,h,w=d['depth'].shape;sp=split_load(dataset);train=(~sp['excluded']).reshape(n,h,w);valid=sp['validation'].reshape(n,h,w)
    source=latest('I10',dataset)/'artifacts/named_or/named_OR';old=latest('I12',dataset)
    with np.load(source/'pointmap.npz') as z:fixed=z['xyz'];label=z['plane_id']
    planes=json.loads((source/'planes.json').read_text())['planes'];history=json.loads((old/'evaluation/planes.json').read_text())
    active=[p['plane_id'] for p in history if p['status']=='OPTIMIZED'];support=np.load(old/'artifacts/photometric/support.npz')
    imfit=[];domfit=[];imval=[];domval=[]
    for f in range(n):
        a,b=photo.fill_split(d['rgb'][f],train[f]);a=apply_blur(a,case,f);imfit.append(a.astype(float)/255.);domfit.append(b)
        a,b=photo.fill_split(d['rgb'][f],valid[f]);a=apply_blur(a,case,f);imval.append(a.astype(float)/255.);domval.append(b)
    pp={a:json.loads(json.dumps(planes)) for a in ['distance','distance_normal']};rows=[]
    matches=m.load(split_path(dataset)/'matches.npz');zero=np.zeros(3)
    for pid in active:
        ids=np.flatnonzero(label==pid);fitids=ids[train.ravel()[ids]];model=photo.source_model(d,planes[pid],fitids)
        def observation(which,images):
            src=support[f'{which}_source_{pid}'];tgt=support[f'{which}_target_{pid}'];ob=photo.obs_make(d,src,tgt)
            color=np.empty((len(src),3));uv=d['uv'][src]
            for f in range(n):
                take=d['fid'][src]==f;color[take]=images[f][uv[take,1],uv[take,0]]
            ob['color']=color;return ob
        fitobs=observation('fit',imfit);valobs=observation('validation',imval)
        matchobs=photo.build_matches(d,label,pid,train,matches);priorids=photo.thin(fitids,256)
        prior=dict(C=d['center_points'][priorids],q=d['q'][priorids],depth=d['d0'][priorids])
        objective=photo.Objective(model,fitobs,matchobs,prior,imfit,domfit,(h,w));validation=photo.Objective(model,valobs,matchobs,prior,imval,domval,(h,w))
        initial=objective.calculate(zero)[0];row=dict(plane_id=pid,fit_fixed=objective.photo_loss(zero),val_fixed=validation.photo_loss(zero),arms={})
        for arm in pp:
            which=[2] if arm=='distance' else [0,1,2]
            def full(x):
                p=np.zeros(3);p[which]=x;return p
            bound=np.array([np.tan(np.deg2rad(photo.PROTOCOL['tangent_bound_degree']))]*2+[photo.PROTOCOL['distance_bound']])[which]
            fit=least_squares(lambda x:objective.calculate(full(x))[0],np.zeros(len(which)),jac=lambda x:objective.calculate(full(x))[1][:,which],
                bounds=(-bound,bound),max_nfev=photo.PROTOCOL['max_nfev'],ftol=1e-8,xtol=1e-8,gtol=1e-8)
            parameter=full(fit.x);plane=photo.stored_plane(model,parameter);_,zz,ok=intersect(d,ids,np.array(plane))
            accepted=bool(ok.all() and np.sum(objective.calculate(parameter)[0]**2)<=np.sum(initial**2)+1e-10)
            if not accepted:parameter=zero.copy();plane=planes[pid]['plane']
            pp[arm][pid]['plane']=plane
            row['arms'][arm]=dict(parameter=parameter.tolist(),accepted=accepted,nfev=fit.nfev,bound_hit=bool(np.any(abs(fit.x)>=.999*bound)),
                fit_photo=objective.photo_loss(parameter),validation_photo=validation.photo_loss(parameter))
        rows.append(row)
    support.close();root.mkdir();c.json_write(root/'planes.json',rows)
    results={}
    for arm in pp:
        xyz,pids,accepted,z,reason,checks=ex.project_map(d,pp[arm],label)
        assert np.array_equal(pids,label) and np.array_equal(xyz[label<0],fixed[label<0])
        path=root/f'{arm}.npz';np.savez_compressed(path,xyz=xyz,intrinsics=d['k'],extrinsics=d['e'],plane_id=pids)
        def average(field):
            values=[row['arms'][arm][field] for row in rows];count=sum(x['count'] for x in values)
            return dict(count=count,loss=sum(x['count']*x['normalized_robust_mean'] for x in values)/max(count,1))
        results[arm]=dict(pointmap=c.record(path),visibility=ex.visibility(d,xyz),fit_photo=average('fit_photo'),validation_photo=average('validation_photo'),
            bound_hits=sum(p['arms'][arm]['bound_hit'] for p in rows))
        if case=='clean':
            key='plane_distance' if arm=='distance' else 'plane_distance_normal'
            with np.load(old/'artifacts/photometric'/key/'pointmap.npz') as original:
                error=float(abs(original['xyz']-xyz).max());assert error<1e-9,(dataset,arm,error)
            results[arm]['clean_I12_replay_max_abs']=error
    for name,key in [('fit_fixed','fit_fixed'),('val_fixed','val_fixed')]:
        values=[p[key] for p in rows];count=sum(p['count'] for p in values)
        results[name]=dict(count=count,loss=sum(p['count']*p['normalized_robust_mean'] for p in values)/max(count,1))
    results['active_planes']=len(active);results['fixed_support']=c.record(old/'artifacts/photometric/support.npz')
    c.json_write(root/'summary.json',results);return results

def run(dataset):
    parents=[latest(k,dataset) for k in ['I22','I23','I0','I12']];st=stage('I24',dataset,parents)
    try:
        clean=load(dataset);sp=split_load(dataset);old_matches=m.load(split_path(dataset)/'matches.npz')
        clean_matches=fixed_split(old_matches,sp,clean['depth'].shape)
        root=st.path/'artifacts/controls';root.mkdir();baseline=fov_state(clean,clean_matches,root/'F00')
        with np.load(latest('I2',dataset)/'artifacts/fov/pointmap.npz') as z:legacy_beta=z['beta']
        baseline['legacy_I2_beta_max_abs_difference']=float(abs(np.array(baseline['beta'])-legacy_beta).max())
        conditions=[]
        for case in CASES:
            out=root/case;out.mkdir()
            with np.load(latest('I22',dataset)/'artifacts/inputs'/case/'images.npz') as z:rgb=z['rgb']
            rawpath=latest('I23',dataset)/'artifacts/inference'/case/'raw.npz';blurred=data_with_raw(dataset,rawpath,rgb)
            rawout=out/'raw.npz';np.savez_compressed(rawout,xyz=blurred['xyz'],intrinsics=blurred['k'],extrinsics=blurred['e'])
            clean_rgb=dict(clean,rgb=rgb,raw_rgb=rgb.reshape(-1,3))
            blur_matches,match_report=m.extract(clean_rgb,out/'matching_clean_geometry',st)
            blur_matches=fixed_split(blur_matches,sp,clean['depth'].shape)
            fixed_clean,resample_clean=resample(clean_matches,blurred);fixed_blur,resample_blur=resample(blur_matches,blurred)
            native,native_report=m.extract(blurred,out/'matching_native_geometry',st);native=fixed_split(native,sp,clean['depth'].shape)
            cases=dict(F01=fov_state(clean,blur_matches,out/'F01'),F10=fov_state(blurred,fixed_clean,out/'F10'),
                F11=fov_state(blurred,fixed_blur,out/'F11'),native=fov_state(blurred,native,out/'native'))
            planes=frozen_plane_trial(dataset,case,out/'plane_RGB_frozen_geometry')
            row=dict(case=case,F00=baseline,arms=cases,plane_RGB=planes,raw=c.record(rawout),
                matching_clean_geometry=match_report,matching_native_geometry=native_report,
                resample_clean=resample_clean,resample_blur=resample_blur,raw_source=c.record(rawpath))
            conditions.append(row);st.log('blur_condition_optimized',case=case,fit_counts={a:v['fit_correspondences'] for a,v in cases.items()},
                identifiable={a:v['rank']['identifiable'] for a,v in cases.items()})
        c.json_write(st.path/'evaluation/conditions.json',conditions)
        st.finish(dict(decision='BLUR_FACTORIAL_AND_FROZEN_PLANE_OPTIMIZATION_EXECUTED',conditions=conditions,
            GT_read=False,checks=dict(fixed_GT_pixel_grid=True,unchanged_existing_outputs=True,clean_plane_replay=True,positive_finite_resampled_depth=True)),
            f'# I24 — {dataset} 블러 원인 분리 최적화\n\n6조건의 geometry×correspondence 2×2 FoV 및 native 제어군을 실행했다. 기존 mask·plane·support를 고정한 split-safe RGB 평면 진단도 실행했다. GT는 사용하지 않았다.\n\nF00은 bilinear footprint까지 동결 FIT 구역 안인 clean 대응으로 재계산했다. 이전 I2 beta 차이는 JSON에 기록했다. 지원/rank 부족은 beta1 fallback이며 성공으로 간주하지 않는다.')
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    for dataset in DATASETS:run(dataset)
