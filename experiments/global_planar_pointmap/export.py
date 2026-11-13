"""I7-I9: fixed-ray maps, state-bound registries, finite observed contours and comparisons."""
from core import *
import solve

def project_map(d,planes,label):
    xyz=d['xyz'].copy();accepted=np.zeros(len(xyz),bool);target=d['d0'].copy();reason=np.zeros(len(xyz),np.uint8);pids=label.copy()
    for p in planes:
        ii=np.flatnonzero(label==p['plane_id'])
        if not len(ii):continue
        pp=np.array(p['plane']);new,z,ok=intersect(d,ii,pp);xyz[ii[ok]]=new[ok];accepted[ii[ok]]=True;target[ii[ok]]=z[ok];reason[ii[~ok]]=2;pids[ii[~ok]]=-1
    assert np.array_equal(xyz[~accepted],d['xyz'][~accepted])
    error=0.;equation=0.
    for f in range(3):
        ii=d['fid']==f;uv,z,_=c.project(xyz[ii],d['k'][f],d['e'][f],*d['depth'].shape[1:]);error=max(error,float(np.max(abs(uv-d['uv'][ii]))));assert (z>0).all()
    for p in planes:
        ii=pids==p['plane_id']
        if ii.any():equation=max(equation,float(abs(xyz[ii]@np.array(p['plane'])[:3]+p['plane'][3]).max()))
    assert error<1e-5 and equation<1e-9
    return xyz,pids,accepted,target,reason,dict(count=len(xyz),self_projection_max_pixel=error,plane_equation_max=equation,unchanged_unknown_bitwise=True,
        unit_normals=all(abs(np.linalg.norm(p['plane'][:3])-1)<1e-12 for p in planes),max_relative_move=None,
        relative_depth_move=c.stats(abs(target[accepted]-d['d0'][accepted])/d['d0'][accepted]),moved_over_100pct=int(np.sum(abs(target-d['d0'])/d['d0']>1)))

def visibility(d,xyz):
    n,h,w=d['depth'].shape;size=h*w;rows=[]
    for i,j in itertools.permutations(range(n),2):
        block=slice(i*size,(i+1)*size);baseuv,_,base=c.project(d['xyz'][block],d['k'][j],d['e'][j],h,w);uv,_,after=c.project(xyz[block],d['k'][j],d['e'][j],h,w)
        loss=float(np.sum(base&~after)/max(1,base.sum()));before_pixels=np.unique(np.rint(baseuv[base]).astype(int),axis=0);after_pixels=np.unique(np.rint(uv[after]).astype(int),axis=0)
        rows.append(dict(source=i,target=j,baseline_frustum_count=int(base.sum()),retained_frustum_count=int((base&after).sum()),frustum_loss_fraction=loss,
            baseline_pixel_coverage=float(len(before_pixels)/(h*w)),proposed_pixel_coverage=float(len(after_pixels)/(h*w)),passed=loss<=.005))
    return dict(pairs=rows,passed=all(r['passed'] for r in rows),maximum_frustum_loss=max(r['frustum_loss_fraction'] for r in rows),
        maximum_pixel_coverage_loss=max(r['baseline_pixel_coverage']-r['proposed_pixel_coverage'] for r in rows),reference='B1 I2 diagnostic proposed; frustum and actual unique pixel coverage separate')

