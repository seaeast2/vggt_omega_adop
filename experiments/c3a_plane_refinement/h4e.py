"""H4e: frozen world plane; cross-view footprint membership and threshold factorial."""
from base import *
from geometry import depth_gate,update
from evaluate import arm,wall_metrics,match_metrics

def footprint_votes(data,target_xyz,intersection_valid,masks,reference_gate=.03):
 """Confirm plane intersections against frozen reference-view masks/depths."""
 _,h,w=data['depth'].shape;votes=np.zeros(len(target_xyz),np.uint8);records=[]
 for frame,mask in sorted(masks.items()):
  uv,z,inside=c.project(target_xyz,data['k'][frame],data['e'][frame],h,w);ids=np.flatnonzero(inside&intersection_valid);xy=np.rint(uv[ids]).astype(int);inmask=mask[xy[:,1],xy[:,0]];maskids=ids[inmask];xy=xy[inmask];ref=data['depth'][frame,xy[:,1],xy[:,0]];rel=(z[maskids]-ref)/ref;good=abs(rel)<=reference_gate
  votes[maskids[good]]+=1;records.append({'reference_frame':int(frame),'in_frustum':len(ids),'in_wall_mask':len(maskids),'depth_agreement':int(good.sum()),'behind_reference':int(np.sum(rel>reference_gate)),'in_front_of_reference':int(np.sum(rel < -reference_gate))})
 return votes,records

def point_angles(normal,plane_normal):
 return np.rad2deg(np.arccos(np.clip(abs(normal@plane_normal),0,1)))

def controls():
 D=np.full(4,2.);q=np.array([[0,0,1.]]*4);C=np.zeros_like(q);p=np.array([0.,0.,1.,-2.10]);t,a,r=depth_gate(D,q,C,p,.05);assert a.all()
 assert not depth_gate(D,q,C,p,.02)[1].any()
 assert depth_gate(D,q,C,np.array([0.,0.,1.,-2.20]),.10)[1].all()
 assert not depth_gate(D,q,C,np.array([0.,0.,1.,-2.20001]),.10)[1].any()
 normals=np.array([[0,0,1.],[0,0,-1.],[1,0,0.],[.5,0,np.sqrt(.75)]]);angles=point_angles(normals,p[:3]);assert np.allclose(angles,[0,0,90,30])
 # Opposite side of a corner excluded even at 35deg; parallel displaced wall outside cap excluded.
 assert not (angles[2]<=35);assert not depth_gate(D,q,C,np.array([0.,0.,1.,-2.5]),.10)[1].any()
 synthetic={'depth':np.full((3,20,20),2.),'k':np.tile(np.array([[20.,0,10],[0,20,10],[0,0,1]]),(3,1,1)),'e':np.tile(np.c_[np.eye(3),np.zeros(3)],(3,1,1))}
 xyz=np.array([[0.,0,2.],[0.,0,2.2],[0.,0,-2.]]);mask=np.ones((20,20),bool);votes,recs=footprint_votes(synthetic,xyz,np.array([True,True,False]),{0:mask});assert votes.tolist()==[1,0,0]
 return {'depth_2_5_10pct_boundaries':True,'normal_sign_invariance':True,'corner_normal_rejection':True,'parallel_wall_outside_10pct_rejection':True,'reference_occlusion_and_negative_depth_rejection':True}

