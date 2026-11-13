"""SAM-driven complete wall membership; unbounded positive ray-plane correction."""
from base import *
from geometry import depth_gate,update
from evaluate import arm,wall_metrics,match_metrics

def mask_transfer(data,points,valid,refs):
 votes=np.zeros(len(points),np.uint8)
 for i,mask in sorted(refs.items()):
  uv,z,inside=c.project(points,data['k'][i],data['e'][i],384,512);ids=np.flatnonzero(valid&inside);xy=np.rint(uv[ids]).astype(int);hit=mask[xy[:,1],xy[:,0]];votes[ids[hit]]+=1
 return votes

def controls():
 D=np.ones(2);q=np.array([[0.,0,1],[0,0,1]]);C=np.zeros_like(q);p=np.array([0.,0,1,-3.]);t,a,r=depth_gate(D,q,C,p,None,1e-8);assert a.all() and np.all(t==3)
 assert not depth_gate(D,q,C,p,.20,1e-8)[1].any()
 assert not depth_gate(D,q,C,np.array([1.,0,0,-3]),None,1e-8)[1].any()
 assert not depth_gate(D,q,C,-np.array([0.,0,-1,-3]),None,1e-8)[1].any()
 return {'unbounded_200pct_move_accepted':True,'20pct_gate_rejects_same_move':True,'parallel_rejected':True,'negative_depth_rejected':True}

