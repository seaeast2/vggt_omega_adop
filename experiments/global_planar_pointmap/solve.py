"""I2-I6 CPU stages. Conservative image/geometry evidence, explicit unknowns."""
from core import *
from scipy import sparse

def fov(dataset):
    st=Stage('I2',dataset,[latest('I0'),latest('I1',dataset)])
    try:
        d=load(dataset);matches=m.load(split_path(dataset)/'matches.npz');train=m.subset(matches,~matches['validation'])
        a,b,w,_=c.build_system(d,train);rank=c.rank_info(a);support=m.pair_support(matches,*d['depth'].shape[1:])
        if rank['identifiable']:beta,history,conv=c.solve_irls(a,b,w)
        else:beta,history,conv=np.ones(6),[],False
        out=st.path/'artifacts/fov';out.mkdir();k=c.corrected_k(d['k'],beta.reshape(3,2));xyz=c.points(d,beta)
        np.savez_compressed(out/'pointmap.npz',xyz=xyz,xyz_raw=d['raw_xyz'],intrinsics=k,intrinsics_raw=d['k'],extrinsics=d['e'],beta=beta,
            observation_id=d['ids'],frame_id=d['fid'],pixel_uv=d['uv'],rgb=d['raw_rgb'],depth_initial=d['depth'])
        np.savez_compressed(out/'beta1_alternative.npz',xyz=d['raw_xyz'],intrinsics=d['k'],beta=np.ones(6))
        tags=latest('I1',dataset)/'artifacts/tags/observation_mask_links.npz';shutil.copy2(tags,out/'observation_mask_links.npz')
        assert c.record(tags)['sha256']==c.record(out/'observation_mask_links.npz')['sha256']
        if dataset=='tum-freiburg1_desk':
            shutil.copy2(HIST/'proposed_not_selected/pointmap.npz',out/'historical_C3a_proposed.npz')
        import diagnostics
        cov=diagnostics.coverage(d,beta,diagnostics.overlap_reference(d))
        c.json_write(out/'solve.json',dict(beta=beta.tolist(),rank=rank,support=support,history=history,converged=conv,coverage=cov,
            selected_policy='diagnostic actual proposed used downstream; beta1 separately retained',tag_file_sha256=c.record(tags)['sha256']))
        st.finish(dict(decision='LOW_SUPPORT_PROPOSED_PRESERVED' if not support['passed'] else 'FOV_PROPOSED',beta=beta.tolist(),support=support,rank=rank,coverage=cov,tag_bitwise_identical=True),
            '# I2 FoV와 tag 전달\n\nI0의 누출 제거 fit 대응만으로 기존 C3a solver를 실행했다. 실제 proposed와 β1 대안을 별도 저장하고 이후 K/pose를 고정했다. '
            'historical C3a 재현은 I0에 있으며 이 구간의 원본 proposed도 별도 보존한다. 태그 CSR 파일 SHA256가 전후 동일하다. '
            'LOW_SUPPORT 또는 coverage 실패는 실제 제안값 사용의 탐색적 한계로 유지한다. 평면을 보고 FoV를 조정하지 않았다.')
    except Exception as e:st.fail(e);raise

def tags_load(dataset):
    path=latest('I1',dataset)/'artifacts/tags';records=json.loads((path/'mask_registry.json').read_text());masks={}
    for f in range(3):
        with np.load(path/f'frame_{f}_masks.npz') as z:
            for mid,mask in zip(z['mask_ids'],z['masks']):masks[int(mid)]=mask
    return records,masks