def reproject(dataset):
    st=Stage('I7',dataset,[latest('I6',dataset)])
    try:
        d=load(dataset,True);planes,ids,fs=solve.registry_load(dataset,'I6')
        with np.load(latest('I6',dataset)/'artifacts/optimization/assignments.npz') as z:label=z['plane_id']
        xyz,pids,acc,target,reason,checks=project_map(d,planes,label);cov=visibility(d,xyz)
        out=st.path/'artifacts/projections';out.mkdir()
        np.savez_compressed(out/'proposed.npz',xyz=xyz,plane_id=pids,accepted=acc,target_depth=target,reason=reason,observation_id=d['ids'])
        retained=xyz if cov['passed'] else d['xyz'];retained_pid=pids if cov['passed'] else np.full(len(pids),-1,np.int32)
        np.savez_compressed(out/'retained.npz',xyz=retained,plane_id=retained_pid,retained_state=np.array('proposed' if cov['passed'] else 'initial'))
        for name,x,p in [('initial',d['xyz'],np.full(len(pids),-1,np.int32)),('proposed',xyz,pids),('retained',retained,retained_pid)]:
            ply_write(out/f'{name}_pixel_rgb.ply',d,x,p,d['raw_rgb'])
        rows=[]
        for f in range(3):
            rgb=[]
            for x in [d['xyz'],xyz]:
                _,win,_=c.front(x,d['k'][f],d['e'][f],*d['depth'].shape[1:]);photo=np.zeros_like(d['rgb'][f]);hit=win>=0;photo[hit]=d['raw_rgb'][win[hit]];rgb.append(photo)
            rows.append([d['rgb'][f],*rgb])
        c.panel(st.path/'artifacts/figures/initial_proposed.png',rows,['Original RGB','B1 initial','A4 proposed'])
        st.finish(dict(decision='HARD_REPROJECTION_PASSED',checks=checks,visibility=cov,accepted=int(acc.sum()),retained='proposed' if cov['passed'] else 'initial'),
            '# I7 전체 frame 재투영\n\n확정 소속 전체를 같은 world plane과 자기 픽셀 광선의 교차로 이동했다. 최대 이동 한도는 없으며 수치 평행·음의 깊이·비유한 교차만 거절한다. '
            'plane 식·자기 투영·unit normal·unknown XYZ bitwise 보존을 검사하고 initial/proposed/retained PLY를 모두 생성했다. '
            'B1 기준 frustum loss가 0.5 percentage point를 넘으면 retained는 initial이다. proposed는 삭제하지 않는다.')
    except Exception as e:st.fail(e);raise

def contours(d,xyz,pids,planes):
    n,h,w=d['depth'].shape;out=[]
    for p in planes:
        pp=np.array(p['plane']);origin,u,v=plane_basis(pp);views=[]
        for f in range(n):
            mask=(pids[f*h*w:(f+1)*h*w]==p['plane_id']).reshape(h,w)
            loops,hier=c.cv2.findContours(mask.astype('uint8'),c.cv2.RETR_TREE,c.cv2.CHAIN_APPROX_SIMPLE)
            rings=[]
            for k,loop in enumerate(loops):
                uv=loop[:,0];ii=f*h*w+uv[:,1]*w+uv[:,0];xy=np.c_[(xyz[ii]-origin)@u,(xyz[ii]-origin)@v]
                border=(uv[:,0]==0)|(uv[:,0]==w-1)|(uv[:,1]==0)|(uv[:,1]==h-1)
                # Boundary labels express observation uncertainty. A hole is NOT asserted physical.
                labels=[];class_evidence=[]
                for vertex,(u0,v0) in enumerate(uv):
                    if border[vertex]:labels.append('image_border');class_evidence.append('exact image extent');continue
                    neighbors=np.array([(int(v0)+dy)*w+int(u0)+dx for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]])+f*h*w
                    other=neighbors[pids[neighbors]!=p['plane_id']]
                    if not len(other):labels.append('segmentation_uncertain');class_evidence.append('no exterior neighbor');continue
                    _,plane_z,ok=intersect(d,other,pp);front=ok&(d['d0'][other]<plane_z*.98)
                    adjacent=pids[other]>=0
                    if np.any(front):labels.append('occlusion_boundary');class_evidence.append('original exterior depth in front of ray-plane surface; provisional')
                    elif np.any(adjacent):labels.append('observed_surface_edge');class_evidence.append('adjacent accepted plane; physical edge remains uncertain')
                    else:labels.append('segmentation_uncertain');class_evidence.append('mask boundary without independent physical-edge evidence')
                rings.append(dict(ring_id=k,parent=int(hier[0,k,3]),is_hole=bool(hier[0,k,3]>=0),pixel_uv=uv.tolist(),plane_local_uv=xy.tolist(),
                    boundary_types=labels,boundary_evidence=class_evidence,physical_hole=False,source='assigned observed view contour, no inter-view hull fill',unobserved_extension='unknown'))
            views.append(dict(frame=f,rings=rings,assigned_count=int(mask.sum()),disconnected_components=sum(r['parent']==-1 for r in rings)))
        out.append(dict(plane_id=p['plane_id'],origin=origin.tolist(),basis_u=u.tolist(),basis_v=v.tolist(),normal=pp[:3].tolist(),views=views,
            union_policy='per-view observed loops retained separately; occluded/unseen areas not filled'))
    return out

