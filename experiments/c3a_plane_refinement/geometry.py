"""Deterministic robust planes, pairwise association and fixed-ray depth updates."""
import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from base import CFG,c

def orient(p):
 if p[np.argmax(abs(p[:3]))]<0:p=-p
 return p

def weighted_plane(x,w):
 mean=np.average(x,axis=0,weights=w);a=x-mean;cov=(a*w[:,None]).T@a/w.sum();vals,vec=np.linalg.eigh(cov)
 p=orient(np.r_[vec[:,0],-vec[:,0]@mean]);return p,vals,mean

def fit(x,depth,frame):
 x=np.asarray(x,float);depth=np.asarray(depth,float);frame=np.asarray(frame);N=len(x)
 if N<100:return {'valid':False,'reason':'LOW_SUPPORT','count':N}
 rng=np.random.default_rng(0);scoreids=np.arange(N) if N<=4096 else np.sort(rng.choice(N,4096,replace=False))
 xs=x[scoreids];ds=depth[scoreids];fs=frame[scoreids];uw=np.ones(len(xs))
 for f in np.unique(fs):uw[fs==f]=1/np.sum(fs==f)
 best=-1.;bp=None;trials=0;limit=2000
 for it in range(limit):
  a,b,cc=x[rng.choice(N,3,replace=False)];normal=np.cross(b-a,cc-a);norm=np.linalg.norm(normal)
  if norm<1e-12:continue
  normal/=norm;p=np.r_[normal,-normal@a];inside=abs(xs@normal+p[3])/ds<=.005;s=float(uw@inside/uw.sum())
  if s>best:best=s;bp=p
  trials=it+1
  # Conservative 99.99% probability, at least 64 trials, max 2000.
  required=2000 if best<=0 else int(np.ceil(np.log(1e-4)/np.log(max(1e-12,1-min(best,.999999)**3))))
  if trials>=max(64,required):break
 if bp is None:return {'valid':False,'reason':'DEGENERATE_PLANE_SUPPORT','count':N}
 weights=np.ones(N)
 for f in np.unique(frame):weights[frame==f]=1/np.sum(frame==f)
 p=bp
 for it in range(20):
  res=abs(x@p[:3]+p[3])/depth
  # RANSAC consensus followed by normalized Huber weights; outliers do not define the plane.
  support=res<=.005
  if support.sum()<3:break
  hub=np.minimum(1.,.005/np.maximum(res,1e-15));w=weights*hub/depth**2*support
  pn,vals,mean=weighted_plane(x,w)
  if np.linalg.norm(pn-orient(p))<1e-10:p=pn;break
  p=pn
 res=abs(x@p[:3]+p[3])/depth;support=res<=.005
 rows=[{'frame':int(f),'fit_count':int(np.sum(frame==f)),'inliers':int(np.sum(support&(frame==f))),'fraction':float(np.mean(support[frame==f]))} for f in np.unique(frame)]
 p,vals,mean=weighted_plane(x,weights*support/np.maximum(depth,1e-12)**2) if support.sum()>=3 else (p,np.zeros(3),x.mean(0))
 res=abs(x@p[:3]+p[3])/depth;support=res<=.005
 rows=[{'frame':int(f),'fit_count':int(np.sum(frame==f)),'inliers':int(np.sum(support&(frame==f))),'fraction':float(np.mean(support[frame==f]))} for f in np.unique(frame)]
 axis_ratio=float(vals[1]/max(vals[2],1e-30));second_span=4*np.sqrt(max(vals[1],0))/np.median(depth)
 degenerate=axis_ratio<1e-4 or second_span<.01
 valid=not degenerate and all(r['inliers']>=100 and r['fraction']>=.7 for r in rows)
 return {'valid':bool(valid),'reason':'VALID' if valid else ('DEGENERATE_PLANE_SUPPORT' if degenerate else 'INSUFFICIENT_INLIERS'),'plane':p.tolist(),'centroid':mean.tolist(),'eigenvalues':vals.tolist(),'second_first_ratio':axis_ratio,'second_axis_span_depth':float(second_span),'frames':rows,'count':N,'ransac_trials':trials,'ransac_scoring_points':len(scoreids),'ransac_scoring_cap':4096,'irls_iterations':it+1,'normalized_residual':c.stats(res),'inlier_fraction':float(support.mean()),'reference_depth':float(np.median(depth))}