def run():
 os.environ['H_OBSERVATION_STAGE']='H2d';h1,h2,h4,he=[latest(cod) for cod in ['H1','H2d','H4d','H4e']]
 st=Stage('H4f',parents=[h1,h2,h4,he],extra={'max_relative_move':'per arm: 0.05/0.20/None (unbounded)','normal_membership_gate':None,'confidence_gate':False,'source_border_exclusion_px':0,'source_mask_erosion_px':0,'reference_depth_gate':None,'minimum_ray_cosine':'1e-8 for SAM arms; old 0.2 for H4e control','primary_SAM_masks':{'camera0':[0],'camera1':[1],'camera2':'mask0 intersect no-depth shared-plane 2D transfer'},'refit_plane':False,'plan':c.record(Path(__file__).parent/'H4f/plan.md'),'execution_context':'host CPU; no CUDA or model inference'})
 try:
  shutil.copy2(Path(__file__).parent/'H4f/plan.md',st.path/'artifacts/source/H4f_plan.md');test=controls();data=load();group=json.loads((h4/'artifacts/associations/refined/groups.json').read_text())[0];p=np.array(group['fit']['plane']);N=len(data['xyz']);size=384*512;inputs=[c.record(h4/'artifacts/associations/refined/groups.json')]
  masks=[];nms=[]
  for i in range(3):
   mf=h1/f'artifacts/masks/camera_{i}_masks.npz';raw=np.load(mf)['masks'].copy();masks.append(raw);inputs.append(c.record(mf));npth=h2/f'artifacts/masks/camera_{i}_mask_nms.json';nm=json.loads(npth.read_text());kept=[r['original_index'] for r in nm['decisions'] if r['retained']];nms.append(raw[kept].any(0));inputs.append(c.record(npth))
  union=np.array([m.any(0) for m in masks]);primary=np.zeros((3,384,512),bool);primary[0]=masks[0][0];primary[1]=masks[1][1]
  target,positive,reason=depth_gate(data['d0'],data['q'],data['center_points'],p,None,1e-8);safe=np.where(np.isfinite(target),target,data['d0']);points=data['center_points']+safe[:,None]*data['q'];votes=mask_transfer(data,points,positive,{0:primary[0],1:primary[1]});primary[2]=masks[2][0]&(votes[2*size:3*size].reshape(384,512)>0)
  oldf=he/'artifacts/membership/frozen_membership.npz';old=np.load(oldf);oldeligible=old['eligible_before_normal'];angles=old['normal_angle_degree'];control=oldeligible&(angles<=35+1e-12);inputs.append(c.record(oldf));testxyz=update(data,[group|{'ids':np.flatnonzero(control)}],max_relative_move=.05)
  with np.load(he/'artifacts/arms/EXP_N35_M05/proposed/pointmap.npz') as z:assert np.array_equal(testxyz[0],z['xyz']) and np.array_equal(testxyz[1],z['accepted']);oldaccepted=z['accepted'].copy()
  test['H4e_control_xyz_accepted_bitwise']=True
  md=st.path/'artifacts/masks';md.mkdir(parents=True);roi=np.zeros((3,384,512),bool);roi[:,:96,154:358]=True;np.savez_compressed(md/'frozen_sam_membership.npz',primary=primary,nms=np.array(nms),all_masks_union=union,reference_votes=votes,valid_positive_intersection=positive.reshape(3,384,512),target_depth=safe.reshape(3,384,512),top_middle_roi=roi,plane=p,original_observation_id=data['ids'])
  # Diagnose every H1 mask, not just the winning NMS mask.
  diagnostics=[]
  for i,mm in enumerate(masks):
   for j,m in enumerate(mm):
    ids=np.flatnonzero(m.ravel())+i*size;focus=ids[roi.ravel()[ids]];pos=positive[ids];delta=abs(safe[ids]-data['d0'][ids])/data['d0'][ids];fpos=focus[positive[focus]];row={'camera':i,'H1_mask':j,'pixels':len(ids),'positive_intersections':int(pos.sum()),'H4e_accepted':int(oldaccepted[ids].sum()),'H4e_valid_normal_border':int(old['valid_normal_border'][ids].sum()),'H4e_reference_footprint':int(old['reference_footprint'][ids].sum()),'H4e_angle_le35':int((angles[ids]<=35).sum()),'move_above_5pct':int(np.sum(pos&(delta>.05))),'move_above_20pct':int(np.sum(pos&(delta>.2))),'move_above_100pct':int(np.sum(pos&(delta>1))),'relative_move_if_positive':c.stats(delta[pos]),'top_middle_pixels':len(focus),'top_middle_positive':len(fpos),'top_middle_H4e_accepted':int(oldaccepted[focus].sum()),'top_middle_relative_move':c.stats(abs(safe[fpos]-data['d0'][fpos])/data['d0'][fpos])};diagnostics.append(row)
  c.json_write(st.path/'evaluation/H1_mask_selection_audit.json',diagnostics)
  baseline=wall_metrics(data,data['xyz'],st.path/'artifacts/baseline/sections');basegeo=match_metrics(data,data['xyz'],np.zeros(N,bool));rows=[];cache={};specs=[('E35_M05_CONTROL',control,.05,.2),('SAM_NMS_UNCAPPED',np.array(nms).ravel(),None,1e-8),('SAM_SHARED_M05',primary.ravel(),.05,1e-8),('SAM_SHARED_M20',primary.ravel(),.20,1e-8),('SAM_SHARED_UNCAPPED',primary.ravel(),None,1e-8),('SAM_ALL_MASKS_UNCAPPED',union.ravel(),None,1e-8)]
  for name,member,cap,ray in specs:
   st.log('arm_started',name=name,members=int(member.sum()),max_move=cap);ids=np.flatnonzero(member);r=arm(st,data,name,[group|{'ids':ids}],max_relative_move=cap,minimum_ray_cosine=ray);out=st.path/'artifacts/arms'/name
   with np.load(out/'proposed/pointmap.npz') as z:
    xyz=z['xyz'];acc=z['accepted'].copy();delta=abs(z['depth']-data['d0'])/data['d0'];res=abs(xyz[acc]@p[:3]+p[3]);assert res.max()<1e-9;assert np.array_equal(xyz[~acc],data['xyz'][~acc]);assert not np.any(acc&~member)
    if cap is None:assert np.array_equal(acc,member&positive)
    if name=='E35_M05_CONTROL':assert np.array_equal(xyz,testxyz[0]) and np.array_equal(acc,oldaccepted)
    cache[name]=(acc,xyz.copy());byframe=[]
    for i in range(3):
     f=data['fid']==i;fm=acc&f;fr=roi.ravel()&f;focus=fr&member;hit=focus&acc;byframe.append({'frame':i,'members':int(np.sum(member&f)),'moved':int(fm.sum()),'new_vs_H4e':int(np.sum(fm&~oldaccepted)),'relative_move':c.stats(delta[fm]),'top_middle_selected':int(focus.sum()),'top_middle_moved':int(hit.sum()),'top_middle_relative_move':c.stats(delta[hit]),'top_middle_source_Z_before':c.stats(data['d0'][hit]),'top_middle_source_Z_after':c.stats(z['depth'][hit])})
     image=data['rgb'][i].copy();mask=acc.reshape(3,384,512)[i];mem=member.reshape(3,384,512)[i];image[mask]=np.rint(.5*image[mask]+.5*np.array([0,255,100])).astype(np.uint8);image[mem&~mask]=[255,0,255];c.cv2.rectangle(image,(154,0),(357,95),(255,120,0),1);c.image_write(st.path/f'artifacts/figures/{name}_camera{i}_membership.png',image)
    r|={'membership_points':len(ids),'per_frame':byframe,'plane_max_residual':float(res.max()),'above_5pct':int(np.sum(acc&(delta>.05))),'above_20pct':int(np.sum(acc&(delta>.2))),'above_100pct':int(np.sum(acc&(delta>1))),'fixed_plane':p.tolist(),'no_point_normal_confidence_border_or_reference_depth_gate':name!='E35_M05_CONTROL','moved_total':int(acc.sum()),'numerical_reason_counts':{str(j):int(np.sum(member&(reason==j))) for j in range(5)}}
   c.json_write(out/'metrics.json',r);rows.append(r);st.log('arm_completed',name=name,accepted=r['moved_total'],frames=[q['moved'] for q in byframe],max_move=r['relative_depth_move'].get('max'),retained=r['retained_state'])
  for a,b in [('SAM_SHARED_M05','SAM_SHARED_M20'),('SAM_SHARED_M20','SAM_SHARED_UNCAPPED')]:assert not np.any(cache[a][0]&~cache[b][0]);common=cache[a][0]&cache[b][0];assert np.array_equal(cache[a][1][common],cache[b][1][common])
  test|={'5_20_unbounded_monotonic':True,'common_accepted_xyz_bitwise':True,'no_hidden_distance_or_normal_gate_in_SAM_uncapped':True,'all_uncapped_positive_selected_points_accepted':True,'same_frozen_plane_and_all_rejected_xyz_unchanged':True};c.json_write(st.path/'evaluation/technical_checks.json',test);c.json_write(st.path/'evaluation/inputs.json',inputs+data['inputs']);views=render_views(st,data,rows,cache,roi,p)
  report='# H4f SAM 마스크 전체·이동 상한 없는 공유 평면 재투영\n\n사용자 지시에 따라 H1 SAM 벽 마스크를 주 소속 근거로 사용하고 큰 깊이 오류도 고정 H4d A4 월드 평면으로 hard 재투영했다. 원래 589,824점·RGB·ID·카메라와 평면 계수는 보존했다. 점별 법선·confidence·영상 border·mask erosion·원본/참조 depth 차이 gate를 제거했다. uncapped는 100% 초과 변화도 허용하며 finite·양의 교차 Z·수치 평행 방지 cos≥1e-8만 남겼다. 평면을 바꾸거나 gradient 학습을 한 것은 아니다.\n\n'
  report+='주 SAM_SHARED 군은 camera0 mask0, camera1의 더 넓은 mask1을 전체 사용한다. camera1 mask1은 H2d에서 NMS로 제외됐던 H1 원본이다. camera2는 mask0 중 이 평면의 교차점이 확인된 camera0/1 벽 범위에 투영되는 부분만 같은 벽에 연결한다. 이때 참조 깊이는 확인하지 않는다. camera0/1은 그 전파 조건도 없이 자기 SAM 마스크 전체를 대상으로 한다. SAM_ALL_MASKS는 책상/다른 면까지 포함된 모든 wall mask union을 한 평면으로 강제하는 별도 stress 비교다. 마스크를 수동 수정하거나 모델을 재추론하지 않았다.\n\n'
  report+='| 군 | 소속 | 이동 frame0/1/2 | 최대 자기 깊이 변화 | 20% 초과 이동 | 고정 벽 두께 변화 | 가시성 포함 보존 | retained |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n'
  for r in rows:report+=f"| {r['name']} | {r['membership_points']} | {' / '.join(str(v['moved']) for v in r['per_frame'])} | {r['relative_depth_move']['max']:.2%} | {r['above_20pct']} | {r['fixed_wall']['thickness_p95_p05']/baseline['thickness_p95_p05']-1:+.2%} | {r['preservation_passed']} | {r['retained_state']} |\n"
  report+='\n최대 이동은 원본 자기 카메라 Z-depth 대비 변화이며 world 거리나 오차의 정답이 아니다. selected/retained가 A0로 돌아가도 요청한 큰 이동의 실제 결과는 각 군 **proposed/**에 보존한다. 색과 점 수/카메라 불변은 가시성 조건과 따로 지표에 있다.\n\n'
  report+='top-middle은 모든 camera의 처리좌표 x=[154,358), y=[0,96)와 자기 SAM 마스크 교집합으로 보정 전에 고정했다. 번호 혼동을 피하도록 camera0/1 모두의 before/after 깊이·이동량·H4e 미수용을 기록했다. RGB의 순수 벽 정답 annotation은 아니다. 원래 H1 mask별 audit에 NMS·법선·유효성·참조 범위·이동량의 제외를 따로 센다.\n\n'
  main=next(r for r in rows if r['name']=='SAM_SHARED_UNCAPPED')
  for q in main['per_frame']:report+=f"- camera{q['frame']}: top-middle 선택 {q['top_middle_selected']} / 이동 {q['top_middle_moved']}, 상대 깊이 이동 최대 {q['top_middle_relative_move'].get('max',0):.2%}.\n"
  report+='\n평면은 하나로 고정하고 각 점은 자기 카메라 광선을 따라 그 평면까지 이동한다. 거절·비소속 XYZ bitwise, 원본 RGB/ID/점 수, 자기 투영, 이전 H4e control bitwise, 5⊆20⊆uncapped, 공통점 XYZ 동일성 검사를 통과했다. 가시성·프레임 간 matching은 실제 큰 이동의 영향을 별도로 기록했다. SAM wall이라는 이름만으로 같은 벽·완전한 평면임이 증명되는 것은 아니므로 모든 mask 강제군을 주 군과 섞지 않는다. GT 정확도 개선은 미평가다.\n\n'
  report+='주 실험 PLY: `artifacts/arms/SAM_SHARED_UNCAPPED/proposed/{pixel_rgb,frame_colors}.ply`. 비교 편의를 위해 실제 경로·hash를 inventory와 `results/c3a_plane_refinement/ply_review/H4f_*.ply`에 제공한다. 확대 단면·같은 크기 카메라 비교·마스크·top-middle crop을 저장했다.\n'
  st.finish({'decision':'COMPLETED_SAM_FULL_MEMBERSHIP_UNCAPPED_DIAGNOSTIC','scientific_improvement':False,'arms':rows,'baseline_wall':baseline,'baseline_geometry':basegeo,'technical_checks':test,'H1_mask_audit':diagnostics,'inputs':inputs,'plane':p.tolist(),'views':views,'primary_arm':'SAM_SHARED_UNCAPPED','stress_arm':'SAM_ALL_MASKS_UNCAPPED'},report)
  shutil.copy2(st.path/'evaluation/ply_inventory.csv',st.doc/'evaluation/ply_inventory.csv')
  with (DOC/'index.md').open('a') as f:f.write(f'| H4f | 완료·SAM 전체/무제한 이동 6군 | [{st.run_id}]({st.doc.relative_to(DOC)}/report.md) |\n')
 except Exception as e:st.fail(e);raise

