"""G-series: fixed observations, exact C3a P objective, bounded FoV/depth refinement."""
from pathlib import Path
import sys,json,shutil,subprocess,time,traceback,hashlib,itertools,os,platform,resource
import numpy as np
import cv2
from scipy.optimize import least_squares
from scipy.optimize._numdiff import approx_derivative
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/camera_fov_alignment'))
import common as c, matching as m, diagnostics as d
FAMILY='point_line_depth_refinement'
SRC=ROOT/'experiments'/FAMILY
BASE=ROOT/'results/camera_fov_alignment/tum-freiburg1_desk-C3a-20261112-001/stages/C3a'
BETA=np.load(BASE/'artifacts/fit/proposed_not_selected/pointmap.npz')['beta'].reshape(6)
class Stage:
 def __init__(self,code):
  self.code=code;date=c.stamp()[:10].replace('-','');seq=1
  root=ROOT/'results'/FAMILY
  while (root/f'tum-freiburg1_desk-{code}-{date}-{seq:03}').exists():seq+=1
  self.id=f'tum-freiburg1_desk-{code}-{date}-{seq:03}'
  self.path=root/self.id/'stages'/code;self.doc=ROOT/'docs/experiments'/FAMILY/code/self.id
  self.path.mkdir(parents=True);self.doc.mkdir(parents=True);self.start=time.time()
  for name in ['artifacts/source','artifacts/figures','evaluation','logs']:(self.path/name).mkdir(parents=True)
  for f in SRC.glob('*.py'):shutil.copy2(f,self.path/'artifacts/source'/f.name)
  for f in ['common.py','matching.py','diagnostics.py']:shutil.copy2(ROOT/'experiments/camera_fov_alignment'/f,self.path/'artifacts/source'/f)
  shutil.copy2(ROOT/'docs/vggt_omega_point_line_depth_refinement_experiment_plan.md',self.path/'artifacts/source/plan.md')
  c.json_write(self.path/'environment.json',{'python':sys.version,'numpy':np.__version__,'opencv':cv2.__version__,'scipy':__import__('scipy').__version__,'context':'host CPU; inference separately host GPU','platform':platform.platform()})
  c.json_write(self.path/'config_resolved.json',{'code':code,'beta_bounds':[c.LOW,c.HIGH],'s0':0,'depth_scale_bounds':[.95,1.05],'loss_weights':{'L':.25,'Z':.25,'A':1,'E':.25},'jacobian':'3-point numerical; amendment G0a','ftol':1e-8,'xtol':1e-8,'gtol':1e-8,'max_nfev':200,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})
  self.man={'status':'running','run_id':self.id,'code':code,'started_at':c.stamp()};c.json_write(self.path/'manifest.json',self.man)
 def log(self,event,**kw):
  line=json.dumps({'time':c.stamp(),'event':event}|kw,ensure_ascii=False);print(line,flush=True)
  with (self.path/'logs/run.log').open('a') as f:f.write(line+'\n')
 def finish(self,metrics,report):
  metrics|={'elapsed_seconds':time.time()-self.start,'process_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'gt_accuracy_evaluated':False}
  c.json_write(self.path/'evaluation/metrics.json',metrics)
  self.log('finished',decision=metrics.get('decision','EXECUTED'))
  self.man|={'status':'completed','ended_at':c.stamp(),'decision':metrics.get('decision','EXECUTED'),'artifacts':[c.record(f) for f in self.path.rglob('*') if f.is_file() and f.name!='manifest.json']}
  c.json_write(self.path/'manifest.json',self.man)
  for f in ['manifest.json','environment.json','config_resolved.json']:shutil.copy2(self.path/f,self.doc/f)
  shutil.copytree(self.path/'evaluation',self.doc/'evaluation',dirs_exist_ok=True)
  shutil.copytree(self.path/'artifacts/figures',self.doc/'figures',dirs_exist_ok=True)
  shutil.copy2(self.path/'logs/run.log',self.doc/'run.log')
  (self.doc/'report.md').write_text(report+'\n\n실행 경로: `'+str(self.path.relative_to(ROOT))+'`\n\nGT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.\n')
 def fail(self,e):
  self.man|={'status':'failed','error':str(e),'traceback':traceback.format_exc()};c.json_write(self.path/'manifest.json',self.man);shutil.copy2(self.path/'manifest.json',self.doc/'manifest.json');(self.doc/'report.md').write_text('# 실행 실패\n\n'+traceback.format_exc());self.log('failed',error=str(e))
def latest(code):
 paths=sorted((ROOT/'results'/FAMILY).glob(f'*-{code}-*/stages/{code}'))
 return [p for p in paths if json.loads((p/'manifest.json').read_text())['status']=='completed'][-1]
def load():
 data=c.load_data('tum-freiburg1_desk');matches=m.load(next((ROOT/'results/camera_fov_alignment').glob('tum-freiburg1_desk-C1-*/stages/C1/artifacts/baseline/matches/matches.npz')))
 return data,matches
def changed(data,x):
 out=data.copy();scales=np.exp(np.r_[0,x[6:]]) if len(x)>6 else np.ones(3);out['depth']=data['depth']*scales[:,None,None];return out,scales
def cover(data,x,ref):
 dd,sc=changed(data,x);return d.coverage(dd,x[:6],ref)
def geo(data,matches,x):
 dd,sc=changed(data,x);mm=matches.copy();mm['di']=matches['di']*sc[matches['pair'][:,0]];mm['dj']=matches['dj']*sc[matches['pair'][:,1]]
 # Keep normalization ORIGINAL, including in variable-depth stage.
 k=c.corrected_k(data['k'],x[:6].reshape(3,2));out={}
 for split,sel in [('fit',~matches['validation']),('validation',matches['validation'])]:
  rows=[];r3=[];rz=[];rp=[];ww=[]
  for i,j in itertools.combinations(range(3),2):
   ids=np.where(sel&(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j))[0]
   if not len(ids):continue
   a=c.unproject(matches['uv_i'][ids],mm['di'][ids],k[i],data['e'][i]);b=c.unproject(matches['uv_j'][ids],mm['dj'][ids],k[j],data['e'][j]);v=[];z=[];px=[]
   for cam,dep,points,uv in [(i,matches['di'][ids],b,matches['uv_i'][ids]),(j,matches['dj'][ids],a,matches['uv_j'][ids])]:
    rr=(a-b)@data['e'][cam,:,:3].T/dep[:,None];v.extend(np.linalg.norm(rr,axis=1));z.extend(abs(rr[:,2]));proj=c.project(points,k[cam],data['e'][cam],*data['depth'].shape[1:])[0];px.extend(np.linalg.norm(proj-uv,axis=1))
   rows.append({'pair':[i,j],'relative_3d':c.stats(v),'relative_z':c.stats(z),'reprojection_px':c.stats(px)})
   r3.extend(v);rz.extend(z);rp.extend(px);ww.extend([1/len(v)]*len(v))
  out[split]={'relative_3d':d.weighted_stats(r3,ww),'relative_z':d.weighted_stats(rz,ww),'reprojection_px':d.weighted_stats(rp,ww),'pairs':rows}
 return out

def export(st,data,x,path):
 path.mkdir(parents=True,exist_ok=False);dd,sc=changed(data,x);xyz=c.points(dd,x[:6]);k=c.corrected_k(data['k'],x[:6].reshape(3,2))
 assert len(xyz)==589824 and np.isfinite(xyz).all()
 np.savez_compressed(path/'pointmap.npz',xyz=xyz,frame_id=data['fid'],pixel_uv=data['uv'],rgb=data['raw_rgb'],intrinsics=k,extrinsics=data['e'],beta=x[:6],depth_scale=sc)
 c.ply_write(path/'pixel_rgb.ply',xyz,data['raw_rgb'],data['fid']);c.ply_write(path/'frame_colors.ply',xyz,c.PALETTE[data['fid']],data['fid'])
 rows,source,metrics=d.render(dd,xyz,k,path/'projections')
 # Common fixed K rendering, separate from candidate K.
 fixed=[]
 for i in range(3):
  z,win,_=c.front(xyz,data['k'][i],data['e'][i],*data['depth'].shape[1:]);im=np.zeros_like(data['rgb'][i]);mask=win>=0;im[mask]=data['raw_rgb'][win[mask]];fixed.append(im)
  c.image_write(path/f'fixed_K_camera_{i}.png',im)
 c.panel(st.path/'artifacts/figures'/f'{path.parent.name}_{path.name}.png',[[data['rgb'][i],rows[i][1],rows[i][2],fixed[i]] for i in range(3)],['Input RGB','Candidate RGB','Source colors','Fixed raw K RGB'])
 return metrics

def g0(st):
 data,matches=load();a,b,w,_=c.build_system(data,m.subset(matches,~matches['validation']));beta,hist,ok=c.solve_irls(a,b,w)
 frozen=np.load(BASE/'artifacts/fit/proposed_not_selected/pointmap.npz');err=float(abs(c.points(data,BETA)-frozen['xyz']).max());assert err<1e-8 and abs(beta-BETA).max()<1e-7 and ok
 jac=approx_derivative(lambda x:(a@x+b).ravel(),BETA,method='3-point');jerr=float(abs(jac-a.reshape(-1,6)).max());assert jerr<1e-7
 rng=np.random.default_rng(0);aa=rng.normal(size=(36,3,6));truth=np.array([1.02,.98,1.03,.97,1.01,.99]);bb=-aa@truth
 recovered=least_squares(lambda x:(aa@x+bb).ravel(),np.ones(6),bounds=(c.LOW,c.HIGH),jac='3-point',gtol=1e-12).x
 assert abs(recovered-truth).max()<1e-7
 # Known pinhole line: samples on y=0 project exactly onto v=cy.
 uv=np.array([[10.,20.],[30.,20.],[50.,20.]]);kk=np.array([[100.,0,30],[0,100,20],[0,0,1]]);ee=np.c_[np.eye(3),np.zeros(3)]
 pp=c.unproject(uv,np.ones(3)*2,kk,ee);proj=c.project(pp,kk,ee,60,80)[0];assert abs(proj[:,1]-20).max()<1e-10
 assert np.all(abs(proj[:,1]-25)==5) # incorrect correspondence control
 deg=np.zeros_like(aa);assert c.rank_info(deg)['rank']==0
 result={'decision':'TECHNICAL_CHECKS_PASSED','c3a_reprojection_xyz_max_abs':err,'c3a_beta_max_abs':float(abs(beta-BETA).max()),'affine_jacobian_max_abs':jerr,'synthetic_beta_max_abs':float(abs(recovered-truth).max()),'line_projection_and_wrong_line_control':True,'zero_sensitivity_rank':0,'rank':c.rank_info(a),'fit_pair_counts':[24,8,15],'validation_pair_counts':[6,3,1],'source_inputs':data['inputs'],'limitations':'G0a performs additional nonlinear depth/Jacobian degeneracy controls before G3'}
 for name,x in [('B0',np.ones(6)),('B1',BETA),('B2',np.ones(6))]:export(st,data,x,st.path/'artifacts/baselines'/name)
 st.finish(result,'# G0 C3a 기준선 재현\n\n재역투영·β 재현, affine Jacobian, 합성 FoV 복구, 선 재투영과 오대응 제어를 통과했다.\n\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```')

def g1(st):
 data,matches=load();art=st.path/'artifacts/observations';art.mkdir();np.savez_compressed(art/'matches.npz',**matches)
 # Manually reviewed in RGB before any G2 fitting: physical right-hand monitor screen edges.
 # LSD endpoints deliberately not matched as points.
 specs={'screen_top':{0:19,1:8,2:8},'screen_bottom':{0:0,1:0,2:0},'screen_right':{0:31,1:21}}
 all_lines=[]
 for i,rgb in enumerate(data['rgb']):
  lines=cv2.createLineSegmentDetector().detect(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY))[0][:,0].astype(float);lines=lines[np.linalg.norm(lines[:,:2]-lines[:,2:],axis=1)>=40][:100];all_lines.append(lines)
 c.json_write(art/'lsd_candidates.json',[x.tolist() for x in all_lines]);tracks=[];samples=[]
 for structure,obs in specs.items():
  valid=int.from_bytes(hashlib.sha256(('0:'+structure).encode()).digest()[:8],'little')%5==0
  tracks.append({'structure':structure,'validation':valid,'observations':{str(i):all_lines[i][idx].tolist() for i,idx in obs.items()},'reviewer':'Codex RGB visual review; not correspondence GT'})
  for i,j in itertools.combinations(obs,2):
   for src,dst in [(i,j),(j,i)]:
    line=all_lines[src][obs[src]].reshape(2,2);target=all_lines[dst][obs[dst]].reshape(2,2);length=np.linalg.norm(line[1]-line[0]);count=max(3,int(.8*length/8)+1);uv=line[0]+np.linspace(.1,.9,count)[:,None]*(line[1]-line[0]);dep,good,_=m.depth_samples(data,src,uv)
    # Exclude line fit samples overlapping held-out point observations (2px radius).
    if not valid:
     for field,side in [('uv_i',0),('uv_j',1)]:
      pts=matches[field][matches['validation']&(matches['pair'][:,side]==src)]
      if len(pts):good&=(np.linalg.norm(uv[:,None]-pts[None],axis=2).min(1)>2)
    coeff=np.cross(np.r_[target[0],1],np.r_[target[1],1]);coeff/=np.linalg.norm(coeff[:2])
    if good.any():samples.append({'structure':structure,'src':src,'dst':dst,'uv':uv[good].tolist(),'depth':dep[good].tolist(),'target':target.tolist(),'coeff':coeff.tolist(),'validation':valid})
 c.json_write(art/'line_tracks.json',tracks);c.json_write(art/'line_samples.json',samples)
 for i,rgb in enumerate(data['rgb']):
  im=rgb.copy()
  for tr in tracks:
   if str(i) not in tr['observations']:continue
   l=np.rint(tr['observations'][str(i)]).astype(int).reshape(2,2);cv2.line(im,tuple(l[0]),tuple(l[1]),(255,0,255) if tr['validation'] else (0,255,0),2);cv2.putText(im,tr['structure'],tuple(l[0]),0,.4,(255,0,0),1)
  c.image_write(st.path/f'artifacts/figures/line_annotation_camera_{i}.png',im)
 roi={'wall_camera0':[220,5,390,65],'desk_camera0':[330,250,470,280],'boundary_camera0':[180,130,215,190]};c.json_write(art/'roi.json',roi)
 support=[]
 for i,j in itertools.combinations(range(3),2):
  rows=[tr for tr in tracks if str(i) in tr['observations'] and str(j) in tr['observations']];support.append({'pair':[i,j],'fit_tracks':sum(not tr['validation'] for tr in rows),'validation_tracks':sum(tr['validation'] for tr in rows),'passed':False})
 # Reference wall plane from B1 camera0 wall points, fixed for all later arms.
 xyz=c.points(data,BETA);u=data['uv'];ids=np.flatnonzero((data['fid']==0)&(u[:,0]>=220)&(u[:,0]<390)&(u[:,1]>=5)&(u[:,1]<65));center=xyz[ids].mean(0);_,_,vt=np.linalg.svd(xyz[ids]-center,full_matrices=False)
 np.savez_compressed(art/'wall_reference.npz',center=center,normal=vt[-1],ids=ids)
 # Fit tile masks derived strictly from C3a anchor tracks, and validation tile exclusion.
 tile=np.zeros((3,12,16),np.int8)
 for val in [False,True]:
  for side,field in [(0,'uv_i'),(1,'uv_j')]:
   for cam,uv in zip(matches['pair'][matches['validation']==val,side],matches[field][matches['validation']==val]):tile[cam,min(11,int(uv[1]/32)),min(15,int(uv[0]/32))]=2 if val else 1
 np.savez_compressed(art/'fit_tiles.npz',tiles=tile)
 result={'decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','line_support':support,'tracks':tracks,'sample_counts':{'fit':sum(len(s['uv']) for s in samples if not s['validation']),'validation':sum(len(s['uv']) for s in samples if s['validation'])},'observations_frozen_at':c.stamp(),'point_support':m.pair_support(matches,384,512),'note':'Monitor borders only; parallel/adjacent edges correlated. No manual line endpoint refinement. Plane fit fixed before G2.'}
 st.finish(result,'# G1 관측 동결\n\n영상에서 공통 모니터의 위·아래·오른쪽 테두리를 확인하고 LSD 선분을 대응시켰다. 선 지원 기준 미달이므로 후속 선 실험은 탐색적이다.\n\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```')

