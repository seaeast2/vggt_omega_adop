"""Fixed observation metrics and visibility, keeping planarity separate from accuracy."""
from base import *
from scipy.ndimage import map_coordinates
import itertools

def matches():
 p=next((ROOT/'results/camera_fov_alignment').glob('tum-freiburg1_desk-C1-*/stages/C1/artifacts/baseline/matches/matches.npz'));return dict(np.load(p))

def match_metrics(data,xyz,accepted):
 m=matches();delta=np.empty_like(data['depth'])
 for i in range(3):
  sl=data['fid']==i;delta[i]=((xyz[sl]-data['xyz'][sl])@data['e'][i,2,:3]).reshape(384,512)
 rows=[]
 for ix,(i,j) in enumerate(m['pair']):
  pi,pj=[],[];original=[];region=[]
  for cam,key,dk in [(i,'uv_i','di'),(j,'uv_j','dj')]:
   uv=m[key][ix];dz=float(map_coordinates(delta[cam],[[uv[1]],[uv[0]]],order=1,mode='nearest')[0]);D=float(m[dk][ix])+dz;pt=c.unproject(uv[None],np.array([D]),data['k'][cam],data['e'][cam])[0];original.append(pt)
   xy=np.rint(uv).astype(int);region.append(bool(accepted[int(cam)*384*512+xy[1]*512+xy[0]]))
  a,b=original;rel=[];zerr=[];reproj=[]
  for cam,dep,other,targetuv in [(i,m['di'][ix],b,m['uv_i'][ix]),(j,m['dj'][ix],a,m['uv_j'][ix])]:
   r=(a-b)@data['e'][cam,:,:3].T/dep;rel.append(float(np.linalg.norm(r)));zerr.append(float(abs(r[2])));uv,z,v=c.project(other[None],data['k'][cam],data['e'][cam],384,512);reproj.append(float(np.linalg.norm(uv[0]-targetuv)))
  rows.append({'index':ix,'pair':[int(i),int(j)],'validation':bool(m['validation'][ix]),'track_id':int(m['track_id'][ix]),'corrected_either':any(region),'corrected_both':all(region),'relative_3d':rel,'relative_z':zerr,'reprojection_pixel':reproj})
 result={}
 for fold in ['fit','validation','all']:
  result[fold]={}
  for region in ['all','corrected','non_target']:
   select=[r for r in rows if (fold=='all' or r['validation']==(fold=='validation')) and (region=='all' or r['corrected_either']==(region=='corrected'))];pairs=[];values={k:[] for k in ['relative_3d','relative_z','reprojection_pixel']};weights=[]
   for pair in itertools.combinations(range(3),2):
    rr=[r for r in select if tuple(r['pair'])==pair]
    if not rr:continue
    vals={k:np.array([v for r in rr for v in r[k]]) for k in values};pairs.append({'pair':list(pair),'matches':len(rr),**{k:c.stats(v) for k,v in vals.items()}})
    for k,v in vals.items():values[k].append(v)
    weights.append(np.full(2*len(rr),1/(2*len(rr))))
   result[fold][region]={'matches':len(select),'pairs':pairs,**{k:d.weighted_stats(np.concatenate(v),np.concatenate(weights)) if v else {'count':0} for k,v in values.items()}}
 result['observations']=rows;result['interpolation']='bilinear dense delta-Z added to frozen original match Z; same frozen corrected K and camera ray';return result

def visibility(data,xyz):
 h,w=data['depth'].shape[1:];rows=[];pixel=[]
 for j in range(3):
  b,win,_=c.front(data['xyz'],data['k'][j],data['e'][j],h,w);z,nwin,_=c.front(xyz,data['k'][j],data['e'][j],h,w);bmask=win>=0;new=nwin>=0
  pixel.append({'camera':j,'initial_pixels':int(bmask.sum()),'new_pixels':int(new.sum()),'coverage_before':float(bmask.mean()),'coverage_after':float(new.mean()),'coverage_loss_percentage_points':float((bmask.mean()-new.mean())*100),'initial_pixels_lost':int(np.sum(bmask&~new)),'initial_pixels_retention':float(np.sum(bmask&new)/max(1,bmask.sum())),'passed':float(bmask.mean()-new.mean())<=.005+1e-12})
  for i in range(3):
   if i==j:continue
   ids=np.flatnonzero(data['fid']==i);ref=c.project(data['xyz'][ids],data['k'][j],data['e'][j],h,w)[2];valid=c.project(xyz[ids],data['k'][j],data['e'][j],h,w)[2];loss=float(np.sum(ref&~valid)/max(1,ref.sum()));rows.append({'source':i,'target':j,'initial_valid':int(ref.sum()),'retained':int(np.sum(ref&valid)),'loss_fraction':loss,'passed':loss<=.005+1e-12})
 return {'frustum_pairs':rows,'pixel_coverage':pixel,'passed':all(r['passed'] for r in rows+pixel)}

