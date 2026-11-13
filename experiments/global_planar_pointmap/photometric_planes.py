"""I12: FIT-only analytic differentiation of frozen I10 planes, CPU float64.

This module never opens sensor GT. I13 is a separate evaluator/process.
"""
from core import *
import export as ex
from named_or import save_map

PLAN=ROOT/'docs/vggt_omega_plane_photometric_experiment_plan.md'
PROTOCOL=dict(version='I12.2',photo_cap=512,validation_cap=512,minimum_fit=64,minimum_validation=16,
    gradient_min=.01,occlusion_relative=.03,photo_sigma=.05,match_sigma=2.,raw_sigma=.02,
    raw_weight=.01,normal_sigma_degree=10.,normal_weight=.01,domain_weight=.1,
    outside_weight=10.,distance_bound=.20,tangent_bound_degree=10.,max_nfev=100,
    primary_arm='plane_distance_normal',gt_access='NONE',rgb_validation_improvement=.01,
    support_policy='frozen initial warp; same predicted target named tag; same split bilinear footprint',
    objective='mean normalized pseudo-Huber photo + match + weak raw/normal prior + domain/depth barriers')

def footprint(mask,uv):
    h,w=mask.shape;x=np.floor(uv[:,0]).astype(int);y=np.floor(uv[:,1]).astype(int)
    inside=np.isfinite(uv).all(1)&(x>=0)&(x<w-1)&(y>=0)&(y<h-1)
    xx=x.clip(0,w-2);yy=y.clip(0,h-2)
    return inside&mask[yy,xx]&mask[yy,xx+1]&mask[yy+1,xx]&mask[yy+1,xx+1]

def bilinear(im,uv):
    if im.ndim==2:im=im[:,:,None]
    h,w=im.shape[:2];u=uv[:,0].clip(0,w-1-1e-8);v=uv[:,1].clip(0,h-1-1e-8)
    x=np.floor(u).astype(int);y=np.floor(v).astype(int);a=(u-x)[:,None];b=(v-y)[:,None]
    p00,p10,p01,p11=im[y,x],im[y,x+1],im[y+1,x],im[y+1,x+1]
    val=(1-b)*((1-a)*p00+a*p10)+b*((1-a)*p01+a*p11)
    du=(1-b)*(p10-p00)+b*(p11-p01);dv=(1-a)*(p01-p00)+a*(p11-p10)
    du*=((uv[:,0]>=0)&(uv[:,0]<w-1))[:,None];dv*=((uv[:,1]>=0)&(uv[:,1]<h-1))[:,None]
    return val,np.stack([du,dv],axis=2)

def fill_split(rgb,allowed):
    assert allowed.any()
    nearest=ndimage.distance_transform_edt(~allowed,return_distances=False,return_indices=True)
    filled=rgb[nearest[0],nearest[1]].copy()
    distance=ndimage.distance_transform_edt(~allowed).astype(float)
    return filled,distance

def thin(ids,cap):
    return ids if len(ids)<=cap else ids[np.linspace(0,len(ids)-1,cap,dtype=int)]

def basis(n):
    axis=np.eye(3)[np.argmin(abs(n))];u=np.cross(n,axis);u/=np.linalg.norm(u)
    return u,np.cross(n,u)

def geometry(p,model,obs):
    # Unnormalized plane parameterization removes normalization from the quotient.
    normal=model['n']+p[0]*model['u']+p[1]*model['v']
    delta=model['center']-obs['C'];den=obs['q']@normal
    den=np.where(abs(den)<1e-8,np.where(den<0,-1e-8,1e-8),den)
    num=delta@normal+p[2]*model['zref'];z=num/den
    dz=np.column_stack([(delta@model['u']*den-num*(obs['q']@model['u']))/den**2,
        (delta@model['v']*den-num*(obs['q']@model['v']))/den**2,np.full(len(z),model['zref'])/den])
    xyz=obs['C']+z[:,None]*obs['q'];jx=obs['q'][:,:,None]*dz[:,None,:]
    cam=np.einsum('nij,nj->ni',obs['R'],xyz)+obs['t'];jc=np.einsum('nij,njk->nik',obs['R'],jx)
    hom=np.einsum('nij,nj->ni',obs['K'],cam);jh=np.einsum('nij,njk->nik',obs['K'],jc)
    cz=cam[:,2];safe=np.maximum(cz,1e-6);js=jc[:,2,:]*(cz>1e-6)[:,None]
    uv=hom[:,:2]/safe[:,None]
    juv=(jh[:,:2,:]*safe[:,None,None]-hom[:,:2,None]*js[:,None,:])/safe[:,None,None]**2
    return uv,juv,z,dz,cz,jc[:,2,:]