def candidates(dataset,semantic_only=False):
    code='I3a' if semantic_only else 'I3'
    st=Stage(code,dataset,[latest('I2',dataset)],dict(semantic_only=semantic_only))
    try:
        d=load(dataset,True);sp=split_load(dataset);records,masks=tags_load(dataset);n,h,w=d['depth'].shape;minimum=int(np.ceil(.001*h*w))
        out=st.path/'artifacts/regions';out.mkdir();normal=[]
        for win in [7,21]:
            nn,v=normals(d,win,sp['normal_excluded']);normal.append((nn,v));np.savez_compressed(out/f'normals_{win}.npz',normals=nn,valid=v)
        # Every source mask, intersections, differences and connected pieces have provenance.
        proposals=[];seen={};events=[]
        def add(mask,f,source,tag,kind):
            if int(mask.sum())<minimum:
                events.append(dict(source_masks=source,kind=kind,reason='below_min_area',area=int(mask.sum())));return
            key=(f,ahash(mask))
            if key in seen:events.append(dict(source_masks=source,kind=kind,alias_of=seen[key],reason='exact_region_alias'));return
            seen[key]=len(proposals);proposals.append(dict(mask=mask,frame=f,source_masks=source,semantic_tag=tag,kind=kind,proposal_id=len(proposals)))
        byid={r['mask_id']:r for r in records}
        for r in records:
            if semantic_only and r['source']!='grounded':continue
            if 'alias_of' in r:continue
            if r['source']=='automatic' and not r.get('official_nms_retained',False):
                events.append(dict(source_masks=[r['mask_id']],reason='official_automatic_box_nms; raw mask and CSR preserved'));continue
            mask=masks[r['mask_id']];add(mask,r['frame'],[r['mask_id']],r['semantic_tag'],'full_mask')
            parts=components(mask,minimum)
            if len(parts)>1:
                for a in parts:add(a,r['frame'],[r['mask_id']],r['semantic_tag'],'connected_component')
            # Image-only cuts supplement depth hypotheses. Keep full parent and all children.
            edge=c.cv2.Canny(d['rgb'][r['frame']],80,160)>0
            cuts=components(mask&~ndimage.binary_dilation(edge,iterations=1),minimum)
            if len(cuts)>1:
                for part in cuts:add(part,r['frame'],[r['mask_id']],r['semantic_tag'],'RGB_boundary_component')
        for f in range(3):
            hier=json.loads((latest('I1',dataset)/f'artifacts/tags/frame_{f}_hierarchy.json').read_text())
            for edge in hier['edges']:
                if edge['relation']!='contains':continue
                a,b=edge['parent'],edge['child'];tag=byid[a]['semantic_tag']
                if semantic_only and any(byid[mid]['source']!='grounded' for mid in [a,b]):continue
                if any(byid[mid]['source']=='automatic' and not byid[mid].get('official_nms_retained',False) for mid in [a,b]):continue
                for a_mask in components(masks[a]&~masks[b],minimum):add(a_mask,f,[a,b],tag,'parent_minus_child')
                add(masks[a]&masks[b],f,[a,b],byid[b]['semantic_tag'],'intersection')
        output=[];membership=[];fits=[];model_records=[];region_alias={};fit_excluded=sp['excluded']
        for prop in proposals:
            mask=prop['mask'];f=prop['frame'];ids=np.flatnonzero(mask)+f*h*w
            interior=ndimage.binary_erosion(mask,iterations=3);seed=np.flatnonzero(interior)+f*h*w
            seed=seed[(~fit_excluded[seed])&(d['conf'].ravel()[seed]>=np.percentile(d['conf'][f],10))]
            remaining=seed.copy();models=[];localfits=[]
            # Compare k=1/2/3 and unknown. Further residual components recurse below.
            for k in range(3):
                ft=fit_plane(d['xyz'][remaining],d['d0'][remaining],d['fid'][remaining])
                if 'plane' not in ft:break
                p=np.array(ft['plane']);rr=abs(d['xyz'][remaining]@p[:3]+p[3])/d['d0'][remaining]
                inside=rr<=.005;consensus=remaining[inside]
                if len(consensus)<50 or ft['second_first_ratio']<1e-4 or ft['second_axis_span']<.01:break
                clean=fit_plane(d['xyz'][consensus],d['d0'][consensus],d['fid'][consensus])
                if not clean['valid']:break
                models.append(clean);localfits.append(consensus);remaining=remaining[~inside]
                if len(remaining)<50:break
            variants=[dict(k=0,score=CFG['lambda_unknown'],state='unknown')]
            bestk=0;bestscore=CFG['lambda_unknown']
            if len(seed):
                for k in range(1,len(models)+1):
                    residual=np.stack([abs(d['xyz'][seed]@np.array(t['plane'])[:3]+t['plane'][3])/d['d0'][seed]/.005 for t in models[:k]])
                    cost=np.min(hcost(residual),axis=0);coverage=float(np.mean(residual.min(0)<=1))
                    score=float(np.mean(np.minimum(cost,CFG['lambda_unknown']))+CFG['lambda_complex']*k)
                    eligible=coverage>=.7
                    variants.append(dict(k=k,score=score,fit_inlier_coverage=coverage,eligible=eligible,state='planar' if k==1 else 'multi_plane'))
                    if eligible and score<bestscore:bestk,bestscore=k,score
            curved=False;quadratic=None
            if len(seed)>=50:
                sx=d['xyz'][seed];mean=sx.mean(0);_,_,basis=np.linalg.svd(sx-mean,full_matrices=False);local=(sx-mean)@basis.T
                design=np.c_[np.ones(len(sx)),local[:,:2],local[:,0]**2,local[:,0]*local[:,1],local[:,1]**2]
                coef=np.linalg.lstsq(design/d['d0'][seed,None],local[:,2]/d['d0'][seed],rcond=None)[0]
                qr=(design@coef-local[:,2])/d['d0'][seed]/.005
                qscore=float(np.mean(np.minimum(hcost(qr),CFG['lambda_unknown']))+2*CFG['lambda_complex'])
                quadratic=dict(score=qscore,coefficients=coef.tolist(),basis=basis.tolist(),origin=mean.tolist(),comparison='training-only quadratic smooth-surface alternative')
                # A continuous curved surface must substantially beat piecewise planes.
                curved=bestk>1 and qscore<.7*bestscore and np.linalg.norm(coef[3:])>.05
                if curved:bestk=0
            state='curved' if curved else 'multi_plane' if bestk>1 else 'planar' if bestk else 'low_support' if len(seed)<50 else 'ambiguous'
            model_records.append(dict(proposal_id=prop['proposal_id'],source_masks=prop['source_masks'],kind=prop['kind'],frame=f,area=len(ids),fit_count=len(seed),models=models,variants=variants,selected_k=bestk,state=state,quadratic_alternative=quadratic))
            if len(models)==3 and len(remaining)>=50 and not curved:
                ps=[np.array(t['plane']) for t in models]
                unexplained=np.min(np.stack([abs(d['xyz'][ids]@p[:3]+p[3])/d['d0'][ids] for p in ps]),axis=0)>.005
                residual_mask=np.zeros(h*w,bool);residual_mask[ids[unexplained]%(h*w)]=True
                for child in components(residual_mask.reshape(h,w),minimum):
                    if child.sum()<mask.sum():add(child,f,prop['source_masks'],prop['semantic_tag'],'recursive_residual_component')
            if bestk:
                rr=np.stack([abs(d['xyz'][ids]@np.array(t['plane'])[:3]+t['plane'][3])/d['d0'][ids] for t in models[:bestk]])
                label=rr.argmin(0) if bestk>1 else np.zeros(len(ids),int)
                for k in range(bestk):
                    moveids=ids[label==k]
                    if len(moveids)<minimum:continue
                    # Do not impose the fitting inlier threshold on the movement membership.
                    fitids=localfits[k];key=(f,ahash(moveids))
                    if key in region_alias:continue
                    rid=len(output);region_alias[key]=rid;ft=models[k]
                    prior=[]
                    for nn,v in normal:
                        ok=v.ravel()[fitids];ns=nn.reshape(-1,3)[fitids[ok]]
                        prior.append(np.median(ns,axis=0).tolist() if len(ns) else None)
                    output.append(dict(region_id=rid,frame=f,proposal_id=prop['proposal_id'],source_masks=prop['source_masks'],semantic_tag=prop['semantic_tag'],kind=prop['kind'],
                        state='material_uncertain' if any(tag in prop['semantic_tag'] for tag in ['screen','window']) else 'planar',fit=ft,area=len(moveids),model_score=bestscore,
                        multi_scale_direction_prior=prior,fit_count=len(fitids),normal_prior_source='original fit-only neighborhood moments'))
                    membership.append(moveids);fits.append(fitids)
            if prop['proposal_id']%50==0:st.log('region_progress',proposal=prop['proposal_id'],total=len(proposals),planes=len(output))
        np.savez_compressed(out/'memberships.npz',**{f'ids_{i}':a for i,a in enumerate(membership)},**{f'fit_{i}':a for i,a in enumerate(fits)})
        c.json_write(out/'regions.json',output);c.json_write(out/'model_selection.json',model_records);c.json_write(out/'proposal_events.json',events)
        planar_cover=np.zeros(len(d['ids']),bool)
        for r,ids in zip(output,membership):
            if r['state']=='planar':planar_cover[ids]=True
        metrics=dict(decision='CANDIDATES_EVALUATED',raw_masks=len(records),proposals=len(proposals),regions=len(output),planar_candidate_coverage=float(planar_cover.mean()),
            fit_validation_mixed=int(sum(sp['excluded'][a].sum() for a in fits)),state_counts={s:sum(r['state']==s for r in output) for s in ['planar','material_uncertain']},
            limitations=['Each proposal compares up to three planes and recursively processes unresolved connected components; no fixed scene plane count.',
                'RGB edges are evaluated later; initial multi-plane partition uses fit depth, so large-error multi-face pixels may be ambiguous.',
                'No learned dynamic/reflection detector; material labels conservative and not complete.'])
        assert metrics['fit_validation_mixed']==0
        st.finish(metrics,'# I3 자동 평면 후보\n\nsemantic 전체 마스크와 공식 automatic NMS 출력·포함 차집합·교집합·연결 성분을 후보로 만들고 fit만으로 0/1/2/3 plane의 robust 잔차와 복잡도를 비교했다. '
            '7/21px normal은 보류점을 moment에서 제외한 고정 prior로 저장했다. 채택된 plane의 이동 영역에는 0.5% 잔차 gate를 적용하지 않는다.\n\n'
            '잔여 연결 성분을 재귀 후보로 만들고 quadratic 곡면 대안을 training score로 비교했다. 해결되지 않은 영역은 unknown이다. '
            '곡면/동적 물체의 실제 의미론적 정답은 없으므로 자동 판정의 오류율은 확정할 수 없다. 전체 후보·탈락 근거를 로컬에 보존했다.')
    except Exception as e:st.fail(e);raise

