"""Integration fixtures independent of real-scene validation or manual H-series choices."""
from core import *

def run():
    from solve import graph_build,relation_model_scores
    n,h,w=3,24,32;k=np.tile(np.array([[40.,0,16],[0,40,12],[0,0,1]]),(3,1,1));e=np.tile(np.c_[np.eye(3),np.zeros(3)],(3,1,1))
    uv=np.tile(np.indices((h,w))[::-1].reshape(2,-1).T,(3,1));fid=np.repeat(np.arange(3),h*w);q=np.c_[uv[:,0]-16,uv[:,1]-12,np.full(len(uv),40.)]/40
    d=dict(dataset='synthetic',depth=np.full((n,h,w),2.),fid=fid,uv=uv,k=k,e=e,centers=np.zeros((3,3)),center_points=np.zeros_like(q),q=q,xyz=q*2,d0=np.full(len(uv),2.))
    empty=dict(pair=np.zeros((0,2),int),uv_i=np.zeros((0,2)),uv_j=np.zeros((0,2)),validation=np.zeros(0,bool))
    ids=[np.flatnonzero(fid==i) for i in range(3)];rs=[]
    for i,ii in enumerate(ids):rs.append(dict(region_id=i,frame=i,state='planar',source_masks=[i],fit=fit_plane(d['xyz'][ii],d['d0'][ii],fid[ii])))
    same,_,_,audit=graph_build(d,rs,ids,ids,matches_override=empty);assert len(same)==1 and same[0]['status']=='multi_view'
    assert same[0]['position_observability']['status']=='LOW_PARALLAX_RAW_ANCHORED'
    dd=dict(d);dd['xyz']=d['xyz'].copy();dd['d0']=d['d0'].copy()
    for i,ii in enumerate(ids):dd['xyz'][ii]=q[ii]*(2+i*.2);dd['d0'][ii]=2+i*.2
    rr=[]
    for i,ii in enumerate(ids):rr.append(dict(region_id=i,frame=i,state='planar',source_masks=[i],fit=fit_plane(dd['xyz'][ii],dd['d0'][ii],fid[ii])))
    separate,_,_,_=graph_build(dd,rr,ids,ids,matches_override=empty);assert len(separate)==3
    a=np.array([1.,0,0,-2.]);b=np.array([0.,1,0,-2.]);scores,fit=relation_model_scores(a,b,[dict(valid=True,normal=a[:3].tolist())],[dict(valid=True,normal=b[:3].tolist())]);assert min(scores,key=scores.get)=='orthogonal'
    b=np.r_[np.cos(np.pi/3),np.sin(np.pi/3),0.,-2.];scores60,_=relation_model_scores(a,b,[dict(valid=True,normal=a[:3].tolist())],[dict(valid=True,normal=b[:3].tolist())]);assert min(scores60,key=scores60.get)=='free'
    rng=np.random.default_rng(0);outlier=rng.normal(size=(500,3));outlier[:,2]=abs(outlier[:,2])+1
    reflection=fit_plane(outlier,outlier[:,2],np.zeros(500,int));assert not reflection['valid']
    return dict(same_surface_shared=True,parallel_different_planes_kept=True,pure_rotation_position_uncertain=True,
        group_order_reversal=audit['group_order_invariant'],orthogonal_scores=scores,nonorthogonal_scores=scores60,
        nonorthogonal_not_forced=True,reflection_unknown=True,synthetic_plane_count=len(same),parallel_plane_count=len(separate))
if __name__=='__main__':print(json.dumps(run(),indent=2))
