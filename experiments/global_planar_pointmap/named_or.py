"""I10: surface-associated semantic OR; exact wall/table/screen only; no joint solve."""
from core import *
import solve
import export as ex
from visualize_unknown import contact

ALLOWED={'wall','table','screen'}

def cluster_regions(regions,edges,reverse=False):
    valid=[r['region_id'] for r in regions if r['semantic_tag']=='unknown' or r['semantic_tag'] in ALLOWED]
    byid={r['region_id']:r for r in regions};compatible={};used_edges=[]
    for e in edges:
        a,b=e['a'],e['b']
        if a not in valid or b not in valid or not e['passed']:continue
        ta,tb=byid[a]['semantic_tag'],byid[b]['semantic_tag']
        if ta!='unknown' and tb!='unknown' and ta!=tb:continue
        # Independent fit RGB correspondence is required for cross-view propagation.
        if byid[a]['frame']!=byid[b]['frame'] and e.get('fit_tracks',0)<2:continue
        compatible[tuple(sorted([a,b]))]=True;used_edges.append(e)
    groups=[[i] for i in (reversed(valid) if reverse else valid)]
    def tags(g):return {byid[i]['semantic_tag'] for i in g if byid[i]['semantic_tag']!='unknown'}
    while True:
        proposals=[]
        for a,b in itertools.combinations(range(len(groups)),2):
            ga,gb=groups[a],groups[b];ta,tb=tags(ga),tags(gb)
            if len(ta|tb)>1:continue
            if not all(compatible.get(tuple(sorted([i,j])),False) for i,j in itertools.product(ga,gb)):continue
            priority=0 if ta and tb else 1 if ta or tb else 2
            merged=tuple(sorted(ga+gb));proposals.append((priority,-len(merged),merged,a,b))
        if not proposals:break
        _,_,merged,a,b=min(proposals);groups=[g for k,g in enumerate(groups) if k not in [a,b]]+[list(merged)]
    return sorted([sorted(g) for g in groups]),used_edges

def synth_controls():
    r=[dict(region_id=0,frame=0,semantic_tag='wall'),dict(region_id=1,frame=1,semantic_tag='unknown'),
       dict(region_id=2,frame=2,semantic_tag='unknown'),dict(region_id=3,frame=2,semantic_tag='screen')]
    edge=lambda a,b,k:dict(a=a,b=b,passed=True,fit_tracks=k)
    groups,_=cluster_regions(r,[edge(0,1,3),edge(1,2,3),edge(0,3,4)])
    assert [0,1] in groups and [2] in groups and [3] in groups
    no,_=cluster_regions(r,[edge(0,1,0)]);assert all(len(g)==1 for g in no)
    assert cluster_regions(r,[edge(0,1,3)])[0]==cluster_regions(r,[edge(0,1,3)],True)[0]
    return dict(named_unknown_OR=True,all_unknown_stays_unknown=True,no_transitive_bridge=True,no_class_conflict_merge=True,no_RGB_support_no_cross_view_transfer=True,order_invariant=True)

def save_map(out,d,xyz,label,planes,state,source_records):
    out.mkdir(parents=True);ps=json.loads(json.dumps(planes));digest=ahash(xyz)+':'+ahash(label)
    for p in ps:
        p['active']=bool(np.any(label==p['plane_id']));p['state']=state;p['assigned_count']=int(np.sum(label==p['plane_id']))
    c.json_write(out/'planes.json',dict(schema_version='I10.1',state=state,state_hash=digest,planes=ps))
    np.savez_compressed(out/'pointmap.npz',xyz=xyz,xyz_initial=d['xyz'],rgb=d['raw_rgb'],observation_id=d['ids'],frame_id=d['fid'],pixel_uv=d['uv'],intrinsics=d['k'],extrinsics=d['e'],plane_id=label,state_hash=np.array(digest),state=np.array(state))
    for name,col in [('pixel_rgb',d['raw_rgb']),('frame_colors',c.PALETTE[d['fid']])]:ply_write(out/f'{name}.ply',d,xyz,label,col)
    c.json_write(out/'plane_boundaries.json',ex.contours(d,xyz,label,ps))
    c.json_write(out/'manifest.json',dict(state=state,state_hash=digest,inputs=source_records,files=[c.record(p) for p in sorted(out.iterdir()) if p.is_file()]))
    with np.load(out/'pointmap.npz') as z:
        for key,value in [('rgb','raw_rgb'),('observation_id','ids'),('frame_id','fid'),('pixel_uv','uv'),('intrinsics','k'),('extrinsics','e')]:assert ahash(z[key])==ahash(d[value]),key
        assert str(z['state_hash'])==digest