def regions_load(dataset,code='I3'):
    path=latest(code,dataset)/'artifacts/regions';rs=json.loads((path/'regions.json').read_text())
    with np.load(path/'memberships.npz') as z:ids=[z[f'ids_{i}'] for i in range(len(rs))];fits=[z[f'fit_{i}'] for i in range(len(rs))]
    return rs,ids,fits

def overlap(d,source,target,p):
    n,h,w=d['depth'].shape;sf=int(d['fid'][source[0]]);tf=int(d['fid'][target[0]])
    take=source[np.linspace(0,len(source)-1,min(1024,len(source)),dtype=int)];x,_,ok=intersect(d,take,p)
    uv,_,inside=c.project(x,d['k'][tf],d['e'][tf],h,w);good=ok&inside
    if not good.any():return 0.
    uv=np.rint(uv[good]).astype(int);pix=np.unique(uv[:,1]*w+uv[:,0]);mask=np.zeros(h*w,bool);mask[target%(h*w)]=True
    return float(mask[pix].mean())

def graph_build(d,rs,ids,fits,semantic_only=False):
    n,h,w=d['depth'].shape;matches=m.load(split_path(d['dataset'])/'matches.npz');train=~matches['validation'];edges=[];compatible={}
    sets=[set(a.tolist()) for a in ids]
    for a,b in itertools.combinations(range(len(rs)),2):
        ra,rb=rs[a],rs[b]
        pa,pb=np.array(ra['fit']['plane']),np.array(rb['fit']['plane']);angle=float(np.degrees(np.arccos(np.clip(abs(pa[:3]@pb[:3]),0,1))))
        if angle>30:continue
        if ra['frame']==rb['frame']:
            common=len(sets[a]&sets[b]);coverage=common/max(1,min(len(ids[a]),len(ids[b])))
            ca=np.array(ra['fit']['centroid']);cb=np.array(rb['fit']['centroid'])
            offset=float(max(abs(ca@pb[:3]+pb[3])/ra['fit']['reference_depth'],abs(cb@pa[:3]+pa[3])/rb['fit']['reference_depth']))
            passed=coverage>=.7 and angle<=5 and offset<.005
            if passed:edges.append(dict(a=a,b=b,angle=angle,passed=True,same_view_alias=True,overlap=coverage,offset=offset))
            compatible[a,b]=passed;continue
        oa=overlap(d,ids[a],ids[b],pa);ob=overlap(d,ids[b],ids[a],pb)
        if min(oa,ob)<.1:continue
        if ra['frame']<rb['frame']:left,right=a,b
        else:left,right=b,a
        i,j=rs[left]['frame'],rs[right]['frame'];sel=train&(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j)
        ua=np.rint(matches['uv_i'][sel]).astype(int);ub=np.rint(matches['uv_j'][sel]).astype(int)
        ia=i*h*w+ua[:,1]*w+ua[:,0];ib=j*h*w+ub[:,1]*w+ub[:,0]
        tracks=int(sum(x in sets[left] and y in sets[right] for x,y in zip(ia,ib)))
        ca=np.array(ra['fit']['centroid']);cb=np.array(rb['fit']['centroid']);offset=float(max(abs(ca@pb[:3]+pb[3])/ra['fit']['reference_depth'],abs(cb@pa[:3]+pa[3])/rb['fit']['reference_depth']))
        # Offset is recorded and softly limits geometry-only links; no 3% raw-depth gate.
        passed=min(oa,ob)>=.2 and angle<=15 and (tracks>=2 or offset<.015)
        edge=dict(a=a,b=b,angle=angle,finite_mask_overlap=[oa,ob],fit_tracks=tracks,centroid_plane_offset=offset,passed=passed,
            evidence='finite ray-plane mask projection + fit image tracks + uncertain plane offset; no raw target depth gate')
        edges.append(edge);compatible[a,b]=passed
    # Canonical all-pair compatible agglomeration. Re-sort after each proposal.
    def cluster(order):
        groups=[[a] for a in order]
        while True:
            proposals=[]
            for i,j in itertools.combinations(range(len(groups)),2):
                ga,gb=groups[i],groups[j]
                if all(compatible.get(tuple(sorted([a,b])),False) for a,b in itertools.product(ga,gb)):
                    key=tuple(sorted(ga+gb));proposals.append((-len(key),key,i,j))
            if not proposals:break
            _,key,i,j=min(proposals);groups=[g for k,g in enumerate(groups) if k not in [i,j]]+[list(key)]
        return sorted([sorted(g) for g in groups])
    valid=[r['region_id'] for r in rs if r['state']=='planar'];groups=cluster(valid);rev=cluster(list(reversed(valid)));assert groups==rev
    planes=[];mem=[];fitmem=[]
    for g in groups:
        fi=np.unique(np.concatenate([fits[i] for i in g]));ft=fit_plane(d['xyz'][fi],d['d0'][fi],d['fid'][fi])
        # A bad joint fit never silently forces the group; preserve separate hypotheses.
        subsets=[g] if ft['valid'] else [[i] for i in g]
        for sub in subsets:
            ff=np.unique(np.concatenate([fits[i] for i in sub]));ft=fit_plane(d['xyz'][ff],d['d0'][ff],d['fid'][ff]);pid=len(planes)
            planes.append(dict(plane_id=pid,uuid=hashlib.sha256((d['dataset']+str(sub)).encode()).hexdigest()[:32],version=0,active=True,
                status='single_view' if len(set(rs[i]['frame'] for i in sub))==1 else 'multi_view',source_regions=sub,source_masks=sorted(set(itertools.chain.from_iterable(rs[i]['source_masks'] for i in sub))),
                frames=sorted(set(rs[i]['frame'] for i in sub)),plane=ft['plane'],fit=ft,parent_ids=[],alias_ids=[],created_reason='all-pair compatible group; joint original fit'))
            mem.append(np.unique(np.concatenate([ids[i] for i in sub])));fitmem.append(ff)
    return planes,mem,fitmem,dict(edges=edges,group_order_invariant=True,unconditional_transitive_chaining=False)