def wall_metrics(data,xyz,out):
 f=np.load(observation_stage()/'artifacts/masks/fixed_wall_reference.npz');ids=f['ids'];center=f['center'];normal=f['normal'];Dref=float(np.median(data['d0'][ids]));dist=(xyz[ids]-center)@normal;med=[];rows=[]
 for i in range(3):
  vals=dist[data['fid'][ids]==i];rows.append({'frame':i,'count':len(vals),'signed_distance':c.stats(vals),'thickness_p95_p05':float(np.percentile(vals,95)-np.percentile(vals,5)) if len(vals) else None})
  if len(vals)>=50:med.append(float(np.median(vals)))
 out.mkdir(parents=True,exist_ok=True);np.savez_compressed(out/'wall_signed_distance.npz',ids=ids,frame_id=data['fid'][ids],distance=dist,center=center,normal=normal)
 basis=np.array([1.,0,0]);basis-=basis@normal*normal;basis/=np.linalg.norm(basis);s=(data['xyz'][ids]-center)@basis;lo,hi=np.percentile(s,[.1,99.9]);limits=[-.08*Dref,.08*Dref];canvas=np.full((480,640,3),250,np.uint8)
 for i in range(3):
  sel=data['fid'][ids]==i;x=((xyz[ids][sel]-center)@basis-lo)/max(hi-lo,1e-12)*600+20;y=440-(dist[sel]-limits[0])/(limits[1]-limits[0])*400;good=(x>=0)&(x<640)&(y>=0)&(y<480)
  canvas[y[good][::3].astype(int),x[good][::3].astype(int)]=c.PALETTE[i]
 c.image_write(out/'wall_section.png',canvas)
 return {'fixed_observations':len(ids),'frames':rows,'layer_gap_model_units':max(med)-min(med) if len(med)>=2 else None,'thickness_p95_p05':float(np.percentile(dist,95)-np.percentile(dist,5)),'normalizer':Dref,'plane_frozen_from_G1_A0':True,'not_gt':True,'plot_clip_fraction':float(np.mean((dist<limits[0])|(dist>limits[1])))}

def external(data,xyz,out):
 lo=np.percentile(data['xyz'],5,axis=0);hi=np.percentile(data['xyz'],95,axis=0);target=(lo+hi)/2;inv=np.linalg.inv(data['e'][0,:,:3]);eye=target+inv@np.array([1.,-.8,-2.])*np.median(data['d0']);forward=target-eye;forward/=np.linalg.norm(forward);right=np.cross(inv@np.array([0.,1.,0.]),forward);right/=np.linalg.norm(right);down=np.cross(forward,right);R=np.array([right,down,forward]);E=np.c_[R,-R@eye];K=np.array([[380.,0,320],[0,380.,240],[0,0,1.]])
 z,win,_=c.front(xyz,K,E,480,640);hit=win>=0;im=np.zeros((480,640,3),np.uint8);im[hit]=data['raw_rgb'][win[hit]];c.image_write(out/'external_rgb.png',im);im[hit]=c.PALETTE[data['fid'][win[hit]]];c.image_write(out/'external_frame_colors.png',im);np.savez_compressed(out/'external_camera.npz',K=K,E=E,baseline_xyz_range=np.array([lo,hi]))

def arm(st,data,name,groups,soft=False):
 from geometry import update
 out=st.path/'artifacts/arms'/name;out.mkdir(parents=True);t=time.perf_counter();xyz,accepted,local,shared,targets,reason,planerecords=update(data,groups,soft);update_time=time.perf_counter()-t;inv=export(data,xyz,out/'proposed',accepted,local,shared,targets);np.savez_compressed(out/'proposed/gate_reasons.npz',reason=reason)
 vis=visibility(data,xyz);geo=match_metrics(data,xyz,accepted);wall=wall_metrics(data,xyz,out/'sections');external(data,xyz,out/'sections');rows,sourcerows,render=d.render(data,xyz,data['k'],out/'projections');c.panel(st.path/f'artifacts/figures/{name}_camera_rgb.png',rows,['original same scale',name,'source frames']);c.panel(out/'all_sources.png',sourcerows,['all sources','other sources','only source0','only source1','only source2']);shutil.copy2(out/'sections/wall_section.png',st.path/f'artifacts/figures/{name}_section.png');shutil.copy2(out/'sections/external_rgb.png',st.path/f'artifacts/figures/{name}_external.png')
 zdelta=np.linalg.norm(xyz-data['xyz'],axis=1);relative=np.zeros(len(xyz))
 for i in range(3):
  ids=data['fid']==i;relative[ids]=abs((xyz[ids]-data['xyz'][ids])@data['e'][i,2,:3])/data['d0'][ids]
 preservation=inv['all_invariants_passed'] and vis['passed'];state='proposed' if preservation else 'initial';initial=latest('H0a')/'artifacts/baseline/A0_C3a';(out/'initial').symlink_to(os.path.relpath(initial,out),target_is_directory=True);(out/'retained').symlink_to(state,target_is_directory=True)
 roi=np.load(observation_stage()/'artifacts/masks/splits_rois.npz');roirows={}
 for key in ['wall_interior','object_boundary','non_target']:
  mask=roi[key].ravel();roirows[key]={'points':int(mask.sum()),'changed':int(np.sum(mask&(zdelta>0))),'relative_move':c.stats(relative[mask&(zdelta>0)]),'per_frame_changed':[int(np.sum(mask&(zdelta>0)&(data['fid']==i))) for i in range(3)]}
 row={'name':name,'soft':soft,'groups':planerecords,'valid_planes':len(planerecords),'shared_planes':sum(len(r['fit']['frames'])>=2 for r in planerecords),'accepted_points':int(accepted.sum()),'changed_points':int(np.sum(zdelta>0)),'accepted_fraction':float(accepted.mean()),'relative_depth_move':c.stats(relative[accepted]),'invariants':inv,'visibility':vis,'geometry':geo,'fixed_wall':wall,'roi_movement':roirows,'retained_state':state,'preservation_passed':preservation,'decision':'NO_SHARED_PLANE' if not groups and 'SHARED' in name else ('NO_VALID_PLANE' if not planerecords else 'LOW_SUPPORT_DIAGNOSTIC_ONLY'),'timing_seconds':{'reprojection':update_time,'arm_total':time.perf_counter()-t},'initial':c.record(initial/'pointmap.npz'),'proposed':c.record(out/'proposed/pointmap.npz'),'retained_equals_initial':state=='initial' or np.array_equal(xyz,data['xyz'])}
 c.json_write(out/'metrics.json',row);return row