class Problem:
 def __init__(self,data,matches,lines,depth=False,L=False,Z=False,E=None,wL=.25,wZ=.25):
  self.data=data;self.matches=matches;self.lines=lines;self.depth=depth;self.L=L;self.Z=Z;self.E=E;self.wL=wL;self.wZ=wZ
  self.norm={};raw=self.parts(np.r_[BETA,[0,0]] if depth else BETA)
  self.norm={k:max(float(np.dot(v,v)/2),1e-8) for k,v in raw.items() if k in ['P','L','Z','E']}
 def parts(self,x):
  data=self.data;mat=self.matches;sc=np.exp(np.r_[0,x[6:]]) if len(x)>6 else np.ones(3);k=c.corrected_k(data['k'],x[:6].reshape(3,2));h,w=data['depth'].shape[1:];pieces={'P':[],'Z':[],'L':[]}
  for i,j in itertools.combinations(range(3),2):
   ids=np.where((mat['pair'][:,0]==i)&(mat['pair'][:,1]==j))[0]
   if not len(ids):continue
   a=c.unproject(mat['uv_i'][ids],mat['di'][ids]*sc[i],k[i],data['e'][i]);b=c.unproject(mat['uv_j'][ids],mat['dj'][ids]*sc[j],k[j],data['e'][j]);diff=a-b
   for cam,dep,other,targetdepth in [(i,mat['di'][ids],b,mat['di'][ids]*sc[i]),(j,mat['dj'][ids],a,mat['dj'][ids]*sc[j])]:
    r=diff@data['e'][cam,:,:3].T/dep[:,None];r[:,2]*=2;norm=np.linalg.norm(r,axis=1);pieces['P'].extend(np.sqrt(2*c.huber(norm)/(6*len(ids))))
    zz=(other@data['e'][cam,:,:3].T+data['e'][cam,:,3])[:,2];z=(zz-targetdepth)/(.01*dep);pieces['Z'].extend(np.sqrt(2*c.huber(abs(z),1)/(6*len(ids))))
  active_pairs=len(set(tuple(sorted((s['src'],s['dst']))) for s in self.lines))
  for s in self.lines:
   i,j=s['src'],s['dst'];uv=np.array(s['uv']);pp=c.unproject(uv,np.array(s['depth'])*sc[i],k[i],data['e'][i]);uvp,z,_=c.project(pp,k[j],data['e'][j],h,w);r=(uvp@np.array(s['coeff'][:2])+s['coeff'][2])/2;r=np.where(z>1e-6,r,1e6+abs(z)*1e6)
   count=sum(t['src']==i and t['dst']==j for t in self.lines);pieces['L'].extend(np.sqrt(2*c.huber(abs(r),1)/(max(1,active_pairs)*2*count*len(r))))
  out={k:np.array(v) for k,v in pieces.items()};out['prior']=np.sqrt(.002/6)*(x[:6]-1)
  if self.depth:out['A']=np.sqrt(2/2)*x[6:]/np.log(1.05)
  if self.E is not None:
   prior,mask=self.E;r=(data['depth']*sc[:,None,None]-prior)/(.05*data['depth']);v=[]
   for i in range(3):v.extend(np.sqrt(2*c.huber(abs(r[i][mask[i]]),1)/(3*mask[i].sum())))
   out['E']=np.array(v)
  return out
 def fun(self,x):
  p=self.parts(x);v=[p['P']/np.sqrt(self.norm['P']),p['prior']/np.sqrt(self.norm['P'])]
  if self.L:v.append(np.sqrt(self.wL/self.norm['L'])*p['L'])
  if self.Z:v.append(np.sqrt(self.wZ/self.norm['Z'])*p['Z'])
  if self.depth:v.append(p['A'])
  if self.E is not None:v.append(np.sqrt(.25/self.norm['E'])*p['E'])
  return np.concatenate(v)