def depth_gate(d0,q,centers,p):
 nq=q@p[:3];cos=abs(nq)/np.linalg.norm(q,axis=1)
 with np.errstate(divide='ignore',invalid='ignore'):target=-(centers@p[:3]+p[3])/nq
 finite=np.isfinite(target);positive=finite&(target>0);angle=cos>=.2
 move=np.zeros(len(d0));move[finite]=abs(target[finite]-d0[finite])/d0[finite]
 bounded=finite&(move<=.02+1e-14);accepted=positive&angle&bounded
 reason=np.full(len(d0),0,np.uint8);reason[~finite]=1;reason[finite&~positive]=2;reason[positive&~angle]=3;reason[positive&angle&~bounded]=4
 return target,accepted,reason

def update(data,groups,soft=False):
 xyz=data['xyz'].copy();D=data['d0'];accepted=np.zeros(len(D),bool);local=np.full(len(D),-1,np.int32);shared=local.copy();targets=D.copy();reason=np.full(len(D),5,np.uint8);plane_records=[]
 for gid,g in enumerate(groups):
  if not g['fit']['valid']:continue
  ids=np.asarray(g['ids'],np.int64);p=np.array(g['fit']['plane']);tar,gate,r=depth_gate(D[ids],data['q'][ids],data['center_points'][ids],p)
  assert not accepted[ids].any(),'conflicting membership'
  safe=ids[gate];delta=tar[gate]-D[safe]
  if soft:
   nq=data['q'][safe]@p[:3];delta*=nq*nq/(1+nq*nq)
  xyz[safe]=data['center_points'][safe]+(D[safe]+delta)[:,None]*data['q'][safe]
  accepted[safe]=True;targets[ids[gate]]=tar[gate];reason[ids]=r;local[ids]=gid
  if len(set(data['fid'][ids]))>=2:shared[ids]=gid
  plane_records.append({'group_id':gid,'candidate_ids':g.get('candidate_ids',[]),'fit':g['fit'],'candidate_points':len(ids),'accepted':int(gate.sum()),'gate_reasons':{str(i):int(np.sum(r==i)) for i in range(5)}})
 return xyz,accepted,local,shared,targets,reason,plane_records

def normals(data,window):
 n,h,w=data['depth'].shape;out=[];eig=[];valid=[]
 for i in range(n):
  x=data['xyz'][i*h*w:(i+1)*h*w]@data['e'][i,:,:3].T+data['e'][i,:,3]
  x=x.reshape(h,w,3);v=(data['conf'][i]>=np.percentile(data['conf'][i],10))&np.isfinite(x).all(2)&(x[...,2]>0)
  count=ndimage.uniform_filter(v.astype(float),size=window,mode='constant');mean=np.stack([ndimage.uniform_filter(x[...,j]*v,size=window,mode='constant')/np.maximum(count,1e-12) for j in range(3)],-1)
  cov=np.empty((h,w,3,3))
  for j in range(3):
   for k in range(3):cov[...,j,k]=ndimage.uniform_filter(x[...,j]*x[...,k]*v,size=window,mode='constant')/np.maximum(count,1e-12)-mean[...,j]*mean[...,k]
  ev,vec=np.linalg.eigh(cov);nn=vec[...,0];flip=np.sum(nn*x,axis=-1)>0;nn[flip]*=-1
  nn=nn@data['e'][i,:,:3];nn/=np.maximum(np.linalg.norm(nn,axis=-1,keepdims=True),1e-12)
  out.append(nn);eig.append(ev);valid.append(v&(count>.5))
 return np.array(out),np.array(eig),np.array(valid)

def components(mask,minarea):
 lab,num=ndimage.label(mask,np.ones((3,3)));sizes=np.bincount(lab.ravel());ids=np.flatnonzero(sizes>=minarea);return [lab==i for i in ids if i!=0]

def geometric_regions(x,norm,valid,depth):
 """Undirected 7x7 pixel graph, symmetric local tangent distance and normals."""
 h,w=valid.shape;grid=np.arange(h*w).reshape(h,w);rows=[];cols=[];cos=np.cos(np.deg2rad(15))
 for dy in range(4):
  for dx in range(-3,4):
   if dy==0 and dx<=0:continue
   y0=max(0,-dy);y1=min(h,h-dy);x0=max(0,-dx);x1=min(w,w-dx)
   a=(slice(y0,y1),slice(x0,x1));b=(slice(y0+dy,y1+dy),slice(x0+dx,x1+dx))
   diff=x[b]-x[a];good=valid[a]&valid[b]&(abs(np.sum(norm[a]*norm[b],-1))>=cos)&(abs(np.sum(diff*norm[a],-1))/depth[a]<=.005)&(abs(np.sum(diff*norm[b],-1))/depth[b]<=.005)
   rows.append(grid[a][good]);cols.append(grid[b][good])
 row=np.concatenate(rows);col=np.concatenate(cols);graph=coo_matrix((np.ones(len(row),bool),(row,col)),shape=(h*w,h*w)).tocsr();num,labels=connected_components(graph,directed=False)
 sizes=np.bincount(labels);big=np.flatnonzero(sizes>=int(np.ceil(.005*h*w)))
 return [(labels.reshape(h,w)==i)&valid for i in big]