def intersection_records(planes,boundaries,relations_):
    records=[];byid={b['plane_id']:b for b in boundaries}
    for rel in relations_:
        a,b=rel['a'],rel['b'];pa,pb=np.array(planes[a]['plane']),np.array(planes[b]['plane']);direction=np.cross(pa[:3],pb[:3]);norm=np.linalg.norm(direction)
        if norm<1e-8:
            if rel['selected']=='parallel':records.append(dict(a=a,b=b,type='parallel',infinite_line=None,observed_intervals=[]))
            continue
        direction/=norm;point=np.linalg.lstsq(np.vstack([pa[:3],pb[:3],direction]),np.array([-pa[3],-pb[3],0.]),rcond=None)[0]
        intervals=[]
        # Store only support actually near the line; no global min/max over disconnected faces.
        for pid in [a,b]:
            boundary=byid[pid];o,u,v=[np.array(boundary[k]) for k in ['origin','basis_u','basis_v']]
            for view in boundary['views']:
                for ring in view['rings']:
                    xy=np.array(ring['plane_local_uv'])
                    if not len(xy):continue
                    x=o+xy[:,0,None]*u+xy[:,1,None]*v;t=(x-point)@direction;dist=np.linalg.norm(x-point-t[:,None]*direction,axis=1)
                    near=dist<.005*planes[pid]['fit']['reference_depth']
                    # Consecutive runs are kept separate, avoiding invented bridge segments.
                    labels,count=ndimage.label(near)
                    for k in range(1,count+1):
                        tt=t[labels==k]
                        if len(tt)>=2:intervals.append(dict(plane_id=pid,frame=view['frame'],ring_id=ring['ring_id'],t=[float(tt.min()),float(tt.max())],status='candidate_boundary_support',physical_adjacency_confirmed=False))
        if intervals or rel['selected'] in ['parallel','orthogonal']:
            records.append(dict(a=a,b=b,type='intersection',point=point.tolist(),direction=direction.tolist(),observed_intervals=intervals,shared_vertex_candidates=[],adjacency='uncertain'))
    return records

def bundle_verify(out):
    manifest=json.loads((out/'manifest.json').read_text())
    for rec in manifest['files']:
        path=out/rec['name'];assert c.record(path)['sha256']==rec['sha256'],f'bundle hash mismatch: {path}'
    registry=json.loads((out/'planes.json').read_text());z=np.load(out/'pointmap.npz');ass=np.load(out/'assignments.npz')
    digest=hashlib.sha256((ahash(z['xyz_refined'])+ahash(ass['plane_id'])+json.dumps([p['plane'] for p in registry['planes']],sort_keys=True)).encode()).hexdigest()
    assert digest==manifest['state_hash']==registry['state_hash']==str(z['state_hash'])
    for p in registry['planes']:
        ii=ass['plane_id']==p['plane_id']
        if ii.any():assert np.max(abs(z['xyz_refined'][ii]@np.array(p['plane'])[:3]+p['plane'][3]))<1e-9
    b=json.loads((out/'plane_boundaries.json').read_text())
    for plane in b:
        for view in plane['views']:
            for ring in view['rings']:
                xy=np.array(ring['plane_local_uv']);o,u,v=[np.array(plane[k]) for k in ['origin','basis_u','basis_v']]
                restored=o+xy[:,0,None]*u+xy[:,1,None]*v
                uv=np.array(ring['pixel_uv']);f=view['frame'];ids=f*512*384+uv[:,1]*512+uv[:,0]
                assert np.max(abs(restored-z['xyz_refined'][ids]),initial=0)<1e-8
    return dict(hash_binding=True,assignment_plane_equations=True,boundary_roundtrip=True,observation_ids_unique=len(np.unique(z['observation_id']))==len(z['observation_id']))

