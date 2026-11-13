"""Nested SAM masks denote two wall planes; preserve R and estimate orthogonal L."""
from base import *
from geometry import fit,orient,depth_gate,update
from evaluate import arm,wall_metrics
from h4f import mask_transfer
from scipy import ndimage,optimize

def orthogonal_fit(x,depth,right,initial):
 r=np.asarray(right[:3]);r=r/np.linalg.norm(r);axis=np.eye(3)[np.argmin(abs(r))];u=np.cross(r,axis);u/=np.linalg.norm(u);v=np.cross(r,u);U=np.c_[u,v];Y=x@U;nf=np.array(initial[:3]);nf-=nf@r*r
 if np.linalg.norm(nf)<1e-12:nf=u.copy()
 nf/=np.linalg.norm(nf);th=float(np.arctan2(nf@v,nf@u));sols=[]
 def residual(a):return (Y@np.array([np.cos(a[0]),np.sin(a[0])])+a[1])/depth
 for start in [th,th+np.pi/2,0.,np.pi/2]:
  d=-np.median(Y@np.array([np.cos(start),np.sin(start)]));s=optimize.least_squares(residual,[start,d],loss='huber',f_scale=.005,max_nfev=2000,ftol=1e-12,xtol=1e-12,gtol=1e-12);sols.append(s)
 best=min(sols,key=lambda s:s.cost);n=U@np.array([np.cos(best.x[0]),np.sin(best.x[0])]);p=orient(np.r_[n,best.x[1]]);res=abs(x@p[:3]+p[3])/depth;support=res<=.005;valid=best.success and support.sum()>=100 and support.mean()>=.7
 return {'valid':bool(valid),'reason':'VALID' if valid else 'INSUFFICIENT_CONSTRAINED_SUPPORT','method':'right-normal-nullspace theta/offset Huber least_squares, four training-loss starts','plane':p.tolist(),'count':len(x),'frames':[{'frame':1,'fit_count':len(x),'inliers':int(support.sum()),'fraction':float(support.mean())}],'inlier_fraction':float(support.mean()),'reference_depth':float(np.median(depth)),'normalized_residual':c.stats(res),'centroid':x[support].mean(0).tolist() if support.any() else x.mean(0).tolist(),'normal_dot_right':float(p[:3]@r),'angle_with_right_degree':float(np.rad2deg(np.arccos(np.clip(abs(p[:3]@r),0,1)))),'converged':bool(best.success),'cost':float(best.cost),'nfev':int(best.nfev),'starts':[{'cost':float(s.cost),'success':bool(s.success),'nfev':int(s.nfev)} for s in sols]}

def synthetic():
 rng=np.random.default_rng(0);x=np.c_[np.ones(400)*2,rng.uniform(-1,1,(400,2))];right=np.array([0.,0,1,-3.]);initial=np.array([1.,0,0,-2.]);result=orthogonal_fit(x,np.ones(400)*3,right,initial);assert result['valid'];p=np.array(result['plane']);assert abs(p[:3]@right[:3])<1e-12 and np.max(abs(x@p[:3]+p[3]))<1e-9
 small=np.zeros((30,40),bool);small[2:15,20:38]=True;big=small.copy();big[2:15,2:15]=True;big[22,32]=True;lab,num=ndimage.label(big&~small,np.ones((3,3)));sizes=np.bincount(lab.ravel());sizes[0]=0;left=lab==sizes.argmax();assert not np.any(left&small) and left.sum()==169 and (big&~small&~left).sum()==1
 return {'known_orthogonal_plane_recovered':True,'nested_mask_right_priority_left_component_ambiguity':True}

