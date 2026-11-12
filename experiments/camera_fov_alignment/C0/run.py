"""C0 mathematical/solver controls; no real-data coefficient fitting."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import cv2
import numpy as np


def main():
    stage=c.Stage('C0')
    try:
        rng=np.random.default_rng(0)
        data=c.load_data('tum-freiburg1_desk')
        n,h,w=data['depth'].shape
        beta=rng.uniform(c.LOW,c.HIGH,(3,2))
        initial=c.points(data,np.ones(6))
        reference_error=float(np.max(np.abs(initial-data['reference_xyz'])))
        assert np.allclose(initial,data['reference_xyz'],atol=1e-7,rtol=1e-6)
        checks={'initial_raw_max_abs_error':reference_error,'raw_point_count':len(initial),
            'self_projection_max_px':0.,'self_z_max_error':0.,'affine_max_error':0.,
            'transpose_vs_inverse_max':0.}
        moved=c.points(data,beta)
        for i in range(3):
            ids=slice(i*h*w,(i+1)*h*w)
            uv,z,valid=c.project(moved[ids],c.corrected_k(data['k'],beta)[i],data['e'][i],h,w)
            px=float(np.max(np.abs(uv-data['uv'][ids])))
            ze=float(np.max(np.abs(z-data['depth'][i].ravel())))
            assert valid.all() and px<1e-5 and ze<1e-10
            p,a=c.affine_observation(data['uv'][ids],data['depth'][i].ravel(),data['k'][i],data['e'][i])
            affine=p+np.einsum('nck,k->nc',a,beta[i]-1)
            error=float(np.max(np.abs(affine-moved[ids])))
            assert np.allclose(affine,moved[ids],atol=1e-9,rtol=1e-8)
            inv=np.linalg.inv(data['e'][i,:,:3])
            checks['transpose_vs_inverse_max']=max(checks['transpose_vs_inverse_max'],float(np.max(np.abs(inv-data['e'][i,:,:3].T))))
            checks['self_projection_max_px']=max(checks['self_projection_max_px'],px)
            checks['self_z_max_error']=max(checks['self_z_max_error'],ze)
            checks['affine_max_error']=max(checks['affine_max_error'],error)
        # Fixed world landmarks, three nonparallel cameras, varied depths.
        world=rng.uniform([-1.2,-.9,3.],[1.2,.9,7.],(180,3))
        es=[];ks=[];uvs=[];depths=[]
        for i,(rvec,center) in enumerate([(np.zeros(3),[0,0,0]),
                (np.array([.1,.18,-.04]),[.7,.1,.1]),
                (np.array([-.15,.05,.08]),[-.3,.6,-.1])]):
            r=cv2.Rodrigues(rvec)[0];center=np.array(center)
            e=np.c_[r,-r@center];k=np.array([[420.,0,256],[0,430.,192],[0,0,1.]])
            cam=world@r.T+e[:,3];uv=(cam@k.T)[:,:2]/cam[:,2,None]
            es.append(e);ks.append(k);uvs.append(uv);depths.append(cam[:,2])
        pairs=np.repeat(np.array([[0,1],[0,2],[1,2]]),len(world),axis=0)
        matches={'pair':pairs,'uv_i':np.vstack([uvs[i] for i,j in [(0,1),(0,2),(1,2)]]),
            'uv_j':np.vstack([uvs[j] for i,j in [(0,1),(0,2),(1,2)]]),
            'di':np.concatenate([depths[i] for i,j in [(0,1),(0,2),(1,2)]]),
            'dj':np.concatenate([depths[j] for i,j in [(0,1),(0,2),(1,2)]])}
        synthetic=[]
        for amount in [.05,.10]:
            for sign in [-1,1]:
                factor=1/(1+sign*amount*np.array([[1,-1],[-1,1],[1,1]]))
                perturbed=np.array(ks)
                perturbed[:,0,0]*=factor[:,0];perturbed[:,1,1]*=factor[:,1]
                a,b,weights,_=c.build_system({'k':perturbed,'e':np.array(es)},matches)
                info=c.rank_info(a)
                result,kkt=c.box_lstsq(a.reshape(-1,6),-b.ravel())
                error=float(np.max(np.abs(result.reshape(3,2)-factor)/factor))
                assert info['identifiable'] and error<=1e-4,(info,error)
                synthetic.append({'perturbation':sign*amount,'beta_expected':factor.ravel().tolist(),
                    'beta_recovered':result.tolist(),'relative_focal_error_max':error,'rank':info,'kkt':kkt,
                    'boundary_control':amount==.10})
        # Independent 1-D grid verifies bounded least squares including bound optima.
        grid_controls=[]
        for target in [.7,1.02,1.4]:
            a=np.array([[1.],[2.],[-.4]]);b=a[:,0]*target
            out,kkt=c.box_lstsq(a,b)
            grid=np.linspace(c.LOW,c.HIGH,10001)
            losses=((grid[:,None]*a[:,0]-b)**2).sum(1)
            assert np.sum((a@out-b)**2)<=losses.min()+1e-12
            grid_controls.append({'unconstrained_truth':target,'solution':out.tolist(),'kkt':kkt})
        # Robust IRLS controls use known coefficients; outliers are fixed before fitting.
        a=rng.normal(0,.3,(600,3,6));truth=np.array([1.02,.98,1.03,.99,1.01,.97])
        b=-(a@truth)+rng.normal(0,.0003,(600,3));b[:30]+=rng.normal(0,.15,(30,3))
        out,hist,converged=c.solve_irls(a,b,np.full(600,1/600),prior=.001)
        robust_error=float(np.max(np.abs(out-truth)))
        assert converged and robust_error<.005
        # Parallel cameras: D-camera-Z residual contains no beta coefficient.
        parallel_e=np.array([np.c_[np.eye(3),-np.array(center)] for center in
            [[0,0,0],[.7,.1,.1],[-.3,.6,-.1]]])
        parallel_uv=[];parallel_depth=[]
        for e,k in zip(parallel_e,ks):
            cam=world+e[:,3]
            parallel_uv.append((cam@k.T)[:,:2]/cam[:,2,None]);parallel_depth.append(cam[:,2])
        pm={'pair':pairs,'uv_i':np.vstack([parallel_uv[i] for i,j in [(0,1),(0,2),(1,2)]]),
            'uv_j':np.vstack([parallel_uv[j] for i,j in [(0,1),(0,2),(1,2)]]),
            'di':np.concatenate([parallel_depth[i] for i,j in [(0,1),(0,2),(1,2)]]),
            'dj':np.concatenate([parallel_depth[j] for i,j in [(0,1),(0,2),(1,2)]])}
        parallel_a,_,_,_=c.build_system({'k':np.array(ks),'e':parallel_e},pm)
        assert np.max(np.abs(parallel_a[:,2,:]))==0
        repeated=np.ones((24,3,6))
        assert not c.rank_info(repeated)['identifiable']
        # Exact nearest-neighbor secondary metric backend checked against brute force.
        target=rng.normal(size=(250,3)).astype(np.float32)
        query=rng.normal(size=(40,3)).astype(np.float32)
        bf=cv2.BFMatcher(cv2.NORM_L2)
        nearest=bf.match(query,target)
        dist=np.array([m.distance**2 for m in nearest])
        exact=((query[:,None,:]-target[None,:,:])**2).sum(2)
        assert np.allclose(dist,exact.min(1),rtol=2e-6,atol=1e-6)
        metrics={'decision':'TECHNICAL_PASS','checks':checks,'synthetic_recovery':synthetic,
            'solver_grid_controls':grid_controls,'robust_control':{
                'converged':converged,'max_beta_error':robust_error,'history':hist},
            'degeneracy_controls':{'parallel_depth_only_coefficients_zero':True,
                'repeated_observations_rank_deficient':True},
            'nearest_neighbor_float32_backend_vs_bruteforce':'passed',
            'inputs':data['inputs'],'scientific_improvement':False}
        stage.finish(metrics,f'''# C0 수식·solver 검증

실행: `{stage.run_id}`. **TECHNICAL_PASS**.

- 원본 역투영 최대 차이: {reference_error:.3g} 모델 단위.
- 자기 재투영 최대 오차: {checks['self_projection_max_px']:.3g} pixel.
- 직접 역투영↔affine 최대 차이: {checks['affine_max_error']:.3g}.
- ±5%/±10% 합성 초점거리 교란 4조건의 6변수 복구·rank·KKT 검사 통과. 10%는 경계 정답 제어다.
- 고정 오매칭 5%·잡음이 있는 IRLS 제어: 수렴={converged}, 최대 β 오차={robust_error:.6g}.
- 1변수 독립 grid, 깊이축 무감각·반복 관측 rank 부족 제어, float32 nearest-neighbor backend의 brute-force 대조 통과.

실제 장면 FoV 보정 효과를 확인한 단계가 아니다. 대응 부족·순수 회전·평면 지원은 C1에서 실제 영상으로 추가 확인한다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