def run():
 os.environ['H_OBSERVATION_STAGE']='H2d';h4=latest('H4d');h2=latest('H2d')
 st=Stage('H4e',parents=[h4,h2,latest('H6a')],extra={'max_relative_move':'per arm 0.02/0.05/0.10','point_membership_angle_grid_degree':[15,25,35],'movement_grid':[.02,.05,.10],'frozen_reference_depth_gate':.03,'point_membership':'cross-view plane intersection footprint, no source-local cluster restriction','refit_plane':False,'default_candidate_selection':'none; fixed 12-arm diagnostic','plan':c.record(Path(__file__).parent/'H4e/plan.md'),'execution_context':'host CPU; no CUDA or model inference'})
 try:
  shutil.copy2(Path(__file__).parent/'H4e/plan.md',st.path/'artifacts/source/H4e_plan.md');test=controls();data=load();sources=[h4/'artifacts/associations/refined/groups.json',h4/'artifacts/associations/refined/group_observations.npz',h2/'artifacts/masks/normals.npz',h2/'artifacts/masks/candidates.json'];inputrecords=[c.record(p) for p in sources]
  rows=json.loads(sources[0].read_text());assert len(rows)==1;group=rows[0];group['ids']=np.load(sources[1])['group_0'];plane=np.array(group['fit']['plane']);normal=plane[:3];assert abs(np.linalg.norm(normal)-1)<1e-10
  norm=np.load(sources[2]);nn=norm['normals_7'].reshape(-1,3);valid=norm['valid'].copy();valid[:,:8]=False;valid[:,-8:]=False;valid[:,:,:8]=False;valid[:,:,-8:]=False;valid=valid.ravel();angles=point_angles(nn,normal)
  candidates=json.loads(sources[3].read_text());masks={};candidate_inputs=[]
  fit_frames={r['frame'] for r in group['fit']['frames']}
  for row in candidates['raw']:
   if row['frame'] not in fit_frames:continue
   p=h2/f"artifacts/masks/candidate_{row['candidate_id']:03}.npz";ids=np.load(p)['ids'];mask=masks.setdefault(row['frame'],np.zeros((384,512),bool));mask.ravel()[ids%(384*512)]=True;candidate_inputs.append(c.record(p))
  target,intersect,_=depth_gate(data['d0'],data['q'],data['center_points'],plane,.99)
  # Geometry of the wall footprint does not depend on a source point's move allowance.
  nq=data['q']@normal;finite=np.isfinite(target)&(target>0);intersect=finite&(abs(nq)/np.linalg.norm(data['q'],axis=1)>=.2);safe_depth=np.where(finite,target,data['d0']);target_xyz=data['center_points']+safe_depth[:,None]*data['q'];votes,confirm=footprint_votes(data,target_xyz,intersect,masks)
  eligible=valid&intersect&(votes>0);out=st.path/'artifacts/membership';out.mkdir(parents=True);np.savez_compressed(out/'frozen_membership.npz',observation_id=data['ids'],normal_angle_degree=angles,valid_normal_border=valid,positive_stable_intersection=intersect,reference_votes=votes,reference_footprint= votes>0,eligible_before_normal=eligible,plane=plane,target_depth=safe_depth)
  c.json_write(out/'reference_footprint.json',{'references':confirm,'raw_candidate_sources':candidate_inputs,'confirmed_frames':sorted(masks),'plane':plane.tolist(),'no_target_frame_semantic_mask_required':True})
  with np.load(h4/'artifacts/arms/A4_SHARED_REFINED/proposed/pointmap.npz') as old:
   repro=update(data,[group]);assert np.array_equal(repro[0],old['xyz']) and np.array_equal(repro[1],old['accepted']);test['legacy_A4_xyz_and_accepted_bitwise_reproduction']=True
  results=[];accepted_sets={};common_xyz={};baseline=wall_metrics(data,data['xyz'],st.path/'artifacts/baseline/sections');baselinegeo=match_metrics(data,data['xyz'],np.zeros(len(data['xyz']),bool));originalmask=np.zeros(len(data['xyz']),bool);originalmask[group['ids']]=True;rawmask_union=np.zeros(len(data['xyz']),bool)
  for frame,mask in masks.items():rawmask_union[frame*384*512:(frame+1)*384*512]=mask.ravel()
  for method,angle in [('legacy',None),('expanded',15),('expanded',25),('expanded',35)]:
   ids=group['ids'] if method=='legacy' else np.flatnonzero(eligible&(angles<=angle+1e-12));g=group|{'ids':ids}
   for cap in [.02,.05,.10]:
    name=f'LEGACY_M{int(cap*100):02}' if angle is None else f'EXP_N{angle:02}_M{int(cap*100):02}';st.log('arm_started',name=name,candidates=len(ids));r=arm(st,data,name,[g],max_relative_move=cap);npz=st.path/'artifacts/arms'/name/'proposed/pointmap.npz'
    with np.load(npz) as z:
     xyz=z['xyz'];acc=z['accepted'].copy();moving=np.flatnonzero(acc);distance=abs(xyz[acc]@normal+plane[3]);assert not len(distance) or distance.max()<1e-10
     assert np.array_equal(xyz[~acc],data['xyz'][~acc]);assert np.array_equal(z['target_depth'][acc],safe_depth[acc]);assert np.array_equal(z['rgb'],data['raw_rgb']);assert abs(xyz.shape[0]-589824)==0
     for prev_key,prev_acc in accepted_sets.items():
      if prev_key[0]!=method:continue
      common=acc&prev_acc;assert np.array_equal(xyz[common],common_xyz[prev_key][common])
     common_xyz[(method,angle,cap)]=xyz.copy();accepted_sets[(method,angle,cap)]=acc
     r|={'method':method,'point_normal_threshold_degree':angle,'membership_points':len(ids),'moved_per_frame':[int(np.sum(acc&(data['fid']==i))) for i in range(3)],'outside_legacy_membership_moved':int(np.sum(acc&~originalmask)),'outside_reference_own_source_mask_moved':int(np.sum(acc&~rawmask_union)),'plane_max_residual':float(distance.max()) if len(distance) else None,'fixed_plane':plane.tolist(),'legacy_source':str(h4),'reference_confirmation':confirm}
     masksout=np.zeros(len(acc),bool);masksout[ids]=True
     for camera in range(3):
      sl=slice(camera*384*512,(camera+1)*384*512);im=data['rgb'][camera].copy();hit=acc[sl].reshape(384,512);membership=masksout[sl].reshape(384,512);im[hit]=np.rint(.5*im[hit]+.5*np.array([0,255,80])).astype(np.uint8);im[membership&~hit]=[255,0,255];c.image_write(st.path/f'artifacts/figures/{name}_camera{camera}_membership.png',im)
    c.json_write(npz.parent.parent/'metrics.json',r);results.append(r);st.log('arm_completed',name=name,moved=r['accepted_points'],frames=r['moved_per_frame'])
  for method in ['legacy','expanded']:
   for angle in ([None] if method=='legacy' else [15,25,35]):
    for a,b in [(.02,.05),(.05,.10)]:assert not np.any(accepted_sets[(method,angle,a)]&~accepted_sets[(method,angle,b)])
  for cap in [.02,.05,.10]:
   for a,b in [(15,25),(25,35)]:assert not np.any(accepted_sets[('expanded',a,cap)]&~accepted_sets[('expanded',b,cap)])
  test|={'angle_and_move_acceptance_monotonic':True,'common_accepted_xyz_bitwise_identical_across_all_caps_and_angles':True,'all_accepted_points_on_same_frozen_plane':True,'all_rejected_xyz_bitwise_unchanged':True};assert [c.record(p) for p in sources]==inputrecords
  c.json_write(st.path/'evaluation/technical_checks.json',test);c.json_write(st.path/'evaluation/inputs.json',inputrecords+candidate_inputs+data['inputs']);self_summary=finish_views(st,data,results,baseline,baselinegeo,plane)
  report='# H4e 공유 평면 범위 확장·이동/법선 허용 완화\n\n기존 H4d A4의 공유 월드 평면 하나를 그대로 고정하고 원래 C3a에서 각 군을 독립 시작했다. 평면의 추정·계수·카메라·RGB·점 수는 바꾸지 않았다. 기존 소속 고정 3군은 이동 한도만, 확장 9군은 같은 소속 정의에서 점 법선 각도와 이동 한도를 비교한다. 기존 2% 제한만으로 거절된 점은 15개였으므로 후보 소속 확장 효과를 분리해야 했다.\n\n'
  report+='기존 15°는 후보 평면 간 association 기준이었다. 이번 15/25/35°는 모든 프레임의 개별 7×7 법선과 고정 공유 평면의 각도다. 기존 법선 K-means cluster를 합치는 설정으로 해석하지 않는다. 확정된 camera0/1 원시 NMS 벽 범위에 교차점이 투영되고 참조 깊이 3% 확인을 통과한 점을 모든 프레임에서 재판정한다. 원래 refined mask/cluster 밖도 허용하지만 무한 평면 전체를 대상으로 하지 않는다. 자기 프레임 RGB mask는 필수 조건이 아니며 원래 mask 밖 변화도 별도로 센다.\n\n'
  report+='| 군 | 자기 이동 한도 | 점 법선 허용각 | 소속점 | 이동 frame0/1/2 | 기존 소속 밖 이동 | 벽 두께 변화 | 층 간격 변화 | 보존 조건 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
  for r in results:
   thick=r['fixed_wall']['thickness_p95_p05']/baseline['thickness_p95_p05']-1;gap=r['fixed_wall']['layer_gap_model_units']/baseline['layer_gap_model_units']-1;report+=f"| {r['name']} | {r['max_relative_move']:.0%} | {r['point_normal_threshold_degree']} | {r['membership_points']} | {' / '.join(map(str,r['moved_per_frame']))} | {r['outside_legacy_membership_moved']} | {thick:+.2%} | {gap:+.2%} | {r['preservation_passed']} |\n"
  report+='\n음수는 C3a 대비 두께/해당 지표 감소다. 층 간격은 다른 패치를 가진 source median 차이이며 평면화 자체와 다를 수 있다. 모든 수용점은 같은 평면 위에 있지만 거절·경계·비대상점은 남는다. 소속이 넓어져 기존 RGB non_target ROI의 일부가 움직일 수 있고 이를 고정 ROI별 지표와 마스크로 공개했다. 0/1의 공유 벽에 대한 참조만 있어 frame2는 평가 대상에 포함해도 실제 수용이 없을 수 있다. 물체 경계의 과보정 가능성을 GT 없이 배제하지 않는다.\n\n'
  report+='평면 0.5% fit inlier·15° association·confidence 하위10% 제외·영상8px border·참조 마스크 erosion3px·참조 가림깊이3%·스침각 cos0.2는 이번에 완화하지 않았다. 이동 한도와 법선 소속 gate 외 제약을 명시적으로 유지했다. 각 군에서 가시성 보존 기준 실패 시 retained=A0이며 실제 proposed는 보존한다. GPU/모델 재추론은 없었다.\n\n'
  report+='원래 2%군의 XYZ/accepted bitwise 재현, 이동/각도 완화 시 수용 집합의 단조 증가, 공통 수용점 XYZ 동일, 한 평면 잔차<1e-10, 거절점 bitwise 보존·PLY 왕복·자기 재투영·입력 해시 검사를 통과했다. 실제 정확도/보편적 최적 threshold는 확정하지 않았다.\n\n빠른 PLY: `results/c3a_plane_refinement/ply_review/H4e_*.ply`. `LEGACY`는 기존 소속, `EXP_N35_M05`는 전역 재소속 법선35°·자기 깊이5%다. 12군 모두 원본 픽셀색과 프레임색 PLY 및 initial/proposed/retained를 제공한다.\n'
  st.finish({'decision':'COMPLETED_THRESHOLD_AND_MEMBERSHIP_DIAGNOSTIC','scientific_improvement':False,'technical_checks':test,'arms':results,'baseline_wall':baseline,'baseline_geometry':baselinegeo,'inputs':inputrecords,'fixed_plane':plane.tolist(),'reference_confirmation':confirm,'membership_angle_distribution':c.stats(angles[eligible]),'eligible_before_normal_per_frame':[int(np.sum(eligible&(data['fid']==i))) for i in range(3)],'views':self_summary},report)
  shutil.copy2(st.path/'evaluation/ply_inventory.csv',st.doc/'evaluation/ply_inventory.csv')
  with (DOC/'index.md').open('a') as stream:stream.write(f'| H4e | 완료·전역 재소속/이동·법선 완화 12군 | [{st.run_id}]({st.doc.relative_to(DOC)}/report.md) |\n')
 except Exception as e:st.fail(e);raise

