"""G6 fixed wall ROI/plane, common views, acceptance guards and accessible PLY index."""
import run as g
import numpy as np,json,os,csv,cv2,itertools
st=g.Stage('G6')
try:
 data,matches=g.load();b1=g.c.points(data,g.BETA);k1=g.c.corrected_k(data['k'],g.BETA.reshape(3,2));plane=np.load(g.latest('G1')/'artifacts/observations/wall_reference.npz');center=plane['center'];normal=plane['normal'];uv,z,valid=g.c.project(b1,k1[0],data['e'][0],384,512)
 wall=valid&(uv[:,0]>=220)&(uv[:,0]<390)&(uv[:,1]>=5)&(uv[:,1]<65)
 ids=np.flatnonzero(wall);owners=data['fid'][ids];normalizer=float(np.median(data['depth'][0]));basis=np.array([1.,0,0]);basis-=basis@normal*normal;basis/=np.linalg.norm(basis)
 near=np.percentile(b1,5,axis=0);far=np.percentile(b1,95,axis=0);target=(near+far)/2;R0=data['e'][0,:,:3];inv=np.linalg.inv(R0);eye=target+inv@np.array([1.,-.8,-2.])*normalizer;forward=target-eye;forward/=np.linalg.norm(forward);right=np.cross(inv@np.array([0.,1.,0.]),forward);right/=np.linalg.norm(right);down=np.cross(forward,right);rot=np.array([right,down,forward]);external=np.c_[rot,-rot@eye];externalK=np.array([[380.,0,320],[0,380,240],[0,0,1]])
 fixed_scatter_x=((b1[ids]-center)@basis);xlow,xhigh=np.percentile(fixed_scatter_x,[.1,99.9]);ylow,yhigh=-.08*normalizer,.08*normalizer
 def diagnostic(xyz,label,path):
  dist=(xyz[ids]-center)@normal;rows=[];med=[]
  canvas=np.full((480,640,3),250,np.uint8)
  for frame in range(3):
   sel=owners==frame;vals=dist[sel];rows.append({'frame':frame,'fixed_points':int(sel.sum()),'signed_distance':g.c.stats(vals) if len(vals) else {'count':0}})
   if len(vals)>=50:med.append(float(np.median(vals)))
   xx=((xyz[ids][sel]-center)@basis-xlow)/(xhigh-xlow)*600+20;yy=440-(vals-ylow)/(yhigh-ylow)*400;good=(xx>=0)&(xx<640)&(yy>=0)&(yy<480)
   for px,py in zip(xx[good][::3].astype(int),yy[good][::3].astype(int)):canvas[py,px]=g.c.PALETTE[frame]
  cv2.putText(canvas,label,(15,20),0,.5,(20,20,20),1);g.c.image_write(path/'wall_section.png',canvas)
  np.savez_compressed(path/'wall_signed_distances.npz',fixed_observation_ids=ids,frame_id=owners,signed_distance=dist,center=center,normal=normal)
  zz,win,_=g.c.front(xyz,externalK,external,480,640);hit=win>=0;im=np.zeros((480,640,3),np.uint8);im[hit]=data['raw_rgb'][win[hit]];g.c.image_write(path/'external_rgb.png',im);im[hit]=g.c.PALETTE[data['fid'][win[hit]]];g.c.image_write(path/'external_frames.png',im)
  return {'frames':rows,'layer_gap_model_units':max(med)-min(med) if len(med)>=2 else None,'thickness_p95_p05':float(np.percentile(dist,95)-np.percentile(dist,5)),'reference_plane_frozen':True,'evaluation_ids_fixed':True,'plot_clipped_fraction':float(np.mean((dist<ylow)|(dist>yhigh))),'semantic_scope':'RGB camera0 wall rectangle; projection overlap can contain occlusions; not geometric GT'}
 baselinefolder=st.path/'artifacts/baseline';baselinefolder.mkdir();baseline=diagnostic(b1,'C3a B1 fixed wall plane',baselinefolder);basegeo=g.geo(data,matches,g.BETA)
 review=g.ROOT/'results/point_line_depth_refinement/ply_review';review.mkdir(exist_ok=True);rows=[];inventory=[]
 for code in ['G2','G3','G4']:
  parent=g.latest(code);metrics=json.loads((parent/'evaluation/metrics.json').read_text())
  for arm in metrics['arms']:
   name=arm['name'];out=st.path/'artifacts/diagnostics'/f'{code}_{name}';out.mkdir(parents=True);npz=parent/'artifacts/arms'/name/'proposed/pointmap.npz';z=np.load(npz);xyz=z['xyz'];wallmetrics=diagnostic(xyz,code+' '+name,out);v=arm['geometry_proposed']['validation'];before=basegeo['validation'];gain3=(before['relative_3d']['median']-v['relative_3d']['median'])/max(before['relative_3d']['median'],1e-5);gainz=(before['relative_z']['median']-v['relative_z']['median'])/max(before['relative_z']['median'],1e-5)
   pairguard=all((b['relative_3d']['median']-a['relative_3d']['median'])/max(a['relative_3d']['median'],1e-5)<=.01 for a,b in zip(before['pairs'],v['pairs']))
   basic=gain3>=.05 and (before['relative_3d']['median']-v['relative_3d']['median'])>=1e-5 and pairguard and arm['coverage_B1']['passed']
   row={'code':code,'arm':name,'validation_3d':v['relative_3d']['median'],'validation_z':v['relative_z']['median'],'gain_3d_vs_B1':gain3,'gain_z_vs_B1':gainz,'per_pair_3d_guard':pairguard,'numeric_3d_acceptance':basic,'scientific_improvement':False,'support_decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','bound_limited':arm['bound_limited'],'converged':arm['converged'],'coverage_B1':arm['coverage_B1'],'coverage_raw':arm['coverage_raw'],'wall':wallmetrics,'parameters':{'beta':arm['beta'],'depth_scale':arm['depth_scale']},'source':str(npz.parent.relative_to(g.ROOT))};rows.append(row)
   g.c.json_write(out/'metrics.json',row)
   for state in ['initial','proposed','selected','last']:
    for color in ['pixel_rgb','frame_colors']:
     f=parent/'artifacts/arms'/name/state/(color+'.ply');inventory.append({'code':code,'arm':name,'state':state,'color':color,**g.c.record(f)})
     if state=='proposed':
      link=review/f'{code}_{name}_{color}.ply'
      if not link.exists():link.symlink_to(os.path.relpath(f,review))
   # Frozen PLY identity: observations and colors never changed.
   assert np.array_equal(z['frame_id'],data['fid']) and np.array_equal(z['pixel_uv'],data['uv']) and np.array_equal(z['rgb'],data['raw_rgb']) and np.array_equal(z['extrinsics'],data['e'])
   sample=np.linspace(0,len(xyz)-1,2000,dtype=int)
   for camera in range(3):
    mask=data['fid'][sample]==camera;sel=sample[mask];p,zdep,_=g.c.project(xyz[sel],z['intrinsics'][camera],data['e'][camera],384,512);assert abs(p-data['uv'][sel]).max()<1e-5
   figures=st.path/'artifacts/figures';shutil=__import__('shutil');shutil.copy2(out/'wall_section.png',figures/f'{code}_{name}_wall.png');shutil.copy2(out/'external_rgb.png',figures/f'{code}_{name}_external_rgb.png');shutil.copy2(out/'external_frames.png',figures/f'{code}_{name}_external_frames.png')
 # Add convenient links for original C3a and the new-window arms without copying files.
 for color,srcname in [('pixel_rgb','all_rgb.ply'),('frame_colors','all_source.ply')]:
  src=g.BASE/'artifacts/fit/proposed_not_selected'/srcname;link=review/f'B1_C3a_{color}.ply'
  if not link.exists():link.symlink_to(os.path.relpath(src,review))
 for f in (g.latest('G5a')/'artifacts/arms').glob('*/proposed/*.ply'):
  link=review/f'G5a_{f.parent.parent.name}_{f.name}'
  if not link.exists():link.symlink_to(os.path.relpath(f,review))
 (st.path/'evaluation/ply_inventory.csv').parent.mkdir(parents=True,exist_ok=True)
 with (st.path/'evaluation/ply_inventory.csv').open('w') as stream:
  writer=csv.DictWriter(stream,fieldnames=inventory[0].keys(),lineterminator='\n');writer.writeheader();writer.writerows(inventory)
 g.c.json_write(st.path/'evaluation/ply_inventory.json',inventory);g.c.json_write(st.path/'evaluation/wall_baseline.json',baseline)
 report='# G6 점·선·깊이 제약 종합 결과\n\nG0~G6 및 G0a/G5a 실행을 마쳤다. **실행 완료와 효과 검증은 구분한다.** 원본 실내의 점 대응과 선 구조가 적어 모든 효과 판정은 탐색적이다.\n\n'
 report+='주 기준선은 사용자가 육안으로 좋게 관찰한 C3a proposed이며 validation 상대 3D median은 '+str(basegeo['validation']['relative_3d']['median'])+'다.\n\n'
 report+='| 군 | 3D 변화(B1 대비) | Z 변화(B1 대비) | FoV 경계 | 정합 개선 기준 충족 |\n| --- | --- | --- | --- | --- |\n'
 for r in rows:report+=f"| {r['code']} {r['arm']} | {r['gain_3d_vs_B1']:+.2%} | {r['gain_z_vs_B1']:+.2%} | {r['bound_limited']} | {r['numeric_3d_acceptance']} |\n"
 report+='\n변화의 양수는 오차 감소다. 선 제약 군은 허용 FoV 경계에 도달했고, 이 소수 선·가중치에서 추가 제약의 일관된 우위는 확인하지 못했다. 이는 PLY 전체 표면의 육안 품질이 악화됐다는 판정이 아니다. 제안값을 모두 보존했으므로 같은 시점·단면에서 직접 확인할 수 있다.\n\n'
 report+='G4는 공식 `Ruicheng/moge-2-vitl` 모델을 동일 RGB 3장에 각각 추론한 prior를 사용했다. GT가 아니며 카메라별 독립 scale 정렬은 하지 않았다. G5는 β=1 초기값 8군과 가중치 민감도 12군을 실행했다. G5a는 고정 100/110/120 구간을 새로 공동 추론하고 8군을 비교했다. 새 구간의 벽 ROI는 보이지 않아 벽 정합은 미평가다.\n\n'
 report+='PLY 빠른 비교 디렉토리: `results/point_line_depth_refinement/ply_review/`. 이 경로는 원본 결과를 가리키는 상대 symlink이며 각 파일의 실제 경로·SHA256은 evaluation/ply_inventory.json에 기록했다. RGB·출처색과 initial/proposed/selected/last를 구분한다.\n\n'
 report+='G0a에서 numerical three-point Jacobian을 쓰는 구현 변경과 analytic 투영 Jacobian 검증을 기록했다. 외부 prior의 fixed 4px stride는 scale 동결 후 계산량을 제한하는 변경이다. GT 평가·자유 깊이맵·자세 최적화·융합·연속 SLAM은 실행하지 않았다.\n'
 st.finish({'decision':'COMPLETED_EFFECT_NOT_ESTABLISHED','scientific_improvement':False,'baseline_geometry':basegeo,'baseline_wall':baseline,'comparisons':rows,'ply_files_indexed':len(inventory),'review_directory':str(review),'all_original_observation_ids_rgb_poses_preserved':True},report)
 # CSV is also copied to tracked doc directory.
 __import__('shutil').copy2(st.path/'evaluation/ply_inventory.csv',st.doc/'evaluation/ply_inventory.csv')
 (g.ROOT/'docs/experiments/point_line_depth_refinement/summary.md').write_text(report+'\n\n[전체 지표·보고서]('+str(st.doc.relative_to(g.ROOT/'docs/experiments/point_line_depth_refinement'))+'/report.md)\n')
except Exception as e:st.fail(e);raise