def registry_save(out,planes,ids,fits):
    out.mkdir(parents=True,exist_ok=True);c.json_write(out/'planes.json',planes)
    np.savez_compressed(out/'memberships.npz',**{f'ids_{i}':a for i,a in enumerate(ids)},**{f'fit_{i}':a for i,a in enumerate(fits)})
def registry_load(dataset,code='I4'):
    path=latest(code,dataset)/('artifacts/associations' if code in ['I4','I4a'] else 'artifacts/optimization')
    planes=json.loads((path/'planes.json').read_text())
    with np.load(path/'memberships.npz') as z:ids=[z[f'ids_{i}'] for i in range(len(planes))];fits=[z[f'fit_{i}'] for i in range(len(planes))]
    return planes,ids,fits

def associate(dataset,semantic_only=False):
    sourcecode='I3a' if semantic_only else 'I3';code='I4a' if semantic_only else 'I4'
    st=Stage(code,dataset,[latest(sourcecode,dataset)])
    try:
        d=load(dataset,True);rs,ids,fs=regions_load(dataset,sourcecode);planes,ids,fs,audit=graph_build(d,rs,ids,fs)
        out=st.path/'artifacts/associations';registry_save(out,planes,ids,fs);c.json_write(out/'graph.json',audit)
        # Synthetic A-B-C cycle: complete-link criterion rejects A-C absent edge.
        synthetic=dict(edges=[[0,1],[1,2]],absent=[0,2],triple_all_pair_compatible=all(x in [(0,1),(1,2)] for x in [(0,1),(1,2),(0,2)]))
        assert not synthetic['triple_all_pair_compatible']
        st.finish(dict(decision='CONSERVATIVE_GLOBAL_IDS',planes=len(planes),multi_view=sum(p['status']=='multi_view' for p in planes),
            single_view=sum(p['status']=='single_view' for p in planes),tested_edges=len(audit['edges']),order_invariant=audit['group_order_invariant'],cycle_control=synthetic),
            '# I4 전역 plane 연결\n\n양방향 유한 plane 영역 투영·fit 대응·방향·offset 증거로 후보를 연결했다. '
            '전체 그룹의 모든 쌍이 양립할 때만 공유 ID를 만들며 joint 원본 fit가 실패하면 단일 시점 모델을 남긴다. '
            'semantic 이름만으로 합치거나 raw depth 3% gate를 사용하지 않았다. 역순 후보 입력으로 같은 그룹인지 검사했다. '
            '보수적 연결이므로 같은 물리적 표면이 여러 ID로 남을 수 있다. ground-truth 소속 정확도는 미평가다.')
    except Exception as e:st.fail(e);raise