def render_views(st,data,rows,cache,roi,plane):
 import csv
 review=FAMILY/'ply_review';inventory=[];names=['E35_M05_CONTROL','SAM_SHARED_M05','SAM_SHARED_M20','SAM_SHARED_UNCAPPED','SAM_ALL_MASKS_UNCAPPED'];zoom=json.loads((latest('H6a')/'evaluation/metrics.json').read_text())['fixed_zoom'];rf=np.load(latest('H2d')/'artifacts/masks/fixed_wall_reference.npz');ids=rf['ids'];center=rf['center'];normal=rf['normal'];basis=np.array([1.,0,0]);basis-=basis@normal*normal;basis/=np.linalg.norm(basis);xl,xh=zoom['x_limits'];yl,yh=zoom['signed_distance_limits'];plots=[];clips=[]
 for r in rows:
  name=r['name'];out=st.path/'artifacts/arms'/name
  for state in ['initial','proposed','retained']:
   for color in ['pixel_rgb','frame_colors']:
    path=out/state/(color+'.ply');inventory.append({'arm':name,'state':state,'color':color,'resolved_file':str(path.resolve()),**c.record(path)})
    if state=='proposed':(review/f'H4f_{st.run_id}_{name}_{color}.ply').symlink_to(os.path.relpath(path,review))
  if name not in names:continue
  xyz=cache[name][1];dist=(xyz[ids]-center)@normal;im=np.full((500,800,3),250,np.uint8);cl=[]
  for tick in np.linspace(yl,yh,5):
   y=int(440-(tick-yl)/(yh-yl)*380);c.cv2.line(im,(80,y),(780,y),(225,225,225),1)
  for source in range(3):
   sel=data['fid'][ids]==source;x=((xyz[ids][sel]-center)@basis-xl)/(xh-xl)*680+90;y=440-(dist[sel]-yl)/(yh-yl)*380;good=(x>=80)&(x<790)&(y>=45)&(y<450);im[y[good].astype(int),x[good].astype(int)]=c.PALETTE[source];cl.append(int((~good).sum()))
  c.cv2.putText(im,name,(85,23),0,.55,(20,20,20),1);c.cv2.putText(im,'same H6a A0 ROI/axes; red=frame0 green=frame1',(85,480),0,.43,(30,30,30),1);c.image_write(st.path/f'artifacts/figures/{name}_zoom.png',im);plots.append((name,im));clips.append({'arm':name,'clipped_per_frame':cl})
 plots.sort(key=lambda q:names.index(q[0]));canvas=np.full((1000,2400,3),250,np.uint8)
 for ix,(name,im) in enumerate(plots):canvas[(ix//3)*500:(ix//3+1)*500,(ix%3)*800:(ix%3+1)*800]=im
 c.image_write(st.path/'artifacts/figures/wall_zoom_comparison.png',canvas)
 for camera in range(3):
  cells=[data['rgb'][camera]];titles=['original same 512x384'];crops=[]
  for name in names:
   folder=st.path/'artifacts/arms'/name/'projections';im=c.cv2.imread(str(folder/f'camera_{camera}_rgb.png'))[...,::-1];cells.append(im);titles.append(name);crop=im[:96,154:358].copy();c.image_write(st.path/f'artifacts/figures/{name}_camera{camera}_top_middle.png',crop);crops.append(crop)
  c.panel(st.path/f'artifacts/figures/camera{camera}_comparison.png',[cells],titles)
  # All crops use their native pixel grid; no upscaling.
  c.panel(st.path/f'artifacts/figures/camera{camera}_top_middle_comparison.png',[[data['rgb'][camera,:96,154:358],*crops]],titles)
 with (st.path/'evaluation/ply_inventory.csv').open('w') as f:writer=csv.DictWriter(f,fieldnames=inventory[0].keys());writer.writeheader();writer.writerows(inventory)
 c.json_write(st.path/'evaluation/ply_inventory.json',inventory)
 return {'fixed_H6a_zoom':zoom,'clips':clips,'ply_inventory_items':len(inventory),'top_middle_xyxy':[154,0,358,96]}

if __name__=='__main__':run()