def direction(data,ia,ib):
 # Distinct target pixels, not multiplicity of projected observations.
 h,w=data['depth'].shape[1:];target_mask=np.zeros(h*w,bool);target_mask[ib%(h*w)]=True
 i=int(data['fid'][ia[0]]);j=int(data['fid'][ib[0]]);uv,z,inside=c.project(data['xyz'][ia],data['k'][j],data['e'][j],h,w)
 src=np.flatnonzero(inside);xy=np.rint(uv[src]).astype(int);pix=xy[:,1]*w+xy[:,0];inmask=target_mask[pix]
 raw=src[inmask];pix=pix[inmask];ref=data['depth'][j].ravel()[pix];rel=(z[raw]-ref)/ref;depthok=abs(rel)<=.03
 count=len(np.unique(pix[depthok]));denom=len(np.unique((np.rint(uv[src]).astype(int)[:,1]*w+np.rint(uv[src]).astype(int)[:,0])))
 return {'source':i,'target':j,'source_points':len(ia),'in_frustum':len(src),'mask_overlap_points':len(raw),'valid_unique_pixels':count,'overlap_fraction':count/max(1,denom),'behind_target_occluded':int(np.sum(rel>.03)),'in_front_depth_mismatch':int(np.sum(rel<-.03)),'passed':count>=100 and count/max(1,denom)>=.2}

def pair_test(data,a,b):
 fa,fb=a['fit'],b['fit'];pa=np.array(fa['plane']);pb=np.array(fb['plane']);angle=float(np.rad2deg(np.arccos(np.clip(abs(pa[:3]@pb[:3]),0,1))))
 da=abs(np.array(fa['centroid'])@pb[:3]+pb[3])/fa['reference_depth'];db=abs(np.array(fb['centroid'])@pa[:3]+pa[3])/fb['reference_depth']
 dirs=[direction(data,a['ids'],b['ids']),direction(data,b['ids'],a['ids'])]
 passed=angle<=15 and da<=.01 and db<=.01 and all(r['passed'] for r in dirs)
 return {'a':a['candidate_id'],'b':b['candidate_id'],'normal_angle_degree':angle,'centroid_relative_distances':[float(da),float(db)],'directions':dirs,'passed':bool(passed)}

def associate(data,candidates):
 import itertools
 good=[a for a in candidates if a['fit']['valid']];edges={};records=[]
 for a,b in itertools.combinations(good,2):
  if a['frame']==b['frame']:continue
  row=pair_test(data,a,b);records.append(row);edges[tuple(sorted([a['candidate_id'],b['candidate_id']]))]=row['passed']
 # All-pair clique groups, largest first; no transitive chaining or conflicting corrections.
 possibilities=[]
 for k in [3,2]:
  for group in itertools.combinations(good,k):
   if len(set(a['frame'] for a in group))!=k:continue
   if not all(edges.get(tuple(sorted([a['candidate_id'],b['candidate_id']])),False) for a,b in itertools.combinations(group,2)):continue
   fitids=np.concatenate([a['fit_ids'] for a in group]);ft=fit(data['xyz'][fitids],data['d0'][fitids],data['fid'][fitids]);ids=np.concatenate([a['ids'] for a in group]);entry={'candidate_ids':[a['candidate_id'] for a in group],'ids':ids,'fit':ft}
   possibilities.append(entry)
 groups=[];used=set();joint=[]
 for g in sorted(possibilities,key=lambda x:(-len(x['candidate_ids']),-len(x['ids']),x['candidate_ids'])):
  overlap=any(i in used for i in g['candidate_ids']);ok=g['fit']['valid'] and not overlap
  joint.append({'candidate_ids':g['candidate_ids'],'fit':g['fit'],'selected':ok,'conflict':overlap})
  if ok:groups.append(g);used.update(g['candidate_ids'])
 return groups,{'pair_tests':records,'joint_tests':joint,'unassociated_candidates':[a['candidate_id'] for a in good if a['candidate_id'] not in used],'shared_groups':len(groups)}