def finish_views(st,data,rows,baseline,baselinegeo,plane):
 review=FAMILY/'ply_review';inventory=[];csvrows=[]
 # Keep the existing H6a fixed A0 zoom range to show the same ROI, axes and source IDs.
 zoom=json.loads((latest('H6a')/'evaluation/metrics.json').read_text())['fixed_zoom'];f=np.load(latest('H2d')/'artifacts/masks/fixed_wall_reference.npz');ids=f['ids'];center=f['center'];normal=f['normal'];basis=np.array([1.,0,0]);basis-=basis@normal*normal;basis/=np.linalg.norm(basis);xlo,xhi=zoom['x_limits'];yl,yh=zoom['signed_distance_limits'];Dref=zoom['Dref'];clipping=[]
 selected=['LEGACY_M02','EXP_N15_M02','EXP_N35_M02','EXP_N15_M05','EXP_N25_M05','EXP_N35_M05','EXP_N15_M10','EXP_N25_M10','EXP_N35_M10'];plots=[]
 for r in rows:
  name=r['name'];out=st.path/'artifacts/arms'/name
  for state in ['initial','proposed','retained']:
   for color in ['pixel_rgb','frame_colors']:
    p=out/state/(color+'.ply');inventory.append({'arm':name,'state':state,'color':color,'resolved_file':str(p.resolve()),**c.record(p)})
    if state=='proposed':
     link=review/f'H4e_{st.run_id}_{name}_{color}.ply';link.symlink_to(os.path.relpath(p,review))
  csvrows.append({'arm':name,'angle':r['point_normal_threshold_degree'],'max_move':r['max_relative_move'],'candidate_count':r['membership_points'],'accepted':r['accepted_points'],'frame0':r['moved_per_frame'][0],'frame1':r['moved_per_frame'][1],'frame2':r['moved_per_frame'][2],'outside_legacy':r['outside_legacy_membership_moved'],'thickness_change':r['fixed_wall']['thickness_p95_p05']/baseline['thickness_p95_p05']-1,'gap_change':r['fixed_wall']['layer_gap_model_units']/baseline['layer_gap_model_units']-1,'preservation_passed':r['preservation_passed']})
  if name not in selected:continue
  xyz=np.load(out/'proposed/pointmap.npz')['xyz'];dist=(xyz[ids]-center)@normal;canvas=np.full((500,800,3),250,np.uint8)
  for tick in np.linspace(yl,yh,5):
   py=int(440-(tick-yl)/(yh-yl)*380);c.cv2.line(canvas,(80,py),(780,py),(225,225,225),1);c.cv2.putText(canvas,f'{tick/Dref:+.4f}',(3,py+5),0,.4,(70,70,70),1)
  clip=[]
  for source in range(3):
   sel=data['fid'][ids]==source;x=((xyz[ids][sel]-center)@basis-xlo)/(xhi-xlo)*680+90;y=440-(dist[sel]-yl)/(yh-yl)*380;good=(x>=80)&(x<790)&(y>=45)&(y<450);canvas[y[good].astype(int),x[good].astype(int)]=c.PALETTE[source];clip.append(int((~good).sum()))
  c.cv2.putText(canvas,name,(85,22),0,.6,(20,20,20),1);c.cv2.putText(canvas,'same H6a fixed ROI/axes | red=frame0 green=frame1',(85,480),0,.45,(30,30,30),1);clipping.append({'arm':name,'clipped_per_frame':clip});c.image_write(st.path/f'artifacts/figures/{name}_zoom.png',canvas);plots.append((name,canvas))
 plots.sort(key=lambda x:selected.index(x[0]));panel=np.full((1500,2400,3),250,np.uint8)
 for ix,(name,im) in enumerate(plots):panel[(ix//3)*500:(ix//3+1)*500,(ix%3)*800:(ix%3+1)*800]=im
 c.image_write(st.path/'artifacts/figures/wall_zoom_grid.png',panel)
 c.json_write(st.path/'evaluation/ply_inventory.json',inventory)
 for filename,values in [('ply_inventory.csv',inventory),('comparisons.csv',csvrows)]:
  with (st.path/'evaluation'/filename).open('w') as stream:
   writer=__import__('csv').DictWriter(stream,fieldnames=values[0].keys());writer.writeheader();writer.writerows(values)
 return {'zoom_frozen_from_H6a':zoom,'clipping':clipping,'ply_inventory_items':len(inventory),'plane_frozen':plane.tolist()}

if __name__=='__main__':run()