def line_eval(data,lines,x):
 k=c.corrected_k(data['k'],x[:6].reshape(3,2));sc=np.exp(np.r_[0,x[6:]]) if len(x)>6 else np.ones(3);out={}
 for fold in [False,True]:
  rows=[]
  for s in lines:
   if s['validation']!=fold:continue
   pp=c.unproject(np.array(s['uv']),np.array(s['depth'])*sc[s['src']],k[s['src']],data['e'][s['src']]);uv,z,_=c.project(pp,k[s['dst']],data['e'][s['dst']],384,512);r=abs(uv@np.array(s['coeff'][:2])+s['coeff'][2]);a,b=np.array(s['target']);t=((uv-a)@(b-a))/np.sum((b-a)**2);rows.append({'structure':s['structure'],'direction':[s['src'],s['dst']],'distance_px':c.stats(r),'outside_segment_fraction':float(np.mean((t<0)|(t>1)))})
  out['validation' if fold else 'fit']=rows
 return out

def optimize(st,data,matches,lines,name,depth=False,L=False,Z=False,E=None,start=None,wL=.25,wZ=.25,save=True):
 train=m.subset(matches,~matches['validation']);prob=Problem(data,train,[s for s in lines if not s['validation']],depth,L,Z,E,wL,wZ)
 x0=np.r_[BETA,[0,0]] if depth else BETA.copy()
 if start is not None:x0[:6]=start
 history=[x0.copy()]
 def callback(intermediate_result):history.append(intermediate_result.x.copy())
 low=np.r_[np.full(6,c.LOW),[np.log(.95)]*2] if depth else np.full(6,c.LOW);hi=np.r_[np.full(6,c.HIGH),[np.log(1.05)]*2] if depth else np.full(6,c.HIGH)
 res=least_squares(prob.fun,x0,bounds=(low,hi),jac='3-point',max_nfev=200,ftol=1e-8,xtol=1e-8,gtol=1e-8,callback=callback)
 history.append(res.x.copy());scores=[float(prob.fun(x)@prob.fun(x)/2) for x in history];idx=int(np.argmin(scores));proposed=history[idx];ref=d.overlap_reference(data);b1=changed(data,BETA)[0];b1xyz=c.points(data,BETA);kb1=c.corrected_k(data['k'],BETA.reshape(3,2));size=384*512
 ref1={(i,j):c.project(b1xyz[i*size:(i+1)*size],kb1[j],data['e'][j],384,512)[2] for i,j in ref}
 # Each saved solver iterate audited; no validation-based selection.
 covs=[cover(data,x,ref) for x in history];feasible=[i for i,cov in enumerate(covs) if cov['passed']];chosen=min(feasible,key=lambda i:scores[i]) if feasible else 0
 after=geo(data,matches,proposed);before=geo(data,matches,x0)
 out={'name':name,'decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','converged':bool(res.success),'termination':res.message,'nfev':res.nfev,'njev':res.njev,'variables':len(res.x),'beta':proposed[:6].tolist(),'depth_scale':(np.exp(np.r_[0,proposed[6:]]) if depth else np.ones(3)).tolist(),'loss_before':scores[0],'loss_proposed':scores[idx],'normalizers':prob.norm,'geometry_before':before,'geometry_proposed':after,'line_proposed':line_eval(data,lines,proposed),'coverage_raw':covs[idx],'coverage_B1':cover(data,proposed,ref1),'selected_index':chosen,'selected_is_feasible':bool(feasible),'bound_limited':bool(np.any(proposed-low<1e-4)|np.any(hi-proposed<1e-4)),'history':[{'x':x.tolist(),'loss':loss,'coverage_pass':cov['passed']} for x,loss,cov in zip(history,scores,covs)]}
 out['loss_parts_proposed']={key:float(v@v/2) for key,v in prob.parts(proposed).items()}
 out['data_rank']=c.rank_info(approx_derivative(lambda x: np.r_[prob.parts(x)['P'],prob.parts(x)['L'] if L else [],prob.parts(x)['Z'] if Z else []],proposed,method='3-point')[:,None,:])
 out['gradient_norm_by_part']={key:float(np.linalg.norm(approx_derivative(lambda x:np.array([np.dot(prob.parts(x)[key],prob.parts(x)[key])/2]),proposed,method='3-point'))) for key in prob.parts(proposed)}
 root=st.path/'artifacts/arms'/name;root.mkdir(parents=True);c.json_write(root/'fit.json',out)
 if save:
  for state,x in [('initial',x0),('proposed',proposed),('selected',history[chosen]),('last',res.x)]:
   # Exact duplicate candidates use hard links, preserving separately reviewable paths.
   dest=root/state;equiv=next((root/s for s,y in [('initial',x0),('proposed',proposed),('selected',history[chosen])] if (root/s).exists() and np.array_equal(x,y)),None)
   if equiv is not None:shutil.copytree(equiv,dest,copy_function=os.link)
   else:out['projection_'+state]=export(st,data,x,dest)
 st.log('arm_completed',arm=name,beta=out['beta'],scale=out['depth_scale'],validation_3d=after['validation']['relative_3d']['median'])
 return out

