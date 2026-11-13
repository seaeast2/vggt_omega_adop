"""H6 fixed comparisons, PLY inventory, masks, sections and complete invariant audit."""
from base import *
from evaluate import match_metrics,wall_metrics,visibility,external
import csv

def relative_change(new,old):return float((new-old)/old) if old is not None and abs(old)>1e-12 else None

def run():
 parents=[latest(x) for x in ['H0a','H1','H2c','H2d','H3c','H4c','H5c','H3d','H4d','H5d']];st=Stage('H6',parents,extra={'authoritative_primary':'H3c/H4c/H5c strict track split, overlap exclusion','authoritative_supplement':'H3d/H4d/H5d strict track split + mask NMS','legacy_runs':'H2/H2b ten mixed known tile tracks; original matching-validation tracks always excluded; c/d results supersede split for final comparison'})
 try:
  data=load();basegeo=match_metrics(data,data['xyz'],np.zeros(len(data['xyz']),bool));basewall=wall_metrics(data,data['xyz'],st.path/'artifacts/baseline/sections');basevis=visibility(data,data['xyz']);external(data,data['xyz'],st.path/'artifacts/baseline/sections')
  review=FAMILY/'ply_review';review.mkdir(exist_ok=True);inventory=[];results=[];allarms=[];audits=[]
  for code in ['H3','H4','H5','H3b','H4b','H5b','H3c','H4c','H5c','H3d','H4d','H5d']:
   parent=latest(code);metrics=json.loads((parent/'evaluation/metrics.json').read_text());suffix=code[-1] if code[-1].isalpha() else '';os.environ['H_OBSERVATION_STAGE']='H2'+suffix
   for row in metrics['arms']:
    name=row['name'];out=parent/'artifacts/arms'/name;npz=out/'proposed/pointmap.npz'
    with np.load(npz) as z:
     xyz=z['xyz'];accepted=z['accepted'];n=len(xyz)
     assert n==589824 and xyz.shape==data['xyz'].shape
     for key,target in [('observation_id','ids'),('rgb','raw_rgb'),('frame_id','fid'),('pixel_uv','uv'),('intrinsics','k'),('extrinsics','e')]:assert np.array_equal(z[key],data[target]),(code,name,key)
     assert np.array_equal(xyz[~accepted],data['xyz'][~accepted]);relative=np.zeros(n)
     for i in range(3):
      select=data['fid']==i;uv,Z,_=c.project(xyz[select],data['k'][i],data['e'][i],384,512);assert abs(uv-data['uv'][select]).max()<1e-5;relative[select]=abs(Z-data['d0'][select])/data['d0'][select]
     assert relative.max()<=.02+1e-12
     # Independent PLY header/data verification, including RGB and frame source palette.
     dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('r','u1'),('g','u1'),('b','u1'),('owner','<i2'),('n','<u4'),('bits','u1')])
     for color in ['pixel_rgb','frame_colors']:
      with (out/'proposed'/(color+'.ply')).open('rb') as stream:
       header=[]
       while True:
        line=stream.readline();header.append(line)
        if line==b'end_header\n':break
        assert line
       assert f'element vertex {n}\n'.encode() in header;ply=np.fromfile(stream,dtype)
      assert len(ply)==n;assert np.array_equal(np.c_[ply['x'],ply['y'],ply['z']],xyz);colors=np.c_[ply['r'],ply['g'],ply['b']];assert np.array_equal(colors,data['raw_rgb'] if color=='pixel_rgb' else c.PALETTE[data['fid']])
     if code in ['H3c','H4c','H5c','H3d','H4d','H5d']:
      for i in range(3):
       mask=accepted.reshape(3,384,512)[i];overlay=data['rgb'][i].copy();overlay[mask]=np.rint(.5*overlay[mask]+.5*np.array([0,255,100])).astype(np.uint8);c.image_write(st.path/f'artifacts/figures/{code}_{name}_camera{i}_accepted.png',overlay)
     audit={'code':code,'arm':name,'point_count':n,'all_arrays_and_ply_verified':True,'rejected_xyz_bitwise_unchanged':True,'max_relative_depth_move':float(relative.max()),'same_as_A0':bool(np.array_equal(xyz,data['xyz']))};audits.append(audit)
    validation=row['geometry']['validation']['all'];bv=basegeo['validation']['all'];gain3=relative_change(validation['relative_3d'].get('median'),bv['relative_3d'].get('median'));gainpx=relative_change(validation['reprojection_pixel'].get('median'),bv['reprojection_pixel'].get('median'));gap=relative_change(row['fixed_wall']['layer_gap_model_units'],basewall['layer_gap_model_units']);thick=relative_change(row['fixed_wall']['thickness_p95_p05'],basewall['thickness_p95_p05'])
    final=code in ['H3c','H4c','H5c','H3d','H4d','H5d'];r={'code':code,'arm':name,'scope':'final_primary' if suffix=='c' else ('final_mask_NMS_supplement' if suffix=='d' else 'legacy_split_diagnostic'),'valid_planes':row['valid_planes'],'shared_planes':row['shared_planes'],'accepted_points':row['accepted_points'],'changed_points':row['changed_points'],'wall_layer_gap':row['fixed_wall']['layer_gap_model_units'],'wall_thickness':row['fixed_wall']['thickness_p95_p05'],'wall_gap_change':gap,'wall_thickness_change':thick,'validation_relative_3d_median':validation['relative_3d'].get('median'),'validation_3d_error_change':gain3,'validation_reprojection_pixel_median':validation['reprojection_pixel'].get('median'),'validation_reprojection_error_change':gainpx,'validation_corrected_matches':row['geometry']['validation']['corrected']['matches'],'planar_cleanup_threshold_passed':gap is not None and gap<=-.2 and thick<=-.2,'preservation_passed':row['preservation_passed'],'retained_state':row['retained_state'],'validation_tradeoff':(gain3 is not None and gain3>.01) or (gainpx is not None and gainpx>.01),'scientific_improvement':False,'actual_proposal_directory':str((out/'proposed').relative_to(ROOT)),'decision':row['decision']};results.append(r);allarms.append((code,name,out,row))
    for state in ['initial','proposed','retained']:
     for color in ['pixel_rgb','frame_colors']:
      p=out/state/(color+'.ply');item={'code':code,'arm':name,'state':state,'color':color,'directory':str(p.parent),'resolved_file':str(p.resolve()),**c.record(p)};inventory.append(item)
      if state=='proposed':
       link=review/f'{code}_{name}_{color}.ply'
       if not link.is_symlink():link.symlink_to(os.path.relpath(p,review))
  for color in ['pixel_rgb','frame_colors']:
   p=latest('H0a')/'artifacts/baseline/A0_C3a'/(color+'.ply');link=review/f'A0_C3a_{color}.ply'
   if not link.is_symlink():link.symlink_to(os.path.relpath(p,review))
   inventory.append({'code':'H0a','arm':'A0_C3a','state':'initial','color':color,'directory':str(p.parent),'resolved_file':str(p.resolve()),**c.record(p)})
  # Fixed pixels, same native scale, same point renderer; original is the frozen model input.
  finals=[(code,name,out,row) for code,name,out,row in allarms if code in ['H3d','H4d','H5d']]
  for camera in range(3):
   imgs=[data['rgb'][camera],c.cv2.imread(str(latest('H0a')/f'artifacts/projections/A0_C3a/camera_{camera}_rgb.png'))[...,::-1]];titles=['original 512x384','C3a A0']
   for code,name,out,row in finals:
    if name not in ['A2_FRAME_REFINED','A3_SHARED_RAWMASK','A4_SHARED_REFINED','A5_SHARED_SOFT']:continue
    imgs.append(c.cv2.imread(str(out/f'projections/camera_{camera}_rgb.png'))[...,::-1]);titles.append(code+' '+name.split('_')[0])
   c.panel(st.path/f'artifacts/figures/camera_{camera}_final_comparison.png',[imgs],titles)
  sec=[c.cv2.imread(str(st.path/'artifacts/baseline/sections/wall_section.png'))[...,::-1]];title=['C3a A0']
  for code,name,out,row in finals:
   if name not in ['A2_FRAME_REFINED','A3_SHARED_RAWMASK','A4_SHARED_REFINED','A5_SHARED_SOFT']:continue
   sec.append(c.cv2.imread(str(out/'sections/wall_section.png'))[...,::-1]);title.append(code+' '+name.split('_')[0])
  c.panel(st.path/'artifacts/figures/wall_sections_final_comparison.png',[sec],title)
  # Same fixed ROI IDs on common image geometry; A4/A6 intersection is explicitly empty when unsupported.
  os.environ['H_OBSERVATION_STAGE']='H2d';h4=latest('H4d');a4=np.load(h4/'artifacts/arms/A4_SHARED_REFINED/proposed/pointmap.npz');a6=np.load(h4/'artifacts/arms/A6_GEOMETRY_ONLY/proposed/pointmap.npz');inter=a4['accepted']&a6['accepted'];intersection={'A4_A6_accepted_intersection_count':int(inter.sum()),'evaluated':bool(inter.any()),'reason':'NO_GEOMETRY_ONLY_SHARED_PLANE' if not inter.any() else 'fixed A0 observation intersection'}
  c.json_write(st.path/'evaluation/fixed_roi_intersection.json',intersection)
  # Stage sources/masks must remain frozen; hash every listed artifact, including actual output files.
  integrity=[]
  for parent in parents:
   manifest=json.loads((parent/'manifest.json').read_text());assert manifest['status']=='completed'
   for rec in manifest.get('artifacts',[]):
    p=Path(rec['path']);assert p.exists(),str(p);assert c.record(p)['sha256']==rec['sha256'],str(p)
   integrity.append({'stage':parent.name,'files_verified':len(manifest.get('artifacts',[]))})
  for code in ['H2c','H2d']:
   z=json.loads((latest(code)/'artifacts/masks/track_split_audit.json').read_text());assert z['contract_passed'] and not z['mixed_after']
  for suffix in ['c','d']:
   hard=np.load(latest('H4'+suffix)/'artifacts/arms/A4_SHARED_REFINED/proposed/pointmap.npz');soft=np.load(latest('H5'+suffix)/'artifacts/arms/A5_SHARED_SOFT/proposed/pointmap.npz');assert np.array_equal(hard['accepted'],soft['accepted']) and np.array_equal(hard['target_depth'],soft['target_depth'])
  c.json_write(st.path/'evaluation/ply_inventory.json',inventory);c.json_write(st.path/'evaluation/array_ply_audit.json',audits)
  with (st.path/'evaluation/ply_inventory.csv').open('w') as stream:
   writer=csv.DictWriter(stream,fieldnames=inventory[0].keys());writer.writeheader();writer.writerows(inventory)
  timings=[]
  for code in ['H0a','H1','H2','H2b','H2c','H2d','H3c','H4c','H5c','H3d','H4d','H5d']:
   p=latest(code);v=json.loads((p/'evaluation/metrics.json').read_text());timings.append({'code':code,'elapsed_seconds':v['elapsed_seconds'],'process_peak_rss_mib':v['process_peak_rss_mib'],'details':v.get('timing_seconds',{}),'stage_bytes':sum(x.stat().st_size for x in p.rglob('*') if x.is_file())})
  # Record literal setup commands and immutable model revision from HF cache metadata.
  metadata=ROOT/'checkpoints/grounding-dino-tiny/.cache/huggingface/download/model.safetensors.metadata';revision=metadata.read_text().splitlines()[0] if metadata.exists() else 'unavailable'
  setup={'commands':['.venvs/p2a/bin/python -m pip install transformers==4.57.1','git clone --depth 1 https://github.com/facebookresearch/segment-anything.git thirdparty/segment-anything','curl -L --fail --retry 3 -o checkpoints/sam/sam_vit_h_4b8939.pth https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth','huggingface_hub.snapshot_download(IDEA-Research/grounding-dino-tiny, local_dir=checkpoints/grounding-dino-tiny)'],'grounding_dino_hf_commit':revision,'setup_download_time_instrumented':False,'segmentation_model_loading_and_inference_timed':True,'model_sources':['https://huggingface.co/IDEA-Research/grounding-dino-tiny','https://github.com/facebookresearch/segment-anything'],'cuda_execution':'outside sandbox host RTX5060, H1','missing_evidence':['network download / package installation duration not separately instrumented','GT RGB-D/pose alignment not validated for H; no GT accuracy claim','No human semantic mask annotation; automatic mask errors not an accuracy score']};c.json_write(st.path/'evaluation/setup_provenance.json',setup)
  report='# H6 C3a 기준 영상 분할·평면 보정 종합 결과\n\nH0~H6 실행과 보조 검증을 완료했다. **실행 완료와 정확도 개선 입증을 구분한다.** C3a 실제 FoV proposed를 고정하고 589,824점의 ID·순서·픽셀색·K·pose를 보존했다. 점은 자기 픽셀 광선의 Z 방향으로만 최대 2% 이동한다.\n\n'
  report+='H0의 합성 지원 오류는 H0a로 보완했다. H2/H2b의 알려진 track 45개 중 10개가 타일 경계로 양쪽 split에 걸린 것을 추가 audit에서 발견했다. 원래 보류 matching track은 모든 실행에서 fit 제외였지만, 전체 track 분리 계약을 만족하지 않아 **H2c(기본)/H2d(NMS)에서 track 전체 holdout으로 수정하고 H3c~H5c / H3d~H5d를 재실행**했다. 최종 두 split은 mixed=0이다. 기존 결과는 비교용 이력으로 보존한다.\n\n'
  report+='기본 마스크는 camera0/1에서 겹쳐 모호한 벽 지지가 대부분 제외된다. 기본 공유군은 연결 조건을 통과하지 못했다. 보조 NMS는 SAM predicted-IoU 높은 후보부터 mask IoU>0.5 중복을 제거하며 원본 H1 마스크를 수정하지 않는다. 최종 NMS 공유군은 camera0/1의 벽 하나를 연결했다. camera2를 같은 공유 벽의 지지로 주장하지 않는다.\n\n'
  report+='| 최종 군 | 공유 평면 | 수용점 | 고정 벽 층 간격 변화 | 고정 벽 두께 변화 | 보류 3D 변화 | 보류 재투영 변화 |\n| --- | --- | --- | --- | --- | --- | --- |\n'
  def pct(v):return '미평가' if v is None else f'{v:+.2%}'
  for r in results:
   if r['scope'].startswith('final'):report+=f"| {r['code']} {r['arm']} | {r['shared_planes']} | {r['accepted_points']} | {pct(r['wall_gap_change'])} | {pct(r['wall_thickness_change'])} | {pct(r['validation_3d_error_change'])} | {pct(r['validation_reprojection_error_change'])} |\n"
  report+='\n음수는 해당 오차/두께 감소다. 벽 기준 평면과 관측 ID는 G6와 같은 A0 참조이며 camera0/1만 지지한다. 서로 다른 공간 패치를 가진 source의 signed median은 공유 평면에 모여도 변할 수 있다. 층 간격·두께를 함께 보고, 적합 평면 잔차가 0이 되는 현상을 정확도 증거로 쓰지 않는다. 보정 후 육안 품질을 이 수치만으로 단정하지 않는다.\n\n'
  report+='기하 전용 region growing은 camera0에서 국소 인접 그래프가 책상·벽까지 연쇄 연결된 큰 후보를 만들었고 최종 robust 70% 지지 조건에서 거절됐다. camera2 후보도 지원 부족이다. A6에는 공유 보정이 없으므로 A4/A6 수용 관측 교집합은 비어 있다. 이 결과는 영상 분할의 보편적 우위를 뜻하지 않는다.\n\n'
  report+='자동 RGB 검토: camera0의 넓은 두 번째 SAM 마스크는 책상 일부까지 포함한다. camera1에는 중복 벽 마스크가 있고, camera2는 다른 벽/물체 주변이 일부 섞인다. NMS 후의 camera0/1 오버레이는 벽 영역을 더 잘 보존하지만 정답 annotation 기반 평가는 아니다. 법선 정제로 좁은 성분이 생기며 적용 면적도 달라진다. 새 RGB ROI·경계·비대상 이동 수는 개별 군 metrics에 있다.\n\n'
  report+='모든 최종 군의 배열·두 색상 PLY를 다시 읽어 점 수/좌표/색/출처를 검증했다. 거절/비대상은 bitwise 유지한다. frustum 관측 유지와 실제 pixel coverage를 별도로 평가했고, retained는 보존 통과 시 proposed를 가리킨다. 제안값이 A0와 같으면 그대로 표시한다. H5c/H5d는 해당 H4의 평면·목표·gate와 정확히 같다.\n\n'
  report+='투영은 원본 입력과 같은 512×384, 같은 nearest-pixel z-buffer/점 크기이며 RGB 학습·색 혼합 없이 원본 픽셀색을 쓴다. 전체/타 프레임/출처별 카메라 투영, 고정 외부 시점, 고정 범위 벽 단면, 수용 마스크를 보존했다. PLY 빠른 경로는 `results/c3a_plane_refinement/ply_review/`이며 **c=기본 최종, d=중복 마스크 NMS 보조 최종**이다. initial/proposed/retained와 RGB/frame_colors를 구분한다.\n\n'
  report+='GT 동기·resize/K/pose·정렬을 이 실험에서 검증하지 않았으므로 실제 기하 정확도는 미평가다. 원래 보류 대응도 소수이며 벽은 텍스처가 적다. 보류 지표가 그대로여도 벽 개선의 독립 검증이 되지 않는다. 모델 설치/다운로드 시간은 별도 계측하지 않았으며 로딩·추론·기하 단계 시간과 process/GPU peak memory는 JSON에 기록했다. 공식 checkpoint SHA256, SAM 소스 commit, HF revision, 환경 변화도 보존했다.\n'
  st.finish({'decision':'COMPLETED_DIAGNOSTIC_ONLY','scientific_improvement':False,'baseline_geometry':basegeo,'baseline_wall':basewall,'baseline_visibility':basevis,'comparisons':results,'all_array_ply_audits_passed':True,'audits':audits,'stage_integrity_audit':integrity,'ply_inventory_count':len(inventory),'timing_storage':timings,'setup_provenance':setup,'fixed_roi_intersection':intersection,'review_directory':str(review),'primary_final_codes':['H3c','H4c','H5c'],'NMS_final_codes':['H3d','H4d','H5d']},report)
  shutil.copy2(st.path/'evaluation/ply_inventory.csv',st.doc/'evaluation/ply_inventory.csv');(DOC/'summary.md').write_text(report+f'\n\n[H6 상세 보고서]({st.doc.relative_to(DOC)}/report.md)\n')
  lines=['# H 실험 실행 목록','','[사전 계획](../../c3a_planargs_plane_refinement_experiment_plan.md) · [종합 결과](summary.md)','','H0~H6 완료. 최종 split 보완: c=기본, d=마스크 NMS. a/b 및 보완 전 실패도 보존.','','| 코드 | 상태 | 보고서 |','| --- | --- | --- |']
  for p in sorted(DOC.glob('*/*/report.md')):
   code=p.parents[1].name;status='실패 보존' if code=='H0' else ('완료·보완 전 진단' if code in ['H2','H2b','H3','H4','H5','H3b','H4b','H5b'] else '완료');lines.append(f'| {code} | {status} | [{p.parent.name}]({p.relative_to(DOC)}) |')
  (DOC/'index.md').write_text('\n'.join(lines)+'\n')
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