def write_bundle(out,d,xyz,pids,planes,ids,fits,state,relations_,versions=None,tags=True):
    # Refuse a geometry/registry mismatch before writing ANY export file.
    for p in planes:
        ii=pids==p['plane_id']
        if ii.any():assert np.max(abs(xyz[ii]@np.array(p['plane'])[:3]+p['plane'][3]))<1e-9,'Refuse mismatched pointmap/registry'
    out.mkdir(parents=True);planes=json.loads(json.dumps(planes));N=len(xyz);sp=split_load(d['dataset']);n,h,w=d['depth'].shape
    for p in planes:
        ii=np.flatnonzero(pids==p['plane_id']);p['active']=bool(len(ii));p['assigned_count']=len(ii);p['assigned_by_frame']={str(f):int(np.sum(d['fid'][ii]==f)) for f in range(n)}
        p['coordinate_frame']='Omega world';p['units']='model units';p['sign_convention']='largest absolute normal component positive';p['state']=state
        p['fit_residual_original']=c.stats(abs(d['xyz'][fits[p['plane_id']]]@np.array(p['plane'])[:3]+p['plane'][3])/d['d0'][fits[p['plane_id']]])
        hh=ii[sp['validation'][ii]];p['holdout_residual_original']=c.stats(abs(d['xyz'][hh]@np.array(p['plane'])[:3]+p['plane'][3])/d['d0'][hh])
        o,u,v=plane_basis(np.array(p['plane']));p|=dict(origin=o.tolist(),basis_u=u.tolist(),basis_v=v.tolist(),change_relative_depth=c.stats(np.linalg.norm(xyz[ii]-d['xyz'][ii],axis=1)/d['d0'][ii]))
    statehash=hashlib.sha256((ahash(xyz)+ahash(pids)+json.dumps([p['plane'] for p in planes],sort_keys=True)).encode()).hexdigest()
    c.json_write(out/'planes.json',dict(schema_version='1.0',state=state,state_hash=statehash,planes=planes))
    np.savez_compressed(out/'pointmap.npz',xyz_raw=d['raw_xyz'],xyz_fov=d['xyz'],xyz_refined=xyz,rgb=d['raw_rgb'],observation_id=d['ids'],frame_id=d['fid'],pixel_uv=d['uv'],
        intrinsics=d['k'],extrinsics=d['e'],beta=d['beta'],state_hash=np.array(statehash),state=np.array(state))
    region=np.full(N,-1,np.int32);rs,regionids,_=solve.regions_load(d['dataset'])
    for p in planes:
        for rid in p['source_regions']:
            ii=regionids[rid];sel=pids[ii]==p['plane_id'];region[ii[sel]]=rid
    np.savez_compressed(out/'assignments.npz',observation_id=d['ids'],region_id=region,plane_id=pids,status=(pids>=0).astype(np.uint8),reason=np.where(pids>=0,1,0).astype(np.uint8))
    c.json_write(out/'schema.json',dict(observation_id='int64 [0,N)',plane_id='int32, -1 unknown; IDs never reused',region_id='int32, -1 no assigned source region',
        status={'0':'unknown_or_unaccepted','1':'assigned_and_projected'},reason={'0':'no accepted plane in this state','1':'fixed ray plane intersection'},state_hash='SHA256(array hashes refined XYZ, int32 plane IDs, serialized plane coefficients)'))
    support={}
    for p,fi in zip(planes,fits):
        k=p['plane_id'];ii=np.flatnonzero(pids==k);support[f'fit_{k}']=fi;support[f'holdout_{k}']=ii[sp['validation'][ii]];support[f'assigned_{k}']=ii
    np.savez_compressed(out/'plane_support.npz',**support)
    if tags:shutil.copy2(latest('I1',d['dataset'])/'artifacts/tags/observation_mask_links.npz',out/'observation_mask_links.npz')
    colors=np.full((N,3),120,np.uint8);palette=np.random.default_rng(0).integers(20,255,(max(1,len(planes)),3),dtype=np.uint8);colors[pids>=0]=palette[pids[pids>=0]]
    for name,col in [('pixel_rgb',d['raw_rgb']),('frame_colors',c.PALETTE[d['fid']]),('plane_colors',colors)]:ply_write(out/f'pointcloud_{name}.ply',d,xyz,pids,col)
    bounds=contours(d,xyz,pids,planes);c.json_write(out/'plane_boundaries.json',bounds)
    c.json_write(out/'plane_relations.json',dict(relations=relations_,intersections=intersection_records(planes,bounds,relations_)))
    vm=out/'view_masks';vm.mkdir()
    for f in range(n):np.savez_compressed(vm/f'frame_{f}.npz',plane_id=pids[f*h*w:(f+1)*h*w].reshape(h,w))
    with (out/'plane_versions.jsonl').open('w') as f:
        for row in (versions or []):f.write(json.dumps(row)+'\n')
        f.write(json.dumps(dict(state=state,state_hash=statehash,planes=planes))+'\n')
    c.json_write(out/'manifest.json',dict(schema_version='1.0',state=state,state_hash=statehash,point_count=N,files=[dict(name=str(p.relative_to(out)),**{k:v for k,v in c.record(p).items() if k!='path'}) for p in sorted(out.rglob('*')) if p.is_file()]))
    return bundle_verify(out)