def run_arms(st,depth=False,E=None):
 data,matches=load();obs=latest('G1')/'artifacts/observations';lines=json.loads((obs/'line_samples.json').read_text());rows=[]
 for L,Z,suffix in [(False,False,'P'),(True,False,'PL'),(False,True,'PZ'),(True,True,'PLZ')]:
  if E is not None and suffix not in ['P','PLZ']:continue
  rows.append(optimize(st,data,matches,lines,('D-' if depth else 'F-')+suffix+('+E' if E is not None else ''),depth,L,Z,E))
 st.finish({'decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','arms':rows},'# '+st.code+' 제약별 비교\n\n주 비교군을 모두 실행하고 실제 proposed와 자동 selected를 분리 보존했다. 지원 부족으로 효과 확정은 보류한다.\n\n'+table(rows))
def table(rows):
 text='| 비교군 | validation 3D median | validation Z median | coverage(raw) | 수렴 |\n| --- | --- | --- | --- | --- |\n'
 for r in rows:text+=f"| {r['name']} | {r['geometry_proposed']['validation']['relative_3d']['median']:.9f} | {r['geometry_proposed']['validation']['relative_z']['median']:.9f} | {r['coverage_raw']['maximum_loss_fraction']:.5%} | {r['converged']} |\n"
 return text

def main():
 code=sys.argv[1];st=Stage(code)
 try:
  if code=='G0':g0(st)
  elif code=='G1':g1(st)
  elif code=='G2':run_arms(st)
  elif code=='G3':run_arms(st,True)
  else:raise ValueError(code)
 except Exception as e:st.fail(e);raise
if __name__=='__main__':main()