def robust(r,j,sigma):
    q=np.sqrt(1+(r/sigma)**2);fac=np.sqrt(2/(q+1));g=r*fac
    deriv=fac*(1-r*r/(2*sigma*sigma*q*(q+1)))
    return g/sigma,j*deriv[...,None]/sigma

def obs_make(d,source,target,uv=None):
    source=np.asarray(source,int);target=np.asarray(target,int)
    xy=d['uv'][source].astype(float) if uv is None else uv
    C=d['centers'][d['fid'][source]]
    q=np.array([np.r_[xy[k],1.]@np.linalg.inv(d['k'][d['fid'][i]]).T@np.linalg.inv(d['e'][d['fid'][i],:,:3]).T for k,i in enumerate(source)])
    return dict(C=C,q=q,R=d['e'][target,:,:3],t=d['e'][target,:,3],K=d['k'][target],target=target,source=source)

class Objective:
    def __init__(self,model,photo,matches,prior,images,domain,shape):
        self.model,self.photo,self.matches,self.prior=model,photo,matches,prior
        self.images,self.domain=images,domain;self.h,self.w=shape
        self.last_p=None
    def photo_values(self,p):
        obs=self.photo;uv,juv,z,dz,cz,jcz=geometry(p,self.model,obs)
        rgb=np.empty((len(uv),3));jac=np.empty((len(uv),3,3));dom=np.empty(len(uv));jd=np.empty((len(uv),3))
        for f in np.unique(obs['target']):
            take=obs['target']==f;val,grad=bilinear(self.images[f],uv[take]);rgb[take]=val
            jac[take]=np.einsum('nci,nij->ncj',grad,juv[take]);dd,dg=bilinear(self.domain[f],uv[take]);dom[take]=dd[:,0];jd[take]=np.einsum('ni,nij->nj',dg[:,0],juv[take])
        return rgb-obs['color'],jac,uv,juv,z,dz,cz,jcz,dom,jd
    def calculate(self,p):
        if self.last_p is not None and np.array_equal(p,self.last_p):return self.last
        parts=[];jacs=[]
        def add(r,j,weight=1.):
            scale=np.sqrt(weight/max(1,r.size));parts.append(r.ravel()*scale);jacs.append(j.reshape(-1,3)*scale)
        r,j,uv,juv,z,dz,cz,jcz,dom,jdom=self.photo_values(p)
        rr,jj=robust(r,j,PROTOCOL['photo_sigma']);add(rr,jj)
        add(dom/2.,jdom/2.,PROTOCOL['domain_weight'])
        low=np.maximum(-uv,0);high=np.maximum(uv-np.array([self.w-1,self.h-1]),0)
        add((low+high)/2.,juv*((uv>np.array([self.w-1,self.h-1])).astype(float)-(uv<0).astype(float))[:,:,None]/2.,PROTOCOL['outside_weight'])
        floor=self.model['zref']*.1
        add(np.maximum(floor-z,0)/floor,-dz*(z<floor)[:,None]/floor,10.)
        add(np.maximum(floor-cz,0)/floor,-jcz*(cz<floor)[:,None]/floor,10.)
        if len(self.matches['source']):
            mu,mj,*_=geometry(p,self.model,self.matches)
            mr,mjac=robust(mu-self.matches['uv_target'],mj,PROTOCOL['match_sigma']);add(mr,mjac)
        pr=self.prior
        if len(pr['q']):
            normal=self.model['n']+p[0]*self.model['u']+p[1]*self.model['v'];delta=self.model['center']-pr['C']
            den=pr['q']@normal;den=np.where(abs(den)<1e-8,1e-8,den);num=delta@normal+p[2]*self.model['zref'];zz=num/den
            deriv=np.column_stack([(delta@self.model['u']*den-num*(pr['q']@self.model['u']))/den**2,
                (delta@self.model['v']*den-num*(pr['q']@self.model['v']))/den**2,np.full(len(den),self.model['zref'])/den])
            denom=pr['depth']*PROTOCOL['raw_sigma'];add((zz-pr['depth'])/denom,deriv/denom[:,None],PROTOCOL['raw_weight'])
        normscale=np.tan(np.deg2rad(PROTOCOL['normal_sigma_degree']))
        add(p[:2]/normscale,np.eye(3)[:2]/normscale,PROTOCOL['normal_weight'])
        self.last_p=p.copy();self.last=(np.concatenate(parts),np.vstack(jacs));return self.last
    def photo_loss(self,p):
        r,j,*_=self.photo_values(p);rr,_=robust(r,j,PROTOCOL['photo_sigma'])
        return dict(count=len(r),rgb_mae=float(abs(r).mean()),normalized_robust_mean=float(np.mean(rr**2)))

