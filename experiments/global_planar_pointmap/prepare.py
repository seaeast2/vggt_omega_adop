"""I0: freeze both windows and disjoint observation/whole-track fit evidence."""
from core import *

def freeze_split(d,out,st):
    out.mkdir(parents=True);n,h,w=d['depth'].shape;N=n*h*w
    if d['dataset']=='tum-freiburg1_desk':
        parent=ROOT/'results/camera_fov_alignment/tum-freiburg1_desk-C1-20261112-001/stages/C1/artifacts/baseline/matches'
        matches=m.load(parent/'matches.npz');tracks=json.loads((parent/'tracks.json').read_text())
    else:
        matches,_=m.extract(d,out/'image_matches',st);tracks=json.loads((out/'image_matches/tracks.json').read_text())
    # Spatial holdout is independent of depth, image content, or corrected output.
    base=np.zeros((n,h,w),bool)
    for f,y,x in itertools.product(range(n),range(12),range(16)):
        val=int.from_bytes(hashlib.sha256(f'0:{f}:{x}:{y}'.encode()).digest()[:8],'little')%5==0
        if val:base[f,y*h//12:(y+1)*h//12,x*w//16:(x+1)*w//16]=True
    val=matches['validation'].copy();members=[]
    for k,(i,j) in enumerate(matches['pair']):
        a=np.rint(matches['uv_i'][k]).astype(int).clip([0,0],[w-1,h-1]);b=np.rint(matches['uv_j'][k]).astype(int).clip([0,0],[w-1,h-1])
        members.append((int(i),a,int(j),b));val[k]|=base[i,a[1],a[0]]|base[j,b[1],b[0]]
    for tid in np.unique(matches['track_id']):
        sel=matches['track_id']==tid;val[sel]=val[sel].any()
    # Fixed-point closure: all observations and 3 px neighborhoods of a heldout track.
    for _ in range(len(tracks)+1):
        exc=np.array([ndimage.binary_dilation(a,iterations=3) for a in base]);old=val.copy()
        for k,(i,a,j,b) in enumerate(members):val[k]|=exc[i,a[1],a[0]]|exc[j,b[1],b[0]]
        for tid in np.unique(matches['track_id']):
            sel=matches['track_id']==tid;val[sel]=val[sel].any()
        for k,(i,a,j,b) in enumerate(members):
            if val[k]:base[i,a[1],a[0]]=True;base[j,b[1],b[0]]=True
        if np.array_equal(val,old):break
    hold=np.array([ndimage.binary_dilation(a,iterations=3) for a in base]).ravel()
    normal_excluded=np.array([ndimage.binary_dilation(a,iterations=10) for a in base]).ravel()
    original=matches['validation'].copy();matches['validation']=val
    np.savez_compressed(out/'matches.npz',**matches)
    np.savez_compressed(out/'split.npz',validation=base.ravel(),excluded=hold,fit=~hold,normal_excluded=normal_excluded)
    c.json_write(out/'tracks.json',tracks)
    # Verify every known fit track observation is outside heldout neighborhoods.
    mixed=0
    for k,(i,a,j,b) in enumerate(members):
        if not val[k]:mixed+=int(hold[i*h*w+a[1]*w+a[0]] or hold[j*h*w+b[1]*w+b[0]])
    assert mixed==0
    legacy_contamination=int(np.sum(~original&val))
    c.json_write(out/'split_audit.json',dict(mixed=mixed,fit_correspondences=int((~val).sum()),validation_correspondences=int(val.sum()),
        original_fit_now_heldout=legacy_contamination,fit_observations=int((~hold).sum()),heldout_with_halo=int(hold.sum()),
        normal_fit_observations=int((~normal_excluded).sum()),split_method='seed0 tile holdout + full known tracks fixed-point closure + 3px halo; 21px normals exclude 10px halo',
        limitations='Known SIFT tracks only; undetected physical correspondences may cross split. RGB joint inference shared. Internal consistency only.'))
    rows=[]
    for p,frame in zip(d['image_paths'],d['frames']):
        rec=c.record(p);assert rec['sha256']==frame['sha256'];rows.append(rec)
    c.json_write(out/'inputs.json',dict(files=d['inputs']+rows,arrays={k:dict(shape=list(d[k].shape),dtype=str(d[k].dtype),sha256=ahash(d[k])) for k in ['depth','k','e','raw_xyz','uv','raw_rgb','fid']},
        preprocessing=(f"Omega max_size 512: original sizes={[f['original_wh'] for f in d['frames']]} -> {list(d['depth'].shape[1:])}; crop boxes={[f.get('crop_box') for f in d['frames']]}; SAM uses processed RGB" if d['dataset'].startswith(('eth3d-','kitti-')) else 'Omega max_size 512: 640x480 -> 512x384, no crop; raw images are normalized preprocessed RGB; SAM nearest mapping from original'),
        camera_convention='X_camera=R X_world+t; C=-R^-1 t; depth is camera Z; R not assumed exactly orthonormal',
        annotations='NONE; no human labels or H4g mask/plane inputs',frame_indices=([f['index'] for f in d['frames']] if d['dataset'].startswith(('eth3d-','kitti-')) else [30,40,50] if d['dataset']=='tum-freiburg1_desk' else [100,110,120])))
    return json.loads((out/'split_audit.json').read_text())

def controls():
    rng=np.random.default_rng(0);xy=rng.uniform(-.5,.5,(1200,2));x=np.c_[xy,np.full(1200,2.)];f=np.repeat(np.arange(3),400)
    wall=fit_plane(x,x[:,2],f);assert wall['valid']
    curve=x.copy();curve[:,2]+=1.8*np.sum(xy**2,axis=1);curved=fit_plane(curve,curve[:,2],f);assert not curved['valid']
    line=np.c_[np.linspace(-1,1,1200),np.zeros(1200),np.full(1200,2.)];assert not fit_plane(line,line[:,2],f)['valid']
    small=x[:60];assert fit_plane(small,small[:,2],f[:60])['valid']
    q=np.c_[xy,np.ones(1200)];d=dict(q=q,center_points=np.zeros_like(q));p=np.array(wall['plane']);moved={}
    for error in [.5,1.,5.]:
        new,z,ok=intersect(d,np.arange(1200),p);assert ok.all();assert np.max(abs(new@p[:3]+p[3]))<1e-12
        moved[str(error)]=dict(raw_z=2*(1+error),recovered_z=float(z.mean()),max_relative_move=None)
    # λ grid uses synthetic curved vs planar model selection, not real validation.
    grid=[]
    for raw,complexity,unknown in itertools.product([.5,1.,2.],[.01,.02,.05],[.4,.6,.8]):
        eplane=raw*np.mean(hcost((x@p[:3]+p[3])/x[:,2]/.005))+complexity
        ecurve=raw*np.mean(hcost((curve@p[:3]+p[3])/curve[:,2]/.005))+complexity
        score=int(eplane<unknown)+int(ecurve>unknown)
        grid.append(dict(lambda_raw=raw,lambda_complex=complexity,lambda_unknown=unknown,control_score=score,
            planar_loss=float(eplane),curved_forced_plane_loss=float(ecurve)))
    eligible=[r for r in grid if r['control_score']==2]
    chosen=min(eligible,key=lambda r:abs(r['lambda_raw']-1)+abs(r['lambda_complex']-.02)+abs(r['lambda_unknown']-.6))
    # Geometry relations may remain free without independent RGB evidence.
    angles=[0,60,90];relations=[dict(angle=a,geometry_hypothesis='parallel' if a<=15 else 'orthogonal' if abs(a-90)<=20 else 'free',selected='uncertain',reason='independent RGB evidence absent') for a in angles]
    a=np.zeros((40,40),bool);a[2:38,2:38]=True;b=np.zeros_like(a);b[10:25,10:25]=True
    assert (a&b).sum()==b.sum() and (a&~b).sum()>0
    # Rings retain holes, disjoint pieces and borders, instead of a convex hull.
    hole=a&~b;contours,hierarchy=c.cv2.findContours(hole.astype('uint8'),c.cv2.RETR_TREE,c.cv2.CHAIN_APPROX_SIMPLE);assert len(contours)==2
    negative=dict(q=q,center_points=np.zeros_like(q));_,_,ok=intersect(negative,np.arange(1200),np.array([0.,0.,1.,2.]));assert not ok.any()
    return dict(planar=wall,curved=curved,large_error_recovery=moved,grid=grid,chosen=chosen,relations=relations,
        checked=['unit normal','collinear support rejection','small plane','curved not forced planar','negative intersection','50/100/500pct depth errors',
            'nested masks and differences','rings and holes','nonorthogonal free hypothesis'],
        deferred_integration_controls=['association cycles and order','merge/split IDs','registry previous-version restoration','pure rotation observability audit'])

def run():
    # This entry point reproduces the historical TUM contract. ETH3D has its own prepare/freeze path.
    require_active_dataset('tum-freiburg1_desk')
    st=Stage('I0')
    try:
        out=st.path/'artifacts/contract';out.mkdir();syn=controls()
        from controls import run as integration_run
        integration=integration_run();c.json_write(out/'integration_controls.json',integration)
        cfg=CFG|{k:v for k,v in syn['chosen'].items() if k.startswith('lambda_')}
        c.json_write(out/'synthetic_controls.json',syn);c.json_write(out/'config_resolved.json',cfg)
        audits={}
        for name in ['tum-freiburg1_desk','tum-freiburg1_desk-extra']:
            d=load(name);audits[name]=freeze_split(d,out/name,st)
        d=load();legacy=m.load(ROOT/'results/camera_fov_alignment/tum-freiburg1_desk-C1-20261112-001/stages/C1/artifacts/baseline/matches/matches.npz')
        a,b,w,_=c.build_system(d,m.subset(legacy,~legacy['validation']));beta,hist,conv=c.solve_irls(a,b,w)
        with np.load(HIST/'proposed_not_selected/pointmap.npz') as z:
            beta_error=float(np.max(abs(beta-z['beta'])));xyz_error=float(np.max(abs(c.points(d,beta)-z['xyz'])))
        assert beta_error<1e-10 and xyz_error<1e-10
        c.json_write(out/'c3a_reproduction.json',dict(beta=beta.tolist(),beta_max_error=beta_error,xyz_max_error=xyz_error,converged=conv,
            source=c.record(HIST/'proposed_not_selected/pointmap.npz'),solver_history=hist))
        c.json_write(st.path/'evaluation/synthetic_controls.json',syn)
        c.json_write(st.path/'evaluation/integration_controls.json',integration)
        c.json_write(st.path/'evaluation/splits.json',audits)
        st.finish(dict(decision='CONTRACT_FROZEN_WITH_EXPLICIT_SPLIT_AMENDMENT',c3a_beta_max_error=beta_error,c3a_xyz_max_error=xyz_error,splits=audits,
            synthetic_control_status='geometry passed; integration checks scheduled I4/I6/I8',weights_selected_on_synthetic_only=True),
            '# I0 입력·좌표·split 동결\n\n기존 C3a의 같은 solver·fit split을 재실행하여 실제 proposed β/XYZ를 검증했다. '
            '주/추가 실내 입력 hash와 고정 관측 ID를 동결했다.\n\n'
            '계획 보완: 기존 C3a split 재현은 역사적 audit로 보존한다. 새 타일 보류 영역 및 알려진 전체 track의 3px 주변과 겹치는 fit 대응을 '
            '제거한 I2 주 solve를 별도 수행한다. 따라서 주 I2 β는 historical C3a와 다를 수 있다. 역사적 B1은 별도 비교로 남긴다. '
            '이는 동일한 fit/validation 분리를 FoV와 plane에 적용하기 위한 변경이며 실제 validation 점수로 설정을 고르지 않는다.\n\n'
            '합성 λ grid는 평면/곡면 제어를 통과한 후보 중 사전 기본값에 가장 가까운 조합을 선택했다. 나머지 λ와 scale은 사전 설정이며 최적값이라고 주장하지 않는다. '
            '관계·순서·lineage 통합 제어는 해당 구현 단계에서 검사한다. 수동 평가 annotation은 없으므로 소속 정확도는 평가할 수 없다.')
    except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