def bundle(dataset):
    st=Stage('I8',dataset,[latest('I7',dataset)])
    try:
        d=load(dataset,True);planes,ids,fs=solve.registry_load(dataset,'I6');audit=json.loads((latest('I6',dataset)/'artifacts/optimization/optimization.json').read_text());path=latest('I7',dataset)/'artifacts/projections'
        with np.load(path/'proposed.npz') as z:xyz,pids=z['xyz'],z['plane_id']
        with np.load(path/'retained.npz') as z:ret,rp,state=z['xyz'],z['plane_id'],str(z['retained_state'])
        root=st.path/'artifacts/bundle';checks={}
        for name,x,p in [('initial',d['xyz'],np.full(len(pids),-1,np.int32)),('proposed',xyz,pids),('retained',ret,rp)]:
            checks[name]=write_bundle(root/name,d,x,p,planes,ids,fs,name,audit['relations'],audit.get('versions',[]))
        # Reject a deliberately mismatched state hash; do not alter original successful bundle.
        test=root/'mismatch_probe';mismatch_rejected=False;wrong=json.loads(json.dumps(planes))
        for p in wrong:p['plane'][3]+=.1
        try:write_bundle(test,d,xyz,pids,wrong,ids,fs,'wrong',audit['relations'],tags=False)
        except AssertionError:mismatch_rejected=True
        assert mismatch_rejected
        c.json_write(st.path/'evaluation/roundtrip.json',checks)
        st.finish(dict(decision='STATE_BOUND_BUNDLES_EXPORTED',states=checks,mismatch_rejected=mismatch_rejected,retained_geometry_state=state,
            limitations='Physical edge/occlusion labels provisional original-depth/adjacency evidence, not boundary GT.'),
            '# I8 pointmap·plane bundle\n\ninitial/proposed/retained 각각에 pointmap·확장 PLY 세 종류·CSR tag·소속·plane 정의·지원·버전·유한 경계·교선과 관측 interval을 저장했다. '
            '관측된 per-view rings/holes/분리 성분을 유지하며 convex hull로 미관측 영역을 메우지 않는다. plane-local 경계 round-trip과 상호 state/hash를 검증했다. '
            'PLY 추가 속성의 binary 재읽기도 통과했다.\n\n제한: 경계의 실제 물리 edge/가림 분류는 확정하지 않고 segmentation_uncertain/image_border로 보존한다. '
            '실제 mesh와 watertight 보장은 이번 범위에 포함하지 않는다.')
    except Exception as e:st.fail(e);raise

def match_metrics(d,xyz,pids):
    matches=m.load(split_path(d['dataset'])/'matches.npz');n,h,w=d['depth'].shape;rows=[]
    for i,j in itertools.combinations(range(n),2):
        sel=matches['validation']&(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j);ui=np.rint(matches['uv_i'][sel]).astype(int);uj=np.rint(matches['uv_j'][sel]).astype(int)
        ia=i*h*w+ui[:,1]*w+ui[:,0];ib=j*h*w+uj[:,1]*w+uj[:,0];delta=xyz[ia]-xyz[ib];scale=(d['d0'][ia]+d['d0'][ib])/2
        changed=(pids[ia]>=0)|(pids[ib]>=0)
        row=dict(pair=[i,j],tracks=len(ia),relative_3d=c.stats(np.linalg.norm(delta,axis=1)/scale),corrected=c.stats(np.linalg.norm(delta[changed],axis=1)/scale[changed]),
            non_target=c.stats(np.linalg.norm(delta[~changed],axis=1)/scale[~changed]),relative_z=c.stats(np.r_[abs(delta@d['e'][i,2,:3]),abs(delta@d['e'][j,2,:3])]/np.r_[scale,scale]))
        uv,_,_=c.project(xyz[ia],d['k'][j],d['e'][j],h,w);row['reprojection_pixel']=c.stats(np.linalg.norm(uv-uj,axis=1));rows.append(row)
    return rows

