from base import *
from geometry import normals,components,geometric_regions
from scipy import ndimage
import hashlib

def run(code='H2',dedup=False):
 st=Stage(code,parents=[latest('H0a'),latest('H1')],extra={'geometry_wall_review_rule':'Frozen RGB rectangles; >=100 rectangle points, >=5pct candidate fraction; no corrected geometry used. Candidate generation itself uses no image segmentation.','raw_duplicate_policy':'SAM predicted-IoU rank mask NMS at mask IoU>0.5; remaining overlaps ambiguous' if dedup else 'Identical/overlapping masks remain stored; pixels in >1 candidate are ambiguous and excluded.', 'mask_nms_supplement':dedup})
 try:
  data=load();h,w=data['depth'].shape[1:];size=h*w;minimum=int(np.ceil(.005*size));out=st.path/'artifacts/masks';out.mkdir(parents=True)
  start=time.perf_counter();nn,ev,valid=normals(data,7);n7time=time.perf_counter()-start;start=time.perf_counter();n21,e21,v21=normals(data,21);n21time=time.perf_counter()-start
  angle=np.rad2deg(np.arccos(np.clip(abs(np.sum(nn*n21,-1)),0,1)));np.savez_compressed(out/'normals.npz',normals_7=nn,eigenvalues_7=ev,valid=valid,normals_21=n21,angle_difference_degree=angle)
  border=np.zeros((h,w),bool);border[8:-8,8:-8]=True;split=np.zeros((3,h,w),bool);tile_rows=[]
  for i in range(3):
   for ty in range(12):
    for tx in range(16):
     digest=hashlib.sha256(f'0,{i},{tx},{ty}'.encode()).hexdigest();hold=int(digest[:16],16)%100<20;split[i,ty*32:(ty+1)*32,tx*32:(tx+1)*32]=hold;tile_rows.append({'frame':i,'tile':[tx,ty],'holdout':hold,'sha256':digest})
  matchfile=next((ROOT/'results/camera_fov_alignment').glob('tum-freiburg1_desk-C1-*/stages/C1/artifacts/baseline/matches/matches.npz'));match=dict(np.load(matchfile));trackhold=set(match['track_id'][match['validation']].tolist());known_holdout=np.zeros_like(split)
  for ix,pair in enumerate(match['pair']):
   if match['track_id'][ix] not in trackhold:continue
   for frame,uv in [(int(pair[0]),match['uv_i'][ix]),(int(pair[1]),match['uv_j'][ix])]:
    x,y=np.rint(uv).astype(int);yy,xx=np.ogrid[:h,:w];known_holdout[frame]|=((xx-x)**2+(yy-y)**2<=9)
  split|=known_holdout;c.json_write(out/'tile_split.json',tile_rows)
  rects=[(220,8,390,65),(70,8,220,65),(365,8,500,60)];wallroi=np.zeros((3,h,w),bool)
  for i,(x0,y0,x1,y1) in enumerate(rects):wallroi[i,y0:y1,x0:x1]=True
  rois={'wall_interior':wallroi,'object_boundary':np.zeros_like(wallroi),'non_target':np.zeros_like(wallroi)}
  sets={'raw':[],'refined':[],'geometry':[]};review=[];candidate_stats=[];counter=0;start=time.perf_counter()
  def addset(method,i,masks):
   nonlocal counter
   ambiguity=np.sum(masks,axis=0)>1 if len(masks) else np.zeros((h,w),bool);labs=np.full((h,w),-1,np.int32)
   for idx,mask in enumerate(masks):
    mask=mask&~ambiguity
    if mask.sum()<minimum:continue
    ids=np.flatnonzero(mask.ravel())+i*size;fitids=ids[~split[i].ravel()[ids%size]];holdids=ids[split[i].ravel()[ids%size]]
    occ=np.zeros((4,4),int)
    yy,xx=np.where(mask)
    for cy in range(4):
     for cx in range(4):occ[cy,cx]=np.sum((yy//(h//4)==cy)&(xx//(w//4)==cx))
    entry={'candidate_id':counter,'method':method,'frame':i,'mask_index':idx,'points':len(ids),'fit_count':len(fitids),'holdout_count':len(holdids),'occupied_4x4':int(np.sum(occ>0)),'support_4x4':occ.tolist(),'wall_rgb_roi_points':int(np.sum(mask&wallroi[i]))}
    sets[method].append(entry);np.savez_compressed(out/f'candidate_{counter:03}.npz',ids=ids,fit_ids=fitids,holdout_ids=holdids);labs[mask]=counter;counter+=1
   np.savez_compressed(out/f'camera_{i}_{method}_labels.npz',labels=labs,ambiguous=ambiguity)
   colors=np.random.default_rng(0).integers(30,255,(max(counter,1),3));show=data['rgb'][i].copy();hit=labs>=0;show[hit]=np.rint(.5*show[hit]+.5*colors[labs[hit]]).astype(np.uint8);show[ambiguity]=[255,0,255];c.image_write(st.path/f'artifacts/figures/camera_{i}_{method}_overlay.png',show)
  for i in range(3):
   with np.load(latest('H1')/f'artifacts/masks/camera_{i}_masks.npz') as z:raw=z['masks'].copy();sam_scores=z['sam_scores'].copy()
   if dedup:
    order=np.argsort(-sam_scores,kind='stable');kept=[];decisions=[]
    for a in order:
     ious=[float(np.sum(raw[a]&raw[b])/max(1,np.sum(raw[a]|raw[b]))) for b in kept];reject=any(v>.5 for v in ious);decisions.append({'original_index':int(a),'sam_score':float(sam_scores[a]),'iou_with_preceding_kept':ious,'retained':not reject})
     if not reject:kept.append(int(a))
    c.json_write(out/f'camera_{i}_mask_nms.json',{'ranking':'SAM predicted IoU descending, stable index ties','iou_threshold':.5,'decisions':decisions,'no_corrected_geometry_used':True});raw=raw[kept]
   # Boundaries/confidence affect support and movement only; no observations are removed.
   rawinner=[ndimage.binary_erosion(mask,structure=np.ones((3,3)),iterations=3)&border&valid[i] for mask in raw]
   union=raw.any(0) if len(raw) else np.zeros((h,w),bool);rois['object_boundary'][i]=ndimage.binary_dilation(union,iterations=3)^ndimage.binary_erosion(union,iterations=3);rois['non_target'][i]=~ndimage.binary_dilation(union,iterations=3)
   np.savez_compressed(out/f'camera_{i}_support_masks.npz',raw_union=union,raw_eroded_union=np.any(rawinner,axis=0) if rawinner else np.zeros((h,w),bool),image_border_interior=border,confidence_normal_valid=valid[i],raw_erosion_rejected=union&~ndimage.binary_erosion(union,structure=np.ones((3,3)),iterations=3))
   addset('raw',i,rawinner)
   refined=[]
   for mask in rawinner:
    ids=np.flatnonzero(mask.ravel())
    if len(ids)<minimum:continue
    c.cv2.setRNGSeed(0);criteria=(c.cv2.TERM_CRITERIA_MAX_ITER,10,0);_,labels,centers=c.cv2.kmeans(nn[i].reshape(-1,3)[ids].astype(np.float32),5,None,criteria,1,c.cv2.KMEANS_PP_CENTERS)
    cluster=np.full(h*w,-1,int);cluster[ids]=labels[:,0];cluster=cluster.reshape(h,w)
    for j in range(5):refined.extend(components(mask&(cluster==j),minimum))
   addset('refined',i,refined)
   regions=geometric_regions(data['xyz'][i*size:(i+1)*size].reshape(h,w,3),nn[i],valid[i]&border,data['depth'][i]);selected=[]
   for j,mask in enumerate(regions):
    overlap=int(np.sum(mask&wallroi[i]));fraction=overlap/max(1,int(mask.sum()));wall=overlap>=100 and fraction>=.05
    review.append({'frame':i,'region':j,'points':int(mask.sum()),'wall_roi_points':overlap,'wall_fraction':fraction,'include_in_wall_experiment':wall,'reviewer':'Codex frozen original RGB rectangle rule; no semantic GT'})
    if wall:selected.append(ndimage.binary_erosion(mask,structure=np.ones((3,3)),iterations=3))
   addset('geometry',i,selected)
   c.image_write(st.path/f'artifacts/figures/camera_{i}_normals7.png',np.rint((nn[i]+1)*127.5).clip(0,255).astype(np.uint8))
   st.log('candidates',camera=i,raw=len(rawinner),refined=len(refined),geometry_regions=len(regions),geometry_walls=len(selected))
  c.json_write(out/'candidates.json',sets);c.json_write(out/'geometry_wall_review.json',review);np.savez_compressed(out/'splits_rois.npz',holdout=split,known_track_holdout=known_holdout,wall_interior=wallroi,object_boundary=rois['object_boundary'],non_target=rois['non_target'],wall_rectangles=np.array(rects))
  # A0 fixed world ROI and plane from prior G6, plus new RGB-only rectangles above.
  gplane=next((ROOT/'results/point_line_depth_refinement').glob('tum-freiburg1_desk-G1-*/stages/G1/artifacts/observations/wall_reference.npz'));gp=np.load(gplane);uv,z,vis=c.project(data['xyz'],data['k'][0],data['e'][0],h,w);old=vis&(uv[:,0]>=220)&(uv[:,0]<390)&(uv[:,1]>=5)&(uv[:,1]<65);oldids=np.flatnonzero(old)
  np.savez_compressed(out/'fixed_wall_reference.npz',ids=oldids,center=gp['center'],normal=gp['normal'],rgb_rectangles=np.array(rects));c.json_write(out/'frozen_roi_provenance.json',{'prior_G1_plane':c.record(gplane),'old_G6_wall_camera0_rectangle':[220,5,390,65],'old_ROI_source_counts':[int(np.sum(data['fid'][oldids]==i)) for i in range(3)],'new_rectangles':rects,'new_own_source_counts':[int(x.sum()) for x in wallroi],'freeze_before_corrected_output':True,'known_holdout_track_ids':sorted(int(x) for x in trackhold),'match_source':c.record(matchfile)})
  counts={k:{'candidates':len(v),'points':sum(x['points'] for x in v),'fit':sum(x['fit_count'] for x in v),'holdout':sum(x['holdout_count'] for x in v)} for k,v in sets.items()}
  st.finish({'decision':'CANDIDATES_SPLITS_ROIS_FROZEN','candidate_support':counts,'candidates':sets,'normal7_vs21_angle_degree':c.stats(angle[valid&v21]),'timing_seconds':{'normals7':n7time,'normals21_diagnostic':n21time,'candidate_refinement':time.perf_counter()-start},'geometry_wall_review':review,'split_heldout_fraction':float(split.mean()),'known_holdout_excluded_fit':True,'raw_masks_sha256':[c.record(latest('H1')/f'artifacts/masks/camera_{i}_masks.npz') for i in range(3)]},f'# {code} 후보·평가 분리 동결\n\n' + ('보조 H2b는 H1 원본 마스크를 수정하지 않고 SAM predicted-IoU 순서의 mask IoU>0.5 NMS로 중복 후보만 제거했다. 나머지 규칙·ROI·split은 H2와 같다. 이는 기본 군을 대체하지 않는 진단이다.\n\n' if dedup else '') + '7×7 PCA 법선, 원본 confidence 하위 10% 제외, 3 px 마스크 erosion과 독립 8 px 영상 border를 적용했다. seed 0의 법선 K-means 5개/10회 및 연결 성분으로 원시 마스크를 분리했다. 21×21은 진단만 했다. 후보 최소 면적은 984 px다.\n\n기하 전용 군은 7×7 이웃 그래프에서 법선 15°·양방향 국소 접평면 거리/원본 Z 0.5%로 생성했다. RGB에서 사전에 정한 벽 사각형 지지 100 px·후보 5% 이상 규칙으로 벽 후보를 표시했으며 영상 마스크는 생성에 사용하지 않았다. 이 검토 규칙과 모든 기하 영역의 수용/제외를 보존했다.\n\n16×12 타일 SHA256으로 fit/holdout을 고정하고, 알려진 보류 track 관측 3 px 주변을 추가로 fit에서 제외했다. 중복 후보 관측은 모호로 제외한다. 벽/경계/비대상 ROI를 보정 결과 생성 전에 고정했다. 기존 G6 벽 ROI와 새 RGB 사각형 ROI를 구분했다. 정답 분할 없이 정확도라고 부르지 않는다.')
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