def source_model(d,plane,ids):
    fit=ids;pp=np.array(plane['plane']);normal=pp[:3];u,v=basis(normal)
    center=d['xyz'][thin(fit,256)].mean(0);center-=normal*(center@normal+pp[3])
    return dict(n=normal,u=u,v=v,center=center,zref=float(np.median(d['d0'][fit])))

def build_photo(d,xyz,label,pid,tagmap,split,filled,cap):
    n,h,w=d['depth'].shape;size=h*w;source=[];target=[]
    for f in range(n):
        ids=np.flatnonzero((label==pid)&split.ravel()&(d['fid']==f))
        if not len(ids):continue
        for t in range(n):
            if t==f:continue
            uv,z,inside=c.project(xyz[ids],d['k'][t],d['e'][t],h,w)
            mask=split[t]&tagmap[t];ok=inside&footprint(mask,uv)
            dep,_=bilinear(d['depth'][t],uv);_,grad=bilinear(filled[t],uv)
            ok&=(dep[:,0]>0)&(z<=dep[:,0]*(1+PROTOCOL['occlusion_relative']))&(np.linalg.norm(grad,axis=(1,2))>=PROTOCOL['gradient_min'])
            source.extend(ids[ok]);target.extend(np.full(int(ok.sum()),t))
    ix=thin(np.arange(len(source)),cap);src=np.asarray(source,int)[ix];tgt=np.asarray(target,int)[ix]
    obs=obs_make(d,src,tgt);obs['color']=d['raw_rgb'][src].astype(float)/255.
    return obs

def build_matches(d,label,pid,split,matches):
    n,h,w=d['depth'].shape;source=[];target=[];uvs=[];uvt=[]
    fit=~matches['validation']
    for k in np.flatnonzero(fit):
        for a,b,ua,ub in [(int(matches['pair'][k,0]),int(matches['pair'][k,1]),matches['uv_i'][k],matches['uv_j'][k]),
                          (int(matches['pair'][k,1]),int(matches['pair'][k,0]),matches['uv_j'][k],matches['uv_i'][k])]:
            if not footprint(split[a],ua[None])[0] or not footprint(split[b],ub[None])[0]:continue
            x,y=np.floor(ua).astype(int);idx=a*h*w+y*w+x
            if label[idx]!=pid:continue
            source.append(idx);target.append(b);uvs.append(ua);uvt.append(ub)
    obs=obs_make(d,source,target,np.array(uvs).reshape(-1,2));obs['uv_target']=np.array(uvt).reshape(-1,2);return obs

def stored_plane(model,p):
    normal=model['n']+p[0]*model['u']+p[1]*model['v'];off=-normal@model['center']-p[2]*model['zref']
    return (np.r_[normal,off]/np.linalg.norm(normal)).tolist()

def numeric_jac(fun,p):
    eps=1e-7
    return np.column_stack([(fun(p+np.eye(3)[k]*eps)-fun(p-np.eye(3)[k]*eps))/(2*eps) for k in range(3)])

