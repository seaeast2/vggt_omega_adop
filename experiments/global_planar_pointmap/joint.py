"""Vectorized joint evidence energy; monotone discrete and continuous proposals."""
from core import *
from scipy import sparse

def run_joint(dataset,struct=True,seed=0,reverse=False,grounded_only=False,continuous=True,update_labels=True,topology=True,registry_code='I4',relations_code='I5',logger=None,checkpoint_dir=None):
    import solve
    d=load(dataset,True);planes,ids,fits=solve.registry_load(dataset,registry_code);initial=json.loads(json.dumps(planes));N=len(d['ids']);n,h,w=d['depth'].shape
    if grounded_only:
        records,_=solve.tags_load(dataset);grounded={r['mask_id'] for r in records if r['source']=='grounded'}
        # A6 must rerun I3/I4 on a source subset; this flag is only a local safeguard.
        for p in planes:
            if not grounded.intersection(p['source_masks']):p['active']=False
    rel=json.loads((latest(relations_code,dataset)/'artifacts/relations/relations.json').read_text())
    relation_updates=[]
    label,_=solve.assignment(d,planes,ids)
    matches=m.load(split_path(dataset)/'matches.npz');mt=m.subset(matches,~matches['validation'])
    ua=np.rint(mt['uv_i']).astype(int);ub=np.rint(mt['uv_j']).astype(int);ia=mt['pair'][:,0]*h*w+ua[:,1]*w+ua[:,0];ib=mt['pair'][:,1]*h*w+ub[:,1]*w+ub[:,0]
    base_p=np.array([p['plane'] for p in planes]);versions=[dict(version=0,state='initial',planes=initial)];topology_history=[];history=[]
    rng=np.random.default_rng(seed)
    if seed:
        # Small deterministic normal/offset perturbation, selected by fit objective only.
        p=base_p+rng.normal(0,1e-4,base_p.shape);p[:,:3]/=np.linalg.norm(p[:,:3],axis=1,keepdims=True)
        for k,plane in enumerate(planes):plane['plane']=orient(p[k]).tolist()

    def make_context():
        ss=[];sp=[];sw=[]
        for k,ff in enumerate(fits):
            frames=np.unique(d['fid'][ff])
            for f in frames:
                a=ff[d['fid'][ff]==f];a=a[np.linspace(0,len(a)-1,min(96,len(a)),dtype=int)]
                ss.extend(a.tolist());sp.extend([k]*len(a));sw.extend([1/(len(frames)*len(a))]*len(a))
        return np.array(ss,int),np.array(sp,int),np.array(sw,float)
    ss,sp,sw=make_context()
    if reverse:
        ss,sp,sw=ss[::-1],sp[::-1],sw[::-1];ia,ib=ia[::-1],ib[::-1]
    def coeff():return np.array([p['plane'] for p in planes])
    def encode(ps):return np.c_[np.arctan2(ps[:,1],ps[:,0]),np.arcsin(np.clip(ps[:,2],-1,1)),ps[:,3]].ravel()
    def decode(v):
        v=v.reshape(-1,3);az,el,off=v.T;return np.c_[np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el),off]
    def corrected_points(obs,lab,ps):
        a=lab[obs];x=d['xyz'][obs].copy();good=a>=0
        if good.any():
            ii=obs[good];p=ps[a[good]];den=np.einsum('ij,ij->i',d['q'][ii],p[:,:3]);num=-np.einsum('ij,ij->i',d['center_points'][ii],p[:,:3])-p[:,3]
            z=np.divide(num,den,out=np.full(len(ii),np.nan),where=abs(den)>1e-12);ok=np.isfinite(z)&(z>0)
            x[np.flatnonzero(good)[ok]]=d['center_points'][ii[ok]]+z[ok,None]*d['q'][ii[ok]]
        return x
    def residual(ps,lab,pattern=False):
        blocks=[];deps=[];active_ids=np.unique(lab[lab>=0]);P=max(1,len(active_ids))
        # Only original fit observations belonging to the current model contribute.
        good=lab[ss]==sp;pp=ps[sp];r=(np.einsum('ij,ij->i',d['xyz'][ss],pp[:,:3])+pp[:,3])/d['d0'][ss]/.005
        blocks.append(robust_residual(r)*np.sqrt(sw*CFG['lambda_raw']/P)*good);deps.extend([[int(k)] for k in sp])
        # Fixed direction priors from ORIGINAL regions, never the newly projected cloud.
        if len(active_ids):
            prior=np.array([planes[k].get('direction_prior',initial[k]['plane'][:3] if k<len(initial) else planes[k]['plane'][:3]) for k in active_ids])
            nr=np.cross(ps[active_ids,:3],prior)/np.sin(np.deg2rad(15));blocks.append(nr.ravel()*np.sqrt(CFG['lambda_normal']/P))
            deps.extend([[int(k)] for k in active_ids for _ in range(3)])
        if len(ia):
            xl=corrected_points(ia,lab,ps);xr=corrected_points(ib,lab,ps);scale=(d['d0'][ia]+d['d0'][ib])/2
            cr=(xl-xr)/scale[:,None]/.005;blocks.append(robust_residual(cr).ravel()*np.sqrt(CFG['lambda_cross']/len(ia)))
            pairdeps=[sorted(set(int(x) for x in [a,b] if x>=0)) for a,b in zip(lab[ia],lab[ib])];deps.extend([dep for dep in pairdeps for _ in range(3)])
            pixel=np.zeros((len(ia),2))
            for f in range(n):
                select=d['fid'][ib]==f;uv,z,_=c.project(xl[select],d['k'][f],d['e'][f],h,w);r=(uv-d['uv'][ib[select]])/2
                r[~np.isfinite(r).all(1)|(z<=0)]=100.;pixel[select]=r
            blocks.append(robust_residual(pixel).ravel()*np.sqrt(CFG['lambda_edge']/len(ia)));deps.extend([dep for dep in pairdeps for _ in range(2)])
        relations_active=[r for r in rel if struct and r['selected'] in ['parallel','orthogonal'] and r['a'] in active_ids and r['b'] in active_ids]
        for relation in relations_active:
            a,b=relation['a'],relation['b'];rr=np.cross(ps[a,:3],ps[b,:3]) if relation['selected']=='parallel' else np.array([ps[a,:3]@ps[b,:3]])
            blocks.append(rr/np.sin(np.deg2rad(15))*np.sqrt(CFG['lambda_struct']*relation['confidence']/max(1,len(relations_active))));deps.extend([[a,b]]*len(rr))
        # Fixed RGB edge observations constrain the projected intersection of two planes.
        edge_rel=[r for r in rel if r.get('boundary_evidence') and r['a'] in active_ids and r['b'] in active_ids]
        for relation in edge_rel:
            a,b=relation['a'],relation['b'];pa,pb=ps[a],ps[b];direction=np.cross(pa[:3],pb[:3]);norm=np.linalg.norm(direction)
            if norm<1e-8:direction=np.array([1.,0.,0.])
            else:direction/=norm
            point=np.linalg.lstsq(np.vstack([pa[:3],pb[:3],direction]),[-pa[3],-pb[3],0.],rcond=None)[0]
            for evidence in relation['boundary_evidence']:
                f=evidence['frame'];R,t=d['e'][f,:,:3],d['e'][f,:,3];line=np.cross(d['k'][f]@(R@point+t),d['k'][f]@(R@direction));line/=max(np.linalg.norm(line[:2]),1e-12)
                uv=np.array(evidence['pixel_uv']);er=(np.c_[uv,np.ones(len(uv))]@line)/2
                blocks.append(robust_residual(er)*np.sqrt(CFG['lambda_edge']/(max(1,len(edge_rel))*len(uv)*len(relation['boundary_evidence']))));deps.extend([[a,b]]*len(uv))
        r=np.concatenate(blocks) if blocks else np.zeros(0)
        if pattern:
            matrix=sparse.lil_matrix((len(r),len(ps)*3),dtype=np.int8)
            for row,ppp in enumerate(deps):
                for k in ppp:matrix[row,3*k:3*k+3]=1
            return r,matrix.tocsr()
        return r
    def terms(ps,lab):
        rr=residual(ps,lab);counts=np.bincount(lab[lab>=0],minlength=len(ps));active=counts>0
        # Complexity normalized by supported area; small planes can remain identifiable.
        complexity=CFG['lambda_complex']*float(np.sqrt(counts[active]/N).sum())
        image=0.
        for k in np.flatnonzero(active):
            # Image containment and mask-boundary cost are independent of raw XYZ.
            image+=CFG['lambda_image']*counts[k]/N*np.log1p(len(ids[k]))/np.log1p(N)
        supported=[r for r in rel if struct and r['rgb_support'] and all(r['model_scores'].get(k) is not None for k in ['free','parallel','orthogonal'])]
        relation_prior=float(np.mean([r['model_scores'][r['selected'] if r['selected'] in ['parallel','orthogonal'] else 'free'] for r in supported]))*CFG['lambda_struct'] if supported else 0.
        return dict(evidence=float(.5*rr@rr),image=float(image),unknown=float(CFG['lambda_unknown']*np.mean(lab<0)),complexity=complexity,relation_prior=relation_prior)
    validity_cache={}
    def invalid_active(lab):
        invalid=[];sample_counts=np.bincount(sp[lab[ss]==sp],minlength=len(fits))
        for k in np.unique(lab[lab>=0]):
            fi=fits[k];selected=lab[fi]==k;key=(int(k),ahash(selected))
            if key not in validity_cache:
                use=fi[selected];valid=len(use)>=CFG['minimum_fit']
                if valid:
                    _,ev,_=svd_plane(d['xyz'][use],np.ones(len(use)))
                    valid=ev[1]/max(ev[2],1e-30)>=1e-4 and 4*np.sqrt(max(0,ev[1]))/np.median(d['d0'][use])>=.01
                valid=valid and int(sample_counts[k])>=3
                validity_cache[key]=bool(valid)
            if not validity_cache[key]:invalid.append(int(k))
        return invalid
    def objective(ps,lab):
        invalid=invalid_active(lab)
        return 1e8+len(invalid) if invalid else sum(terms(ps,lab).values())
    def candidate_score(ps,lab,k,ii):
        trial=lab.copy();trial[ii]=k
        return objective(ps,trial),trial
    initial_invalid=invalid_active(label)
    for k in initial_invalid:label[label==k]=-1;planes[k]['unknown_reason']='INSUFFICIENT_EFFECTIVE_ASSIGNED_FIT_SUPPORT'
    ps=coeff();old=objective(ps,label);history.append(dict(iteration=0,objective=old,terms=terms(ps,label),assignment_changes=0,initial_unobservable_planes=initial_invalid))
    def checkpoint(iteration,ps,label):
        if checkpoint_dir is None:return None
        out=Path(checkpoint_dir);out.mkdir(parents=True,exist_ok=True);file=out/f'version_{iteration:02d}.npz'
        np.savez_compressed(file,plane_id=label,coefficients=ps,observation_id=d['ids'])
        return c.record(file)
    versions[0]['checkpoint']=checkpoint(0,ps,label)
    patience=0
    for iteration in range(1,21):
        start=old;old_label=label.copy();continuous_info=dict(attempted=False)
        if continuous and len(ps) and len(np.unique(label[label>=0])):
            value,pattern=residual(ps,label,True);v=encode(ps);activecols=np.flatnonzero(np.asarray(pattern.sum(0)).ravel()>0)
            if reverse:activecols=activecols[::-1]
            if len(activecols):
                def unpack(x):
                    vv=v.copy();vv[activecols]=x;return decode(vv)
                result=least_squares(lambda x:residual(unpack(x),label),v[activecols],jac_sparsity=pattern[:,activecols],max_nfev=200,ftol=1e-7,xtol=1e-7,gtol=1e-7)
                candidate=unpack(result.x);value=objective(candidate,label);accept=value<old
                if accept:ps=candidate;old=value
                continuous_info=dict(attempted=True,nfev=int(result.nfev),converged=bool(result.success),accepted=accept)
        if update_labels:
            # Canonical order after optional input reversal; exact fixed energy acceptance.
            order=list(range(len(planes)))
            if reverse:order.reverse()
            order=sorted(order,key=lambda k:(planes[k]['uuid'],k))
            for k in order:
                if planes[k]['status'] in ['merged','split','rejected']:continue
                ii=ids[k];value,trial=candidate_score(ps,label,k,ii)
                if value<old-1e-10:label=trial;old=value
                # Unknown is a genuine alternative, evaluated on the same total energy.
                ii=np.flatnonzero(label==k)
                if len(ii):
                    trial=label.copy();trial[ii]=-1;value=objective(ps,trial)
                    if value<old-1e-10:label=trial;old=value
        if struct:
            for relation in rel:
                if not relation['rgb_support'] or not all(relation['model_scores'].get(k) is not None for k in ['free','parallel','orthogonal']):continue
                for hypothesis in ['free','parallel','orthogonal']:
                    previous=relation['selected'];relation['selected']=hypothesis;relation['confidence']=.5 if hypothesis!='free' else 0.
                    value=objective(ps,label);accept=value<old-1e-10
                    relation_updates.append(dict(iteration=iteration,a=relation['a'],b=relation['b'],from_hypothesis=previous,proposed=hypothesis,accepted=accept,objective=value))
                    if accept:old=value
                    else:relation['selected']=previous;relation['confidence']=.5 if previous in ['parallel','orthogonal'] else 0.
        if topology:
            # Merge proposals need pairwise compatible original geometry and shared footprint.
            active_ids=np.unique(label[label>=0]);merge_proposals=[]
            for a,b in itertools.combinations(active_ids,2):
                pa,pb=ps[a],ps[b];angle=np.degrees(np.arccos(np.clip(abs(pa[:3]@pb[:3]),0,1)))
                if angle>10:continue
                ca=np.array(planes[a]['fit']['centroid']);cb=np.array(planes[b]['fit']['centroid']);scale=(planes[a]['fit']['reference_depth']+planes[b]['fit']['reference_depth'])/2
                if max(abs(ca@pb[:3]+pb[3]),abs(cb@pa[:3]+pa[3]))/scale>.01:continue
                # Shared observation candidates prevent merging parallel disjoint physical faces.
                shared=np.intersect1d(ids[a],ids[b],assume_unique=True)
                if len(shared)<.2*min(len(ids[a]),len(ids[b])):continue
                merge_proposals.append((int(a),int(b)))
            for a,b in merge_proposals:
                if not np.any(label==a) or not np.any(label==b):continue
                fi=np.union1d(fits[a],fits[b]);ft=fit_plane(d['xyz'][fi],d['d0'][fi],d['fid'][fi])
                if not ft['valid']:continue
                k=len(planes);combined=np.union1d(ids[a],ids[b]);pnew=dict(planes[a]);pnew|=dict(plane_id=k,uuid=hashlib.sha256(f'{dataset}:{a}:{b}:{k}'.encode()).hexdigest()[:32],
                    parent_ids=[a,b],alias_ids=[],source_regions=sorted(set(planes[a]['source_regions']+planes[b]['source_regions'])),source_masks=sorted(set(planes[a]['source_masks']+planes[b]['source_masks'])),
                    frames=sorted(set(planes[a]['frames']+planes[b]['frames'])),plane=ft['plane'],fit=ft,created_reason='objective-approved merge',direction_prior=np.array(ft['plane'])[:3].tolist())
                planes.append(pnew);ids.append(combined);fits.append(fi);ss,sp,sw=make_context();trialps=np.vstack([ps,ft['plane']]);trial=label.copy();trial[(label==a)|(label==b)]=k
                val=objective(trialps,trial);accepted=val<old-1e-10
                topology_history.append(dict(iteration=iteration,type='merge',parents=[a,b],new_id=k,objective_before=old,objective_proposed=val,accepted=accepted))
                if accepted:
                    ps=trialps;label=trial;old=val
                    for parent in [a,b]:planes[parent]['status']='merged';planes[parent]['successor_ids']=[k];planes[parent]['active']=False
                else:
                    # Rejected IDs still remain in lineage; never reuse an allocated ID.
                    ps=trialps;planes[k]['status']='rejected';planes[k]['active']=False
                    ids[k]=np.array([],np.int64);fits[k]=np.array([],np.int64);ss,sp,sw=make_context()
            # Split source-region groups; original regional planes stay available as alternatives.
            for k in list(np.unique(label[label>=0])):
                source=planes[k]['source_regions']
                if len(source)<2:continue
                # Reassignment to existing source alternatives is a split proposal; no ID reuse.
                children=[j for j,p in enumerate(planes) if j!=k and p['source_regions'] and set(p['source_regions'])<set(source) and len(ids[j]) and p['status'] not in ['merged','split','rejected']]
                if not children:continue
                trial=label.copy();assigned=label==k;newchildren=[];trialps=ps.copy()
                for j in sorted(children,key=lambda j:len(planes[j]['source_regions'])):
                    childid=len(planes);child=dict(planes[j]);child|=dict(plane_id=childid,uuid=hashlib.sha256(f'{dataset}:split:{k}:{j}:{childid}'.encode()).hexdigest()[:32],parent_ids=[int(k),j],created_reason='split/revert hypothesis')
                    planes.append(child);ids.append(ids[j].copy());fits.append(fits[j].copy());trialps=np.vstack([trialps,ps[j]]);newchildren.append(childid)
                    ii=ids[j];sel=assigned[ii];trial[ii[sel]]=childid
                ss,sp,sw=make_context();value=objective(trialps,trial);accept=value<old-1e-10
                topology_history.append(dict(iteration=iteration,type='split_revert',parent=int(k),children=newchildren,objective_before=old,objective_proposed=value,accepted=accept))
                ps=trialps
                if accept:label=trial;old=value;planes[k]['status']='split';planes[k]['successor_ids']=newchildren
                else:
                    for j in newchildren:planes[j]['status']='rejected';planes[j]['active']=False;ids[j]=np.array([],np.int64);fits[j]=np.array([],np.int64)
                    ss,sp,sw=make_context()
        delta=float(np.mean(label!=old_label));rel_decrease=(start-old)/max(abs(start),1e-12)
        history.append(dict(iteration=iteration,objective=old,terms=terms(ps,label),assignment_changes=delta,continuous=continuous_info))
        versions.append(dict(version=iteration,state='proposed',coefficients=ps.tolist(),assignment_hash=ahash(label),allocated_ids=list(range(len(planes))),checkpoint=checkpoint(iteration,ps,label)))
        event=dict(dataset=dataset,iteration=iteration,objective=old,active_planes=len(np.unique(label[label>=0])),change=delta)
        if logger:logger('joint_iteration',**event)
        else:print(json.dumps(dict(event='joint_iteration',**event)),flush=True)
        if rel_decrease<1e-5 and delta<.001:patience+=1
        else:patience=0
        if patience>=3:break
    assert all(b['objective']<=a['objective']+1e-8 for a,b in zip(history,history[1:]))
    for k,p in enumerate(planes):
        p['plane']=orient(ps[k]).tolist();p['version']=len(history)-1;p['active']=bool(np.any(label==k));p['status']=p['status'] if p['active'] or p['status'] in ['merged','split','rejected'] else 'inactive'
        centers=d['centers'][p['frames']];baseline=max((np.linalg.norm(a-b) for a,b in itertools.combinations(centers,2)),default=0.)/p['fit']['reference_depth']
        p['position_observability']=dict(relative_baseline=float(baseline),status='LOW_PARALLAX_RAW_ANCHORED' if baseline<.01 else 'MULTIVIEW_POSITION_NOT_GT_VALIDATED',independent_position_accuracy_established=False)
    assert [p['plane_id'] for p in planes]==list(range(len(planes)))
    assert len({p['uuid'] for p in planes})==len(planes)
    return d,planes,ids,fits,label,dict(history=history,versions=versions,initial=initial,relations=rel,topology_history=topology_history,relation_updates=relation_updates,
        struct_enabled=struct,objective_formula='sum robust original-fit/normal/cross3D/fixed-RGB-correspondence reprojection + image membership + unknown + area-normalized complexity',
        topology_proposals='merge/split/revert evaluated against same objective; allocated IDs never reused',effective_fit_support_feasibility=True,
        limitations='RGB correspondence reprojection is edge evidence surrogate; no direct photometric residual. Local optimum only.')