def arm_data(dataset,arm):
    d=load(dataset,True);rs,ri,rf=solve.regions_load(dataset)
    if arm in ['B0','B1']:
        return d,[],[],[],np.full(len(d['ids']),-1,np.int32),d['raw_xyz'] if arm=='B0' else d['xyz']
    if arm in ['A4','A5']:
        if arm=='A4':
            pp,ii,ff=solve.registry_load(dataset,'I6')
            with np.load(latest('I6',dataset)/'artifacts/optimization/assignments.npz') as z:lab=z['plane_id']
        else:d,pp,ii,ff,lab,audit=solve.optimize(dataset,False,arm)
    elif arm in ['A2','A3','A6']:
        pp,ii,ff=solve.registry_load(dataset)
        if arm=='A6':
            recs,_=solve.tags_load(dataset);semantic={r['mask_id'] for r in recs if r['source']=='grounded'}
            for p in pp:
                if not any(mid in semantic for mid in p['source_masks']):p['active']=False
        lab,_=solve.assignment(d,pp,ii)
        if arm=='A3':
            # Only structure effect: keep assignment fixed; optimize coefficients with other joint changes disabled.
            rel=json.loads((latest('I5',dataset)/'artifacts/relations/relations.json').read_text())
            active=[r for r in rel if r['selected'] in ['parallel','orthogonal']]
            if active:
                ps=np.array([p['plane'] for p in pp]);initial=ps.copy()
                def fun(v):
                    p=v.reshape(-1,4);p=p/np.linalg.norm(p[:,:3],axis=1,keepdims=True);r=[(p-initial).ravel()]
                    for rr in active:
                        a,b=rr['a'],rr['b'];r.append(np.array([p[a,:3]@p[b,:3]]) if rr['selected']=='orthogonal' else np.cross(p[a,:3],p[b,:3]))
                    return np.concatenate(r)
                result=least_squares(fun,ps.ravel(),max_nfev=200)
                for k,p in enumerate(pp):p['plane']=orient(result.x.reshape(-1,4)[k]).tolist()
    elif arm=='A1':
        pp=[];ii=[];ff=[]
        for r,ids,fit in zip(rs,ri,rf):
            if r['state']!='planar':continue
            k=len(pp);pp.append(dict(plane_id=k,plane=r['fit']['plane'],fit=r['fit'],active=True,source_regions=[r['region_id']],frames=[r['frame']]))
            ii.append(ids);ff.append(fit)
        lab,_=solve.assignment(d,pp,ii)
    elif arm=='A0':
        recs,masks=solve.tags_load(dataset);groups={}
        for r in recs:
            if r['source']=='grounded':groups.setdefault(r['semantic_tag'],[]).append(r)
        pp=[];ii=[];ff=[];sp=split_load(dataset)
        for tag,rows in sorted(groups.items()):
            ids=np.unique(np.concatenate([np.flatnonzero(masks[r['mask_id']])+r['frame']*512*384 for r in rows]));fi=ids[~sp['excluded'][ids]]
            ft=fit_plane(d['xyz'][fi],d['d0'][fi],d['fid'][fi])
            if 'plane' not in ft:continue
            k=len(pp);pp.append(dict(plane_id=k,plane=ft['plane'],fit=ft,active=True,source_regions=[],frames=sorted(set(d['fid'][ids].tolist()))));ii.append(ids);ff.append(fi)
        lab,_=solve.assignment(d,pp,ii)
    xyz,pids,_,_,_,_=project_map(d,pp,lab)
    return d,pp,ii,ff,pids,xyz