def synthetic_controls():
    h=w=96;K=np.array([[90.,0.,47.5],[0.,90.,47.5],[0.,0.,1.]])
    normal=np.array([0.,0.,1.]);u,v=basis(normal);model=dict(n=normal,u=u,v=v,center=np.array([0.,0.,2.]),zref=2.)
    yy,xx=np.indices((h,w));im=np.stack([.5+.2*np.sin(xx*.19)+.15*np.cos(yy*.17),.5+.2*np.cos(xx*.13+yy*.11),.5+.2*np.sin(xx*.09-yy*.21)],axis=2)
    xy=np.c_[xx[20:76:3,20:76:3].ravel(),yy[20:76:3,20:76:3].ravel()].astype(float)+[.123,.217];count=len(xy)
    obs=dict(C=np.zeros((count,3)),q=np.c_[xy,np.ones(count)]@np.linalg.inv(K).T,
        R=np.tile(np.eye(3),(count,1,1)),t=np.tile([-.25,-.04,0.],(count,1)),K=np.tile(K,(count,1,1)),
        source=np.arange(count),target=np.zeros(count,int))
    truth=np.array([.045,-.035,.06]);uv,*_=geometry(truth,model,obs);obs['color']=bilinear(im,uv)[0]
    empty=dict(C=np.empty((0,3)),q=np.empty((0,3)),source=np.array([],int))
    ob=Objective(model,obs,empty,empty,[im],[np.zeros((h,w))],(h,w))
    p=np.array([.011,.017,.02]);r,j=ob.calculate(p);nj=numeric_jac(lambda x:ob.calculate(x)[0],p)
    error=float(np.max(abs(j-nj))/max(1.,np.max(abs(nj))));assert error<2e-5,error
    # Pure photo recovery: remove weak normal prior so known image geometry is the optimum.
    def photo_fun(p):return ob.photo_values(p)[0].ravel()
    def photo_jac(p):return ob.photo_values(p)[1].reshape(-1,3)
    fit=least_squares(photo_fun,np.zeros(3),jac=photo_jac,max_nfev=100,gtol=1e-12,ftol=1e-12,xtol=1e-12)
    recovery=float(np.max(abs(fit.x-truth)));assert recovery<1e-6,(fit.x,truth)
    allowed=(xx%7!=0);filled,_=fill_split(im,allowed);altered=im.copy();altered[~allowed]=1000.
    filled2,_=fill_split(altered,allowed);assert np.array_equal(filled,filled2)
    # Same-camera re-projection cannot recover depth: its image coordinate Jacobian vanishes.
    own=dict(obs,t=np.zeros_like(obs['t']));_,juv,*_=geometry(p,model,own);assert abs(juv).max()<1e-10
    return dict(analytic_jac_relative_error=error,synthetic_photo_parameter_error=recovery,
        forbidden_RGB_perturbation_invariant=True,self_view_depth_gradient_zero=True)