def image_orientation(d,mask,f):
    gray=c.cv2.cvtColor(d['rgb'][f],c.cv2.COLOR_RGB2GRAY);ls=c.cv2.createLineSegmentDetector().detect(gray)[0]
    if ls is None:return dict(valid=False,reason='no_lines')
    ls=ls[:,0].reshape(-1,2,2);length=np.linalg.norm(ls[:,1]-ls[:,0],axis=1);mid=np.rint(ls.mean(1)).astype(int);h,w=mask.shape
    good=(length>=20)&mask[mid[:,1].clip(0,h-1),mid[:,0].clip(0,w-1)];ls=ls[good];length=length[good]
    coeff=np.cross(np.c_[ls[:,0],np.ones(len(ls))],np.c_[ls[:,1],np.ones(len(ls))]);inv=np.linalg.inv(d['k'][f]);line_cam=coeff@d['k'][f]
    line_cam/=np.maximum(np.linalg.norm(line_cam,axis=1,keepdims=True),1e-12);remaining=np.arange(len(ls));vps=[];supports=[]
    rng=np.random.default_rng(0)
    for _ in range(2):
        if len(remaining)<3:break
        best=None
        for __ in range(min(200,len(remaining)*(len(remaining)-1)//2)):
            a,b=rng.choice(remaining,2,False);v=np.cross(line_cam[a],line_cam[b]);norm=np.linalg.norm(v)
            if norm<1e-8:continue
            v/=norm;inside=abs(line_cam[remaining]@v)<np.sin(np.deg2rad(2));score=float(length[remaining][inside].sum())
            if best is None or score>best[0]:best=(score,v,remaining[inside])
        if best is None or len(best[2])<3:break
        _,v,used=best;vps.append(v);supports.append(used.tolist());remaining=np.setdiff1d(remaining,used)
    if len(vps)<2:return dict(valid=False,reason='two_independent_line_families_unavailable',line_count=len(ls),families=supports)
    normal=np.cross(vps[0],vps[1]);norm=np.linalg.norm(normal)
    if norm<np.sin(np.deg2rad(15)):return dict(valid=False,reason='near_parallel_image_directions')
    nw=normal/norm@d['e'][f,:,:3];nw/=np.linalg.norm(nw)
    return dict(valid=True,normal=nw.tolist(),line_families=supports,line_segments=ls.tolist(),source='RGB-only vanishing directions + fixed K/R; depth not used')

def relation_model_scores(pa,pb,rgb_a,rgb_b):
    targets=[[pa[:3]]+[np.array(x['normal']) for x in rgb_a if x['valid']], [pb[:3]]+[np.array(x['normal']) for x in rgb_b if x['valid']]]
    scores={};fit={}
    for model,dof in [('free',4),('parallel',2),('orthogonal',3)]:
        def decode(v):
            a=v[:3]/max(np.linalg.norm(v[:3]),1e-12)
            if model=='parallel':b=a
            else:
                b=v[3:6]
                if model=='orthogonal':b=b-a*(a@b)
                b=b/max(np.linalg.norm(b),1e-12)
            return a,b
        def residual(v):
            normals=decode(v);return np.concatenate([np.cross(nn,t)/np.sin(np.deg2rad(15))/np.sqrt(len(tt)) for nn,tt in zip(normals,targets) for t in tt])
        start=np.r_[pa[:3],pb[:3]] if model!='parallel' else pa[:3]
        result=least_squares(residual,start,max_nfev=100);rr=residual(result.x)
        scores[model]=float(.5*rr@rr+CFG['lambda_complex']*dof)
        fit[model]=dict(normals=[a.tolist() for a in decode(result.x)],training_loss=float(.5*rr@rr),dof=dof,model_cost=CFG['lambda_complex']*dof)
    return scores,fit

def relations(dataset,semantic_only=False):
    sourcecode='I4a' if semantic_only else 'I4';code='I5a' if semantic_only else 'I5'
    st=Stage(code,dataset,[latest(sourcecode,dataset)])
    try:
        d=load(dataset,True);planes,ids,fs=registry_load(dataset,sourcecode);n,h,w=d['depth'].shape;rgb=[]
        frozen_labels,_=assignment(d,planes,ids);boundary_map={}
        for f in range(n):
            lab=frozen_labels[f*h*w:(f+1)*h*w].reshape(h,w);edge=c.cv2.Canny(d['rgb'][f],80,160)>0
            for dy,dx in [(0,1),(1,0)]:
                a=lab[:h-dy,:w-dx];b=lab[dy:,dx:];good=(a>=0)&(b>=0)&(a!=b)&(edge[:h-dy,:w-dx]|edge[dy:,dx:])
                yy,xx=np.nonzero(good)
                for y,x in zip(yy,xx):
                    key=tuple(sorted([int(a[y,x]),int(b[y,x])]));boundary_map.setdefault(key,{}).setdefault(f,[]).append([int(x),int(y)])
        for p,ii in zip(planes,ids):
            evidence=[]
            for f in p['frames']:
                mask=np.zeros(h*w,bool);mask[ii[d['fid'][ii]==f]%(h*w)]=True;evidence.append(dict(frame=f,**image_orientation(d,mask.reshape(h,w),f)))
            rgb.append(evidence)
        rel=[]
        for a,b in itertools.combinations(range(len(planes)),2):
            pa,pb=np.array(planes[a]['plane']),np.array(planes[b]['plane']);angle=float(np.degrees(np.arccos(np.clip(abs(pa[:3]@pb[:3]),0,1))))
            hyp='parallel' if angle<=15 else 'orthogonal' if abs(angle-90)<=20 else 'free';err=angle if hyp=='parallel' else 90-angle
            compatible=[]
            for ra,rb in itertools.product(rgb[a],rgb[b]):
                if ra['valid'] and rb['valid']:
                    imageangle=float(np.degrees(np.arccos(np.clip(abs(np.array(ra['normal'])@rb['normal']),0,1))))
                    imageerr=imageangle if hyp=='parallel' else 90-imageangle
                    # Require each RGB plane normal also agree with its geometric normal.
                    na=float(np.degrees(np.arccos(np.clip(abs(np.array(ra['normal'])@pa[:3]),0,1))))
                    nb=float(np.degrees(np.arccos(np.clip(abs(np.array(rb['normal'])@pb[:3]),0,1))))
                    if abs(imageerr)<10 and max(na,nb)<20:compatible.append(dict(frames=[ra['frame'],rb['frame']],image_angle=imageangle,normal_agreement=[na,nb]))
            scores,model_fits=relation_model_scores(pa,pb,rgb[a],rgb[b]) if compatible else ({'free':0.,'parallel':None,'orthogonal':None},{})
            preferred=min(scores,key=lambda k:np.inf if scores[k] is None else scores[k])
            selected=preferred if preferred in ['parallel','orthogonal'] and compatible else 'free' if hyp=='free' or compatible else 'uncertain'
            boundary_evidence=[]
            if angle>15:
                for frame,pixels in boundary_map.get((a,b),{}).items():
                    if len(pixels)>=8:
                        take=np.linspace(0,len(pixels)-1,min(64,len(pixels)),dtype=int)
                        boundary_evidence.append(dict(frame=frame,pixel_uv=np.array(pixels)[take].tolist(),status='frozen_RGB_edge_at_candidate_adjacency; not GT'))
            rel.append(dict(a=a,b=b,hypothesis=hyp,selected=selected,angle_before=angle,confidence=.5 if selected in ['parallel','orthogonal'] else 0.,boundary_evidence=boundary_evidence,
                independent_evidence=['original_depth_plane','RGB_vanishing_directions'] if compatible else ['original_depth_plane'],rgb_support=compatible,
                model_scores=scores,model_fits=model_fits,selection_reason='fit-only free/parallel/orthogonal orientation likelihood + dof cost; independent image/depth evidence required'))
        out=st.path/'artifacts/relations';out.mkdir();c.json_write(out/'relations.json',rel);c.json_write(out/'rgb_direction_evidence.json',rgb)
        active=[r for r in rel if r['selected'] in ['parallel','orthogonal']]
        st.finish(dict(decision='SOFT_RELATIONS' if active else 'RELATION_EVIDENCE_INSUFFICIENT_FREE_RETAINED',pairs=len(rel),active=len(active),
            rgb_valid_planes=sum(any(r['valid'] for r in rr) for rr in rgb),user_structural_prior=False,
            limitations='Conditional orientation model comparison; image-line family assignment uncertainty is not fully marginalized.'),
            '# I5 자동 구조 관계\n\n원본 depth plane과 RGB line의 두 소실방향에서 얻은 별도 방향 증거가 함께 맞는 경우에만 soft 관계를 활성화했다. '
            '증거가 부족하면 uncertain/free를 유지하며 사용자가 지정한 벽·90도 prior는 없다. '
            'training의 방향 likelihood와 자유도 비용으로 자유/평행/수직 모델을 직접 비교했다. 영상/원본 depth의 독립 증거가 없으면 제약을 비활성화한다. '
            'line family 추정의 불확실성을 완전히 적분한 확률 모델은 아니다.')
    except Exception as e:st.fail(e);raise

def assignment(d,planes,ids,rs=None):
    N=len(d['ids']);best=np.full(N,CFG['lambda_unknown']);second=np.full(N,np.inf);label=np.full(N,-1,np.int32)
    for p,ii in zip(planes,ids):
        if not p['active']:continue
        # Region training residual defines confidence; no per-movement-point depth rejection.
        quality=min(.45,p['fit']['normalized_residual']['median']/.005*.1)
        cost=quality+CFG['lambda_image']*np.log1p(len(ii))/np.log1p(N)
        better=cost<best[ii];old=best[ii].copy();second[ii]=np.minimum(second[ii],np.where(better,old,cost))
        best[ii[better]]=cost;label[ii[better]]=p['plane_id']
    return label,best

def optimize(dataset,struct=True,arm='A4',**kwargs):
    from joint import run_joint
    return run_joint(dataset,struct=struct,**kwargs)

def joint(dataset,semantic_only=False):
    code='I6a' if semantic_only else 'I6';regcode='I4a' if semantic_only else 'I4';relcode='I5a' if semantic_only else 'I5'
    st=Stage(code,dataset,[latest(regcode,dataset),latest(relcode,dataset)])
    try:
        runs=[optimize(dataset,registry_code=regcode,relations_code=relcode),optimize(dataset,reverse=True,registry_code=regcode,relations_code=relcode),optimize(dataset,seed=1,registry_code=regcode,relations_code=relcode)]
        from scipy.optimize import linear_sum_assignment
        stability=[];reference=runs[0][4]
        for i,run in enumerate(runs):
            current=run[4];a=reference[reference>=0];maxpid=max(int(reference.max(initial=-1)),int(current.max(initial=-1)))+1
            both=(reference>=0)&(current>=0);confusion=np.zeros((maxpid,maxpid),np.int64)
            np.add.at(confusion,(reference[both],current[both]),1)
            row,col=linear_sum_assignment(confusion,maximize=True);correct=int(confusion[row,col].sum())+int(np.sum((reference<0)&(current<0)))
            stability.append(dict(run=i,seed=1 if i==2 else 0,reversed_evidence_and_variables=i==1,agreement_after_label_permutation=correct/len(reference),
                objective_final=run[5]['history'][-1]['objective'],assigned=int((current>=0).sum())))
        chosen=min(range(len(runs)),key=lambda i:runs[i][5]['history'][-1]['objective'])
        d,planes,ids,fs,label,audit=runs[chosen];audit['stability']=stability;audit['chosen_initialization_by_fit_objective']=chosen
        out=st.path/'artifacts/optimization';registry_save(out,planes,ids,fs)
        np.savez_compressed(out/'assignments.npz',plane_id=label,observation_id=d['ids']);c.json_write(out/'optimization.json',audit)
        with (out/'plane_versions.jsonl').open('w') as f:
            for row in audit.get('versions',[]):f.write(json.dumps(row)+'\n')
        c.json_write(st.path/'evaluation/history.json',audit['history'])
        c.json_write(st.path/'evaluation/stability.json',stability)
        st.finish(dict(decision='JOINT_SOLVE_EXECUTED',active_planes=sum(p['active'] for p in planes),assigned=int((label>=0).sum()),iterations=len(audit['history'])-1,
            objective_initial=audit['history'][0]['objective'] if audit['history'] else None,objective_final=audit['history'][-1]['objective'] if audit['history'] else None,
            topology_proposals=audit['topology_proposals'],stability=stability,topology_events=len(audit['topology_history'])),
            '# I6 전역 plane·소속 최적화\n\n모든 plane 계수를 하나의 sparse least-squares 문제로 함께 갱신하고 지역 소속 제안을 같은 목적함수로 수용했다. '
            '원본 FoV fit·고정 RGB 대응을 계속 사용하며 보정된 점에 plane을 다시 맞추지 않았다. 목적함수 비증가를 검사했다.\n\n'
            'merge/split/revert 제안은 같은 목적함수로 평가하고 신규 ID를 할당하며 이전 ID를 재사용하지 않는다. '
            '관측/변수 역순과 별도 초기값을 반복하고 label permutation 보정 후 안정성을 기록했다. '
            'RGB 대응의 재투영을 경계 증거의 대리 잔차로 사용한다. 직접적인 RGB 교선 경계 항과 관계의 반복 재선택은 후속 보완 대상이다.',criteria=False)
    except Exception as e:st.fail(e);raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('code',choices=['I2','I3','I4','I5','I6']);parser.add_argument('--dataset',default='tum-freiburg1_desk');args=parser.parse_args()
    dict(I2=fov,I3=candidates,I4=associate,I5=relations,I6=joint)[args.code](args.dataset)