def comparison(dataset):
    st=Stage('I9',dataset,[latest('I8',dataset)]);review=FAMILY/'ply_review'/st.run_id;review.mkdir(parents=True)
    try:
        results=[];inventory=[];out=st.path/'artifacts/comparisons';out.mkdir()
        for arm in ['B0','B1','A0','A1','A2','A3','A4','A5','A6']:
            t=time.perf_counter();d,planes,ii,ff,pids,xyz=arm_data(dataset,arm)
            ply=review/f'{arm}_pixel_rgb.ply';ply_write(ply,d,xyz,pids,d['raw_rgb']);rec=c.record(ply);inventory.append(dict(arm=arm,**rec))
            row=dict(arm=arm,assigned_count=int((pids>=0).sum()),assigned_fraction=float(np.mean(pids>=0)),unknown_fraction=float(np.mean(pids<0)),planes=len(set(pids[pids>=0])),
                per_frame=[dict(frame=f,assigned_fraction=float(np.mean(pids[d['fid']==f]>=0))) for f in range(3)],
                heldout=match_metrics(d,xyz,pids),visibility=visibility(d,xyz),seconds=time.perf_counter()-t)
            byplane=[]
            for p in planes:
                ids=np.flatnonzero(pids==p['plane_id'])
                if len(ids):byplane.append(dict(plane_id=p['plane_id'],frames=sorted(set(d['fid'][ids].tolist())),count=len(ids),
                    original_thickness=c.stats(abs(d['xyz'][ids]@np.array(p['plane'])[:3]+p['plane'][3])),
                    proposed_equation=c.stats(abs(xyz[ids]@np.array(p['plane'])[:3]+p['plane'][3]))))
            row['per_plane']=byplane;results.append(row);st.log('arm',arm=arm,assigned=row['assigned_count'],planes=row['planes'])
            c.json_write(out/f'{arm}.json',row)
        for name,code in [('M1','H4f'),('M2','H4g')]:
            ps=sorted((ROOT/'results/c3a_plane_refinement').glob(f'tum-freiburg1_desk-{code}-*/stages/{code}/manifest.json'))
            if ps:inventory.append(dict(arm=name,historical_reference=c.record(ps[-1]),input_to_automatic_pipeline=False))
        c.json_write(st.path/'evaluation/arms.json',results);c.json_write(st.path/'evaluation/ply_inventory.json',inventory)
        table='\n'.join(f"| {r['arm']} | {r['planes']} | {r['assigned_fraction']:.4%} | {r['visibility']['maximum_frustum_loss']:.4%} |" for r in results)
        st.finish(dict(decision='EXPLORATORY_COMPARISON_WITH_UNMET_CONTRACTS',arms=len(results),raw_observations=len(d['ids']),
            scientific_verdict=dict(automatic_assignment='GT_NOT_EVALUATED; conservative proposals only',surface_cleanup='TECHNICAL_PLANARITY_ONLY',
                visibility='see proposed/retained per-arm guards',gt_accuracy='GT_NOT_EVALUATED'),
            limitations=['I3/I5/I6/I8 full plan gates not yet satisfied; see stage reports.',
                'A6 currently filters shared candidates by grounded provenance; full detector-only re-derivation not yet implemented.',
                'No pre-frozen human category annotations or completed user visual review; no category accuracy/generalization claim.']),
            '# I9 비교·추가 실내 전이\n\n같은 동결 split과 후보에서 B0/B1/A0–A6의 실제 PLY와 보류 대응·plane/view별 지표를 만들었다. '
            'M1/M2는 역사적 참고 경로만 기록했으며 자동 모델 입력에 넣지 않았다. 추가 실내는 과거 사용 구간이며 독립 장면 GT 검증이 아니다.\n\n'
            '| 군 | plane 수 | 확정 관측 비율 | 최대 frustum loss |\n| --- | --- | --- | --- |\n'+table+
            '\n\n미완료 조건과 비교군 제한을 metrics에 명시했다. plane 식 일치는 기술 검증이며 실제 표면 정확도는 아니다. '
            '육안 검토는 생성된 비교 이미지와 PLY를 통해 별도 기록해야 한다.',criteria=False)
    except Exception as e:st.fail(e);raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('code',choices=['I7','I8','I9']);parser.add_argument('--dataset',default='tum-freiburg1_desk');args=parser.parse_args()
    dict(I7=reproject,I8=bundle,I9=comparison)[args.code](args.dataset)