def run():
 os.environ['H_OBSERVATION_STAGE']='H2d';h1,h2,h4,hf=[latest(code) for code in ['H1','H2d','H4d','H4f']]
 st=Stage('H4g',parents=[h1,h2,h4,hf],extra={'max_relative_move':None,'normal_membership_gate':None,'minimum_ray_cosine':1e-8,'two_wall_relation':'user provided perpendicular prior, not measured GT','right_plane_refit':False,'left_plane_fit_source':'original C3a, camera1 largest big-minus-small connected component, strict fit split','plan':c.record(Path(__file__).parent/'H4g/plan.md'),'execution_context':'host CPU; no CUDA or model inference'})
 try:
  shutil.copy2(Path(__file__).parent/'H4g/plan.md',st.path/'artifacts/source/H4g_plan.md');checks=synthetic();data=load();N=len(data['xyz']);size=384*512;rgroup=json.loads((h4/'artifacts/associations/refined/groups.json').read_text())[0];pr=np.array(rgroup['fit']['plane']);oldpath=hf/'artifacts/arms/SAM_SHARED_UNCAPPED/proposed/pointmap.npz';old=dict(np.load(oldpath));masks=[np.load(h1/f'artifacts/masks/camera_{i}_masks.npz')['masks'].copy() for i in range(3)];small,big=masks[1];extra=big&~small;lab,num=ndimage.label(extra,np.ones((3,3)));sizes=np.bincount(lab.ravel());sizes[0]=0;left=lab==sizes.argmax();ambiguous=extra&~left;left_ids=np.flatnonzero(left.ravel())+size;extra_ids=np.flatnonzero(extra.ravel())+size
  hold=np.load(h2/'artifacts/masks/splits_rois.npz')['holdout'][1];conf=data['conf'][1]>=np.percentile(data['conf'][1],10);fitmask=ndimage.binary_erosion(left,iterations=3)&~hold&conf;fitids=np.flatnonzero(fitmask.ravel())+size;holdids=np.flatnonzero((left&hold).ravel())+size;free=fit(data['xyz'][fitids],data['d0'][fitids],data['fid'][fitids]);assert free['valid'],free
  orth=orthogonal_fit(data['xyz'][fitids],data['d0'][fitids],pr,np.array(free['plane']));assert orth['valid'],orth
  assert abs(np.array(orth['plane'][:3])@pr[:3])<1e-12
  for info in [free,orth]:
   p=np.array(info['plane']);info['holdout_before_correction']=c.stats(abs(data['xyz'][holdids]@p[:3]+p[3])/data['d0'][holdids]);info['angle_with_right_degree']=float(np.rad2deg(np.arccos(np.clip(abs(p[:3]@pr[:3]),0,1))))
  maskdir=st.path/'artifacts/masks';maskdir.mkdir(parents=True);np.savez_compressed(maskdir/'nested_wall_split.npz',right_small=small,left_extra=extra,left_component=left,ambiguous=ambiguous,fit=fitmask,holdout=hold,fit_ids=fitids,holdout_ids=holdids,left_ids=left_ids,original_ids=data['ids']);c.json_write(st.path/'evaluation/plane_fits.json',{'right':rgroup['fit'],'left_free':free,'left_orthogonal':orth,'fit_source_count':len(fitids),'user_prior':'two walls perpendicular','not_gt':True})
  rmask=old['accepted'].copy();rmask[extra_ids]=False;rmask[size:2*size]|=small.ravel();leftmask=np.zeros(N,bool);leftmask[left_ids]=True;assert not np.any(rmask&leftmask)
  # The same L world plane may be used in another frame; no second L is fitted.
  p=np.array(orth['plane']);dl,vl,_=depth_gate(data['d0'],data['q'],data['center_points'],p,None,1e-8);dr,vr,_=depth_gate(data['d0'],data['q'],data['center_points'],pr,None,1e-8);xl=data['center_points']+np.where(np.isfinite(dl),dl,data['d0'])[:,None]*data['q'];xr=data['center_points']+np.where(np.isfinite(dr),dr,data['d0'])[:,None]*data['q'];lv=mask_transfer(data,xl,vl,{1:left});rv=mask_transfer(data,xr,vr,{0:masks[0][0],1:small});lmask2=leftmask.copy();rtransfer=rmask.copy();components,number=ndimage.label(masks[2][0],np.ones((3,3)));transfer=[]
  for j in range(1,number+1):
   ids=np.flatnonzero((components==j).ravel())+2*size
   if len(ids)<100:continue
   lc=int(np.sum(lv[ids]>0));rc=int(np.sum(rv[ids]>0));lf=lc/len(ids);rf=rc/len(ids);accept=lc>=100 and lf>=.5 and lf-rf>=.2;transfer.append({'frame':2,'component':j,'pixels':len(ids),'left_supported':lc,'right_supported':rc,'left_fraction':lf,'right_fraction':rf,'assigned_left':accept})
   if accept:lmask2[ids]=True;rtransfer[ids]=False
  assert not np.any(lmask2&rtransfer);c.json_write(st.path/'evaluation/plane_transfer.json',transfer);np.savez_compressed(maskdir/'global_plane_membership.npz',right_local_only=rmask,left_local_only=leftmask,right_with_transfer=rtransfer,left_with_transfer=lmask2,left_reference_votes=lv,right_reference_votes=rv)
  for i in range(3):
   im=data['rgb'][i].copy();rs=rmask.reshape(3,384,512)[i];ls=lmask2.reshape(3,384,512)[i];im[rs]=np.rint(.5*im[rs]+.5*np.array([0,255,80])).astype(np.uint8);im[ls]=np.rint(.5*im[ls]+.5*np.array([255,90,0])).astype(np.uint8)
   if i==1:im[ambiguous]=[255,0,255]
   c.image_write(st.path/f'artifacts/figures/camera{i}_two_wall_membership.png',im)
  repro=update(data,[rgroup|{'ids':np.flatnonzero(old['accepted'])}],max_relative_move=None,minimum_ray_cosine=1e-8);assert np.array_equal(repro[0],old['xyz']) and np.array_equal(repro[1],old['accepted']);checks['H4f_control_bitwise']=True
  rows=[];cache={};protected=old['accepted']&~np.isin(data['ids'],extra_ids);protected_c01=protected&(data['fid']<2);baseline=wall_metrics(data,data['xyz'],st.path/'artifacts/baseline/sections')
  specs=[('F_CONTROL',old['accepted'],None,None),('SPLIT_RESTORE_LEFT',rmask,None,None),('TWO_PLANES_FREE',rmask,leftmask,free),('TWO_PLANES_ORTHO',rmask,leftmask,orth),('TWO_PLANES_ORTHO_TRANSFER',rtransfer,lmask2,orth)]
  for name,rs,ls,lf in specs:
   groups=[rgroup|{'ids':np.flatnonzero(rs)}]
   if ls is not None:groups.append({'ids':np.flatnonzero(ls),'candidate_ids':['camera1_big_minus_small_left'],'fit':lf})
   st.log('arm_started',name=name,right_members=int(rs.sum()),left_members=int(ls.sum()) if ls is not None else 0);r=arm(st,data,name,groups,max_relative_move=None,minimum_ray_cosine=1e-8);out=st.path/'artifacts/arms'/name
   with np.load(out/'proposed/pointmap.npz') as z:
    xyz=z['xyz'];accepted=z['accepted'];assert np.array_equal(xyz[~accepted],data['xyz'][~accepted]);preserve=protected_c01 if name.endswith('TRANSFER') else protected
    assert np.array_equal(xyz[preserve],old['xyz'][preserve]),name
    if name=='F_CONTROL':assert np.array_equal(xyz,old['xyz'])
    if name!='F_CONTROL':
     extra_right=(z['local_plane_id'][extra_ids]==0)&accepted[extra_ids];assert not extra_right.any()
     if name=='SPLIT_RESTORE_LEFT':assert np.array_equal(xyz[extra_ids],data['xyz'][extra_ids])
     else:assert np.array_equal(xyz[np.flatnonzero(ambiguous.ravel())+size],data['xyz'][np.flatnonzero(ambiguous.ravel())+size])
    angle=lf.get('angle_with_right_degree') if lf else None;byplane=[];colors=np.full((N,3),135,np.uint8)
    for pid,g in enumerate(groups):
     hits=accepted&(z['local_plane_id']==pid);p=np.array(g['fit']['plane']);res=abs(xyz[hits]@p[:3]+p[3]);assert len(res)==0 or res.max()<1e-9;colors[hits]=[0,230,80] if pid==0 else [255,110,0];byplane.append({'plane_id':pid,'role':'right' if pid==0 else 'left','fit_frames':[v['frame'] for v in g['fit']['frames']],'moved_per_frame':[int(np.sum(hits&(data['fid']==i))) for i in range(3)],'plane_max_residual':float(res.max()) if len(res) else None})
    c.ply_write(out/'proposed/plane_colors.ply',xyz,colors,data['fid']);r|={'plane_angle_degree':angle,'plane_roles':byplane,'left_wall_points':len(left_ids),'left_wall_moved':int(accepted[left_ids].sum()),'left_wall_wrongly_assigned_right':int(np.sum((z['local_plane_id'][left_ids]==0)&accepted[left_ids])),'right_C01_H4f_bitwise_preserved':True,'ambiguous_pixels_restored_C3a':int(ambiguous.sum()) if name!='F_CONTROL' else 0,'world_planes':len(groups),'left_plane_estimated_frames':[1] if lf else [],'geometry_GT_evaluated':False};cache[name]=xyz.copy()
   c.json_write(out/'metrics.json',r);rows.append(r);st.log('arm_completed',name=name,left_moved=r['left_wall_moved'],angle=angle,right_preserved=True)
  checks|={'right_C01_unchanged_all_arms':True,'corrected_left_never_on_right_plane':True,'left_right_memberships_disjoint':True,'orthogonality_dot_below_1e12':True,'unassigned_and_ambiguous_C3a_restored':True,'all_accepted_points_on_assigned_plane':True};c.json_write(st.path/'evaluation/technical_checks.json',checks)
  inputs=[c.record(oldpath),c.record(h4/'artifacts/associations/refined/groups.json'),c.record(h2/'artifacts/masks/splits_rois.npz')]+[c.record(h1/f'artifacts/masks/camera_{i}_masks.npz') for i in range(3)]+data['inputs'];c.json_write(st.path/'evaluation/inputs.json',inputs);views=render_views(st,data,rows,cache,pr,np.array(orth['plane']),left_ids,protected)
  report='# H4g 꺾인 두 벽 분리와 수직 평면 보정\n\n사용자가 camera1 큰 마스크의 왼쪽이 오른쪽 벽에 수직인 별도 벽이라고 확인했다. **H4f의 큰 마스크 전체→오른쪽 평면 소속은 잘못된 연결이었다.** 기존 H4f를 보존하고 작은 마스크 우선·큰-minus-작은 왼쪽 최대 연결 성분을 분리했다. 왼쪽 주요 성분은 8,290점, 전체 차집합 8,521점 중 나머지 231점은 모호한 경계로 C3a에 복원한다.\n\n'
  report+='오른쪽 plane은 기존 H4d A4 그대로이며 이미 좋아진 오른쪽의 H4f XYZ를 bitwise 보존했다. 왼쪽 plane은 잘못 이동한 H4f가 아니라 원래 C3a의 왼쪽 내부 fit '+str(len(fitids))+'점에서 추정했다. confidence/erosion/split은 적합 지원에만 사용하고 이동 대상 8,290점을 잘라내지 않았다. 새 hard 이동은 계속 uncapped다.\n\n'
  report+=f"자유 적합의 두 평면 각도는 {free['angle_with_right_degree']:.4f}°, 사용자 수직 prior를 적용한 적합은 {orth['angle_with_right_degree']:.4f}°다. 수직 적합 fit inlier 비율은 {orth['inlier_fraction']:.2%}다. 정확히90°는 부과한 제약의 충족이며 실제 각도의 독립 측정 결과가 아니다. L plane은 camera1에서만 적합했고 다른 카메라에는 그 계수를 재사용한다. 왼쪽 offset과 corner 교선의 GT 위치는 미검증이다.\n\n"
  report+='| 군 | world 평면 수 | 왼쪽 이동 | 왼쪽→오른쪽 오소속 | 두 평면 각도 | 기존 오른쪽 보존 | 가시성 포함 보존 | retained |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n'
  for r in rows:report+=f"| {r['name']} | {r['world_planes']} | {r['left_wall_moved']} | {r['left_wall_wrongly_assigned_right']} | {r['plane_angle_degree']} | {r['right_C01_H4f_bitwise_preserved']} | {r['preservation_passed']} | {r['retained_state']} |\n"
  report+='\nF_CONTROL은 의도적으로 기존 오류를 그대로 재현한 군이다. SPLIT_RESTORE_LEFT는 오소속만 해제해 C3a로 복원한 제어다. TWO_PLANES_FREE/ORTHO는 같은 소속에서 평면 제약만 비교한다. TRANSFER는 camera2의 H1 연결 성분을 각 평면의 2D 참조 마스크 지지로 연결하며 pixel>=100·fraction>=50%·R 대비20pp를 만족한 L만 추가한다. 새 frame2 plane을 적합하지 않는다. 연결 근거와 모호 판정은 JSON에 있다. source0/1의 오른쪽 기존 보정은 모두 유지했다.\n\n'
  report+='각 군의 실제 proposed를 모두 보존했다. camera1 왼쪽 mask를 R로 보내는 관측은 수정군에서 0이며 231개 모호한 점은 원래 위치로 복원했다. 원본 RGB/ID/카메라/589,824점·거절점 불변, 자기 재투영, H4f 재현, plane 잔차·수직 제약·오른쪽 bitwise 보존을 검증했다. 가시성 기준 실패 시 retained는 A0이므로 실제 변화는 proposed에서 확인한다. 기존 고정 G6 벽 ROI는 R만 보므로 새 왼쪽 개선 평가를 대신할 수 없다. L holdout의 보정 후 plane 잔차0은 정확도 증거가 아니다.\n\n'
  report+='주 비교 PLY: `artifacts/arms/TWO_PLANES_ORTHO_TRANSFER/proposed/`. 원본 픽셀색·프레임색 외 `plane_colors.ply`는 R=초록/L=주황/미보정=회색이다. 같은 고정 시점 corner 단면 및 camera1 소속 overlay로 꺾임을 확인한다. 실제 기하 정확도와 사용자 prior의 계측 검증은 미평가다.\n'
  st.finish({'decision':'COMPLETED_TWO_WALL_MEMBERSHIP_CORRECTION','scientific_improvement':False,'arms':rows,'planes':{'right':rgroup['fit'],'left_free':free,'left_orthogonal':orth},'technical_checks':checks,'camera2_transfer':transfer,'baseline_wall':baseline,'inputs':inputs,'views':views,'primary_arm':'TWO_PLANES_ORTHO_TRANSFER','mask_split':{'small':int(small.sum()),'big':int(big.sum()),'intersection':int((small&big).sum()),'extra':int(extra.sum()),'left':int(left.sum()),'ambiguous':int(ambiguous.sum())}},report)
  shutil.copy2(st.path/'evaluation/ply_inventory.csv',st.doc/'evaluation/ply_inventory.csv')
  with (DOC/'index.md').open('a') as f:f.write(f'| H4g | 완료·꺾인 두 벽 소속/수직 평면 5군 | [{st.run_id}]({st.doc.relative_to(DOC)}/report.md) |\n')
 except Exception as e:st.fail(e);raise