def run(dataset):
    parents=[latest(k,dataset) for k in ['I1','I2','I3','I4']]
    st=Stage('I10',dataset,parents,dict(allowed_semantic_tags=sorted(ALLOWED),mixed_tags='defer',
        semantic_OR='same-surface all-pair-compatible graph; cross-view edges require >=2 frozen FIT RGB tracks',
        structure_priors=False,joint_optimization=False,box_cylinder_sphere=False,unknown_policy='no supported named observation -> unchanged XYZ'))
    try:
        controls=synth_controls();d=load(dataset,True);rs,ids,fits=solve.regions_load(dataset);records,masks=solve.tags_load(dataset)
        n,h,w=d['depth'].shape;N=len(d['ids']);sp=split_load(dataset)
        # Verify the cached graph belongs to exactly the candidate version being used.
        gm=json.loads((latest('I4',dataset)/'manifest.json').read_text());assert any(x['sha256']==c.record(latest('I3',dataset)/'manifest.json')['sha256'] for x in gm['parents'])
        graph=json.loads((latest('I4',dataset)/'artifacts/associations/graph.json').read_text())
        groups,edges=cluster_regions(rs,graph['edges']);assert groups==cluster_regions(rs,graph['edges'],True)[0]
        st.log('surface_groups',regions=len(rs),groups=len(groups),association_edges=len(edges))
        direct={tag:np.zeros(N,bool) for tag in ALLOWED};other=np.zeros(N,bool)
        for record in records:
            if record['source']!='grounded':continue
            obs=np.flatnonzero(masks[record['mask_id']])+record['frame']*h*w
            if record['semantic_tag'] in ALLOWED:direct[record['semantic_tag']][obs]=True
            else:other[obs]=True
        direct_any=np.logical_or.reduce(list(direct.values()));blocked=other&~direct_any
        local_planes=[];or_planes=[];local_members=[];or_members=[];local_fits=[];or_fits=[];history=[]
        eligible=np.zeros(N,bool);named_support=np.zeros(N,bool)
        for g in groups:
            tags={rs[i]['semantic_tag'] for i in g if rs[i]['semantic_tag'] in ALLOWED}
            tag=next(iter(tags)) if len(tags)==1 else None
            if tag is None:
                history.append(dict(regions=g,status='ALL_UNKNOWN',or_named=False));continue
            anchors=[i for i in g if rs[i]['semantic_tag']==tag];anchor_frames=sorted({rs[i]['frame'] for i in anchors})
            members=np.unique(np.concatenate([ids[i] for i in g]));named_support[members]=True
            # Nonlocal pixels need a named observation in ANOTHER view; no same-UV OR.
            permitted=direct[tag][members]|np.array([any(a!=int(f) for a in anchor_frames) for f in d['fid'][members]])
            members=members[permitted&~blocked[members]];eligible[members]=True
            local=np.unique(np.concatenate([ids[i] for i in anchors]));local=local[direct[tag][local]&~blocked[local]]
            pid=len(or_planes);row=dict(plane_id=pid,uuid=hashlib.sha256((st.run_id+str(g)).encode()).hexdigest()[:32],semantic_tag=tag,source_regions=g,
                source_masks=sorted(set(itertools.chain.from_iterable(rs[i]['source_masks'] for i in g))),named_anchor_regions=anchors,named_anchor_frames=anchor_frames,
                frames=sorted(set(d['fid'][members].tolist())),parent_ids=[],alias_ids=[],coordinate_frame='Omega world/model units',version=0)
            for mode,member,source_fit,pp,mm,ff in [('local',local,np.unique(np.concatenate([fits[i] for i in anchors])),local_planes,local_members,local_fits),
                    ('OR',members,np.unique(np.concatenate([fits[i] for i in g])),or_planes,or_members,or_fits)]:
                use=source_fit[np.isin(source_fit,member)];assert not sp['excluded'][use].any()
                ft=fit_plane(d['xyz'][use],d['d0'][use],d['fid'][use]);record=dict(row,active=ft['valid'],fit=ft,mode=mode,
                    plane=ft.get('plane',rs[anchors[0]]['fit']['plane']))
                pp.append(record);mm.append(member if ft['valid'] else np.array([],np.int64));ff.append(use)
            history.append(dict(regions=g,status='NAMED_OR',semantic_tag=tag,or_named=True,named_anchors=anchors,anchor_frames=anchor_frames,or_fit_valid=or_planes[-1]['active'],candidate_observations=len(members)))
        source_records=[c.record(p/'manifest.json') for p in parents]
        out=st.path/'artifacts/named_or';out.mkdir();c.json_write(out/'association.json',dict(groups=history,edges=edges,controls=controls))
        np.savez_compressed(out/'semantic_OR.npz',direct_named=direct_any,or_supported=named_support,eligible=eligible,blocked_other_named=blocked,observation_id=d['ids'])
        summaries={};states={}
        for name,pp,mm,ff in [('named_local',local_planes,local_members,local_fits),('named_OR',or_planes,or_members,or_fits)]:
            label,_=solve.assignment(d,pp,mm);xyz,pids,acc,target,reason,checks=ex.project_map(d,pp,label)
            assert not np.any(acc&~eligible) if name=='named_OR' else not np.any(acc&~direct_any)
            assert ahash(xyz[~eligible])==ahash(d['xyz'][~eligible])
            assert ahash(xyz[blocked])==ahash(d['xyz'][blocked])
            cov=ex.visibility(d,xyz);states[name]=(xyz,pids,pp)
            save_map(out/name,d,xyz,pids,pp,name,source_records)
            np.savez_compressed(out/name/'fit_support.npz',**{f'fit_{i}':a for i,a in enumerate(ff)})
            summaries[name]=dict(accepted=int(acc.sum()),accepted_fraction=float(acc.mean()),rescued_unknown_pixels=int(np.sum(acc&~direct_any)),
                active_planes=len(np.unique(pids[pids>=0])),checks=checks,visibility=cov,heldout=ex.match_metrics(d,xyz,pids),
                accepted_by_tag={tag:int(sum(np.sum(pids==p['plane_id']) for p in pp if p['semantic_tag']==tag)) for tag in sorted(ALLOWED)})
            st.log('arm_finished',arm=name,accepted=int(acc.sum()),rescued=int(np.sum(acc&~direct_any)),coverage_passed=cov['passed'])
        initial_label=np.full(N,-1,np.int32);save_map(out/'initial',d,d['xyz'],initial_label,or_planes,'initial',source_records)
        proposed,labels,pp=states['named_OR'];passed=summaries['named_OR']['visibility']['passed'];ret=proposed if passed else d['xyz'];rl=labels if passed else initial_label
        save_map(out/'retained',d,ret,rl,pp,'retained_proposed' if passed else 'retained_initial',source_records)
        rows=[];maskrows=[];captions=[]
        for f in range(n):
            sl=slice(f*h*w,(f+1)*h*w);rgb=d['rgb'][f];before=np.zeros_like(rgb);after=before.copy()
            for x,image in [(d['xyz'],before),(proposed,after)]:
                _,winner,_=c.front(x,d['k'][f],d['e'][f],h,w);hit=winner>=0;image[hit]=d['raw_rgb'][winner[hit]]
            show=rgb.copy();local=direct_any[sl].reshape(h,w);rescue=(eligible[sl]&~direct_any[sl]).reshape(h,w)
            show[local]=[0,255,0];show[rescue]=[0,0,255]
            untouched=~eligible[sl].reshape(h,w);show[untouched]=np.rint(.6*show[untouched]+.4*np.array([255,0,0])).astype('uint8')
            rows.append([rgb,before,after]);maskrows.append([rgb,show]);captions.append(f"index {d['frames'][f]['index']} | newly named {rescue.mean():.2%}")
        contact(st.path/'artifacts/figures/rgb_comparison.png',rows,['Original RGB','FoV initial','Named OR proposed'],captions)
        contact(st.path/'artifacts/figures/named_OR_mask.png',maskrows,['Original RGB','GREEN local | BLUE transferred | RED excluded'],captions)
        c.json_write(st.path/'evaluation/arms.json',summaries)
        c.json_write(st.path/'evaluation/controls.json',controls)
        c.json_write(st.path/'evaluation/ply_inventory.json',[c.record(p) for p in sorted(out.rglob('*.ply'))])
        st.finish(dict(decision='NAMED_OR_PLANE_TEST_EXECUTED',allowed_tags=sorted(ALLOWED),arms=summaries,retained='proposed' if passed else 'initial',
            no_named_support_unchanged_bitwise=True,other_named_blocked_bitwise=True,OR_order_invariant=True,geometry_types=['plane'],
            raw_named_fraction=float(direct_any.mean()),eligible_OR_fraction=float(eligible.mean()),box_cylinder_sphere_applied=False),
            '# I10 named OR 평면 투영\n\n동일 표면으로 연결된 region의 named 정보를 OR했다. 서로 다른 카메라의 같은 픽셀 좌표를 OR하지 않았다. '
            '원본 RGB의 동결 fit 대응 2개 이상과 기존 양방향 유한 평면 투영/기하 양립 조건을 만족한 cross-view 연결만 사용하고, 그룹 전체의 모든 쌍을 검사했다. '
            '해당 연결을 못 찾은 관측은 보수적으로 미확정으로 남긴다.\n\n'
            '첫 허용 목록은 exact `wall/table/screen`이다. 혼합 태그와 그 밖의 named는 보류하며, 원본 GroundedSAM의 screen도 유효한 평면 fit가 있으면 허용한다. '
            'AMG unknown 자체를 평면 근거로 사용하지 않고, 같은 표면의 다른 view에 named 근거가 있는 경우에만 소속을 전달한다. '
            '명백한 평면 여부는 기존 fit-only robust plane/최소 지원/퇴화 조건으로 검사하며 semantic 또는 geometry GT는 아니다.\n\n'
            'named_local과 named_OR를 함께 실행했다. 카메라·RGB·관측 ID·점 수를 고정하고 단일 world plane과 자기 픽셀 광선의 교차로 이동했다. '
            'I6 공동 최적화·수직/평행 prior·박스/원통/구 모델은 적용하지 않았다. 원래 오류 크기에 따른 이동 상한도 추가하지 않았다. '
            '모든 view에서 named 근거가 없는 관측과 보류된 다른 named 영역의 XYZ bitwise 보존을 검사했다.\n\n'
            '![소속 OR](figures/named_OR_mask.png)\n\n![투영 비교](figures/rgb_comparison.png)\n\n'
            '초록은 현재 view의 허용 named, 파랑은 다른 view에서 OR로 전달된 신규 후보, 빨강은 제외 영역이다. 파랑/초록 후보도 fit 또는 수치 교차가 실패하면 이동하지 않는다. '
            '원래 마스크가 책·종이 등을 잘못 포함한 경우까지 semantic GT로 보장하지 않는다. 가시성 실패 시 retained는 initial이며 proposed를 별도 보존한다.')
        return st.path
    except Exception as e:st.fail(e);raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',default='tum-freiburg1_desk');args=parser.parse_args();run(args.dataset)