def run(dataset):
    parent=latest('I10',dataset);st=Stage('I12',dataset,[parent],PROTOCOL)
    try:
        shutil.copy2(PLAN,st.path/'artifacts/source/photometric_plan.md')
        st.config.update(PROTOCOL);c.json_write(st.path/'config_resolved.json',st.config)
        c.json_write(st.path/'evaluation/protocol.json',PROTOCOL);st.log('protocol_frozen',plan=c.record(PLAN))
        checks=synthetic_controls();st.log('synthetic_controls',**checks)
        d=load(dataset,True);n,h,w=d['depth'].shape;N=len(d['ids']);split=split_load(dataset)
        train=(~split['excluded']).reshape(n,h,w);valid=split['validation'].reshape(n,h,w)
        assert not (train&valid).any()
        source=parent/'artifacts/named_or/named_OR';pfile=source/'pointmap.npz'
        with np.load(pfile) as z:fixed=z['xyz'];label=z['plane_id'];original_meta={k:z[k] for k in ['rgb','observation_id','frame_id','pixel_uv','intrinsics','extrinsics']}
        planes=json.loads((source/'planes.json').read_text())['planes']
        images=d['rgb'].astype(float)/255.;fillfit=[];domainfit=[];fillval=[];domainval=[]
        for f in range(n):
            a,b=fill_split(images[f],train[f]);fillfit.append(a);domainfit.append(b)
            a,b=fill_split(images[f],valid[f]);fillval.append(a);domainval.append(b)
        matches=m.load(split_path(dataset)/'matches.npz');tags={}
        for tag in ['wall','table','screen']:
            ids=[p['plane_id'] for p in planes if p['semantic_tag']==tag];tags[tag]=np.isin(label,ids).reshape(n,h,w)
        pp={a:json.loads(json.dumps(planes)) for a in ['plane_distance','plane_distance_normal']}
        out=st.path/'artifacts/photometric';out.mkdir();support={};history=[];photo_before=[];photo_after={a:[] for a in pp};optimized=np.zeros(N,bool)
        for plane in planes:
            pid=plane['plane_id'];ids=np.flatnonzero(label==pid);fitids=ids[train.ravel()[ids]]
            if not len(fitids):history.append(dict(plane_id=pid,status='NO_FIT_GEOMETRY'));continue
            model=source_model(d,plane,fitids)
            fitobs=build_photo(d,fixed,label,pid,tags[plane['semantic_tag']],train,fillfit,PROTOCOL['photo_cap'])
            valobs=build_photo(d,fixed,label,pid,tags[plane['semantic_tag']],valid,fillval,PROTOCOL['validation_cap'])
            row=dict(plane_id=pid,tag=plane['semantic_tag'],fit_photo=len(fitobs['source']),validation_photo=len(valobs['source']))
            for name,ob in [('fit',fitobs),('validation',valobs)]:
                for key in ['source','target']:support[f'{name}_{key}_{pid}']=ob[key]
            if row['fit_photo']<PROTOCOL['minimum_fit'] or row['validation_photo']<PROTOCOL['minimum_validation']:
                row['status']='INSUFFICIENT_RGB_SUPPORT';history.append(row);continue
            matchobs=build_matches(d,label,pid,train,matches);priorids=thin(fitids,256)
            prior=dict(C=d['center_points'][priorids],q=d['q'][priorids],depth=d['d0'][priorids])
            obj=Objective(model,fitobs,matchobs,prior,fillfit,domainfit,(h,w))
            val=Objective(model,valobs,matchobs,prior,fillval,domainval,(h,w))
            zero=np.zeros(3);basefit=obj.photo_loss(zero);baseval=val.photo_loss(zero)
            photo_before.append(baseval);row.update(status='OPTIMIZED',matches=len(matchobs['source']),initial_fit=basefit,initial_validation=baseval,arms={})
            assert np.max(abs(np.array(stored_plane(model,zero))-np.array(plane['plane'])))<1e-9
            r0,j0=obj.calculate(zero);nj=numeric_jac(lambda x:obj.calculate(x)[0],zero)
            jac_error=float(np.max(abs(j0-nj))/max(1.,np.max(abs(nj))))
            # Bilinear interpolation is nondifferentiable at exact grid boundaries.
            # Strict check uses a deterministic small interior parameter perturbation.
            probe=np.array([.0013,-.0017,.0021]);rr,jj=obj.calculate(probe);nn=numeric_jac(lambda x:obj.calculate(x)[0],probe)
            probe_error=float(np.max(abs(jj-nn))/max(1.,np.max(abs(nn))))
            assert probe_error<2e-3,(pid,probe_error)
            row.update(initial_jac_error=jac_error,probe_jac_error=probe_error,jac_singular_values=np.linalg.svd(j0,compute_uv=False).tolist())
            for arm in pp:
                active=[2] if arm=='plane_distance' else [0,1,2]
                def full(x):
                    q=np.zeros(3);q[active]=x;return q
                bound=np.array([np.tan(np.deg2rad(PROTOCOL['tangent_bound_degree']))]*2+[PROTOCOL['distance_bound']])[active]
                fit=least_squares(lambda x:obj.calculate(full(x))[0],np.zeros(len(active)),
                    jac=lambda x:obj.calculate(full(x))[1][:,active],bounds=(-bound,bound),
                    max_nfev=PROTOCOL['max_nfev'],ftol=1e-8,xtol=1e-8,gtol=1e-8)
                parameter=full(fit.x);candidate=stored_plane(model,parameter)
                _,zz,ok=intersect(d,ids,np.array(candidate))
                accepted=bool(ok.all() and np.sum(obj.calculate(parameter)[0]**2)<=np.sum(r0**2)+1e-10)
                if not accepted:parameter=np.zeros(3);candidate=plane['plane']
                pp[arm][pid]['plane']=candidate
                ff=obj.photo_loss(parameter);vv=val.photo_loss(parameter);photo_after[arm].append(vv)
                row['arms'][arm]=dict(parameter=parameter.tolist(),accepted=accepted,nfev=fit.nfev,solver_success=bool(fit.success),
                    solver_message=fit.message,bound_hit=bool(np.any(abs(fit.x)>=bound*.999)),fit_photo=ff,validation_photo=vv,
                    normal_angle_degree=float(np.rad2deg(np.arccos(np.clip(np.dot(candidate[:3],plane['plane'][:3]),-1,1)))))
            optimized[ids]=True;history.append(row)
            if len(history)%10==0:st.log('plane_progress',processed=len(history),supported=len(photo_before))
        def aggregate(rows):
            total=sum(x['count'] for x in rows)
            return dict(count=total,normalized_robust_mean=sum(x['count']*x['normalized_robust_mean'] for x in rows)/max(total,1),
                rgb_mae=sum(x['count']*x['rgb_mae'] for x in rows)/max(total,1))
        validation={'plane_fixed':aggregate(photo_before)}|{a:aggregate(v) for a,v in photo_after.items()}
        inputrecords=[c.record(parent/'manifest.json'),c.record(pfile),c.record(PLAN),c.record(split_path(dataset)/'split.npz'),c.record(split_path(dataset)/'matches.npz')]
        states={'initial':(d['xyz'],np.full(N,-1,np.int32),[]),'plane_fixed':(fixed,label,planes)};arms={}
        for arm in pp:
            xyz,pids,acc,z,reason,check=ex.project_map(d,pp[arm],label)
            assert np.array_equal(pids,label);assert np.array_equal(xyz[label<0],fixed[label<0])
            states[arm]=(xyz,pids,pp[arm]);arms[arm]=dict(visibility=ex.visibility(d,xyz),projection_checks=check)
        primary=PROTOCOL['primary_arm'];baseline=validation['plane_fixed']['normalized_robust_mean']
        gain=1-validation[primary]['normalized_robust_mean']/max(baseline,1e-30)
        passed=bool(len(photo_before)>0 and gain>=PROTOCOL['rgb_validation_improvement'] and arms[primary]['visibility']['passed'])
        if passed:states['retained']=states[primary];retained=primary
        else:
            with np.load(parent/'artifacts/named_or/retained/pointmap.npz') as z:states['retained']=(z['xyz'],z['plane_id'],planes if (z['plane_id']>=0).any() else [])
            retained='I10_retained'
        for arm,(xyz,pids,ps) in states.items():
            save_map(out/arm,d,xyz,pids,ps,arm,inputrecords)
            with np.load(out/arm/'pointmap.npz') as z:
                for key,v in original_meta.items():assert ahash(z[key])==ahash(v),(arm,key)
            arms.setdefault(arm,{})['visibility']=ex.visibility(d,xyz)
        np.savez_compressed(out/'support.npz',optimized_mask=optimized,**support)
        c.json_write(st.path/'evaluation/planes.json',history);c.json_write(st.path/'evaluation/validation_photo.json',validation)
        result=dict(decision='RGB_PLANE_OPTIMIZATION_EXECUTED',retained=retained,primary_passes_rgb_visibility=passed,
            validation_relative_gain=gain,validation_photo=validation,arms=arms,optimized_plane_count=len(photo_before),
            optimized_observations=int(optimized.sum()),checks=checks,inputs=inputrecords,GT_read_during_optimization=False,
            limitations=['Most plane IDs have one source view; target same-tag checks do not establish physical identity.',
                'Same scene as previous GT evaluation; exploratory study.', 'Frozen support may not represent all visible pixels.'])
        st.finish(result,'# I12 — 평면 거리·법선의 RGB 최적화\n\n'
            +f"대상 `{dataset}`. RGB 지지 평면 {len(photo_before)}/{len(planes)}, 관측 {optimized.sum():,}개."
            +f"\n\n보류 RGB 손실 상대 감소 {gain:.4%}, RGB/가시성 선택 통과={passed}, retained=`{retained}`."
            +'\n\nGT를 읽지 않고 카메라·의미 태그·소속·RGB·ID·UV를 고정했다. 출력은 artifacts/photometric에 저장했다.'
            +'\n\n계획: docs/vggt_omega_plane_photometric_experiment_plan.md. GT 정확도 판정은 별도 프로세스 I13에서 수행한다.')
        return st
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['tum-freiburg1_desk','tum-freiburg1_desk-extra','all'],default='all');args=p.parse_args()
    for ds in (['tum-freiburg1_desk','tum-freiburg1_desk-extra'] if args.dataset=='all' else [args.dataset]):run(ds)