def render_views(st,data,rows,cache,right,left,leftids,rightids):
 import csv
 # Frozen A0 coordinates and axes for a top/corner view, not selected after correction.
 r=right[:3];l=left[:3];corner_direction=np.cross(r,l);corner_direction/=np.linalg.norm(corner_direction);corner=np.linalg.lstsq(np.stack([r,l]),-np.array([right[3],left[3]]),rcond=None)[0];selected=np.r_[leftids,np.flatnonzero(rightids&(data['fid']==1))];Q=data['xyz'][selected]-corner;coords=np.c_[Q@l,Q@r];bounds=np.array([np.percentile(coords,0,axis=0),np.percentile(coords,100,axis=0)]);span=np.maximum(bounds[1]-bounds[0],.1);bounds[0]-=.25*span;bounds[1]+=.25*span
 # Include corner origin and keep identical, near-square model-unit axes.
 bounds[0]=np.minimum(bounds[0],-.1*span);bounds[1]=np.maximum(bounds[1],.1*span);center=bounds.mean(0);extent=max(bounds[1]-bounds[0]);bounds=np.array([center-extent/2,center+extent/2]);clipping=[];figs=[];inventory=[];review=FAMILY/'ply_review'
 for row in rows:
  name=row['name'];xyz=cache[name];q=xyz[selected]-corner;xy=np.c_[q@l,q@r];px=80+(xy[:,0]-bounds[0,0])/(bounds[1,0]-bounds[0,0])*600;py=640-(xy[:,1]-bounds[0,1])/(bounds[1,1]-bounds[0,1])*600;ok=(px>=70)&(px<700)&(py>=35)&(py<660);canvas=np.full((720,720,3),250,np.uint8);origin=[int(80-bounds[0,0]/(bounds[1,0]-bounds[0,0])*600),int(640+bounds[0,1]/(bounds[1,1]-bounds[0,1])*600)];c.cv2.line(canvas,(70,origin[1]),(700,origin[1]),(160,160,160),1);c.cv2.line(canvas,(origin[0],35),(origin[0],660),(160,160,160),1)
  colors=np.tile([0,205,70],(len(selected),1));colors[:len(leftids)]=[255,110,0];canvas[py[ok].astype(int),px[ok].astype(int)]=colors[ok];c.cv2.putText(canvas,name,(20,23),0,.5,(20,20,20),1);c.cv2.putText(canvas,'fixed A0 view | orange=left IDs green=right IDs',(20,695),0,.45,(20,20,20),1);c.image_write(st.path/f'artifacts/figures/{name}_corner_section.png',canvas);figs.append(canvas);clipping.append({'arm':name,'clipped':int((~ok).sum()),'observations':len(selected)})
  out=st.path/'artifacts/arms'/name
  for state in ['initial','proposed','retained']:
   for color in ['pixel_rgb','frame_colors']:
    path=out/state/(color+'.ply');inventory.append({'arm':name,'state':state,'color':color,'resolved_file':str(path.resolve()),**c.record(path)})
  for color in ['pixel_rgb','frame_colors','plane_colors']:
   path=out/'proposed'/(color+'.ply');link=review/f'H4g_{st.run_id}_{name}_{color}.ply';link.symlink_to(os.path.relpath(path,review))
  c.json_write(out/'plane_colors_legend.json',{'right':[0,230,80],'left':[255,110,0],'unmoved':[135,135,135]})
 panel=np.full((1440,2160,3),250,np.uint8)
 for ix,im in enumerate(figs):panel[(ix//3)*720:(ix//3+1)*720,(ix%3)*720:(ix%3+1)*720]=im
 c.image_write(st.path/'artifacts/figures/corner_sections_comparison.png',panel)
 for camera in range(3):
  ims=[data['rgb'][camera]];titles=['original']
  for row in rows:
   name=row['name'];path=st.path/'artifacts/arms'/name/'projections'/f'camera_{camera}_rgb.png';ims.append(c.cv2.imread(str(path))[...,::-1]);titles.append(name)
  c.panel(st.path/f'artifacts/figures/camera{camera}_comparison.png',[ims],titles)
 c.json_write(st.path/'evaluation/ply_inventory.json',inventory)
 with (st.path/'evaluation/ply_inventory.csv').open('w') as f:writer=csv.DictWriter(f,fieldnames=inventory[0].keys());writer.writeheader();writer.writerows(inventory)
 np.savez_compressed(st.path/'evaluation/fixed_corner_view.npz',right_plane=right,left_plane=left,corner=corner,corner_direction=corner_direction,ids=selected,xy_bounds=bounds)
 return {'corner':corner.tolist(),'corner_direction':corner_direction.tolist(),'bounds':bounds.tolist(),'clipping':clipping,'ply_inventory_items':len(inventory),'fixed_from_A0_and_plane_prior':True}

if __name__=='__main__':run()
