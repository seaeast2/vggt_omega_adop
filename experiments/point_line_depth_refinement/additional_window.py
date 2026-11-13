"""G5a: preselected additional indoor window, frozen RGB reviewed line observations."""
import run as g
import json,numpy as np,itertools,hashlib,cv2,tarfile
st=g.Stage('G5a')
try:
 src=g.ROOT/'results/point_line_depth_refinement/extra_indoor_100_110_120';z=np.load(src/'raw.npz');dep=z['depth'][0,...,0].astype(float);rgb=np.rint(z['images'][0].transpose(0,2,3,1)*255).astype('uint8');n,h,w=dep.shape
 data={'dataset':'tum-freiburg1_desk-window100_110_120','depth':dep,'conf':z['depth_conf'][0],'k':z['intrinsics'][0].astype(float),'e':z['extrinsics'][0].astype(float),'rgb':rgb,'raw_rgb':rgb.reshape(-1,3),'uv':np.tile(np.indices((h,w))[::-1].reshape(2,-1).T,(3,1)),'fid':np.repeat(np.arange(3,dtype=np.int16),h*w)}
 data['centers']=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in data['e']])
 with tarfile.open(g.ROOT/'data/pointmap_refinement/tum/rgbd_dataset_freiburg1_desk.tgz') as tar:
  txt=[s.split() for s in tar.extractfile('rgbd_dataset_freiburg1_desk/rgb.txt').read().decode().splitlines() if s.strip() and not s.startswith('#')]
  rows=json.loads((src/'frames.json').read_text())
  for row in rows:assert row['source_member']=='rgbd_dataset_freiburg1_desk/'+txt[row['index']][1]
 matches,support=g.m.extract(data,st.path/'artifacts/matches',st);train=g.m.subset(matches,~matches['validation']);a,b,weights,_=g.c.build_system(data,train);beta,history,conv=g.c.solve_irls(a,b,weights);g.BETA=beta
 lines=[];tracks=[];candidates=[]
 for im in rgb:
  ls=cv2.createLineSegmentDetector().detect(cv2.cvtColor(im,cv2.COLOR_RGB2GRAY))[0][:,0].astype(float);ls=ls[np.linalg.norm(ls[:,:2]-ls[:,2:],axis=1)>=40][:100];candidates.append(ls)
 # Reviewed in raw RGB before fitting this window: same left book cover edge and telephone bezel edge.
 specs={'book_left':{0:18,1:31,2:26},'telephone_left':{0:20,1:35,2:23}}
 for name,obs in specs.items():
  val=int.from_bytes(hashlib.sha256(('0:'+name).encode()).digest()[:8],'little')%5==0;tracks.append({'structure':name,'validation':val,'observations':{str(i):candidates[i][idx].tolist() for i,idx in obs.items()},'reviewer':'Codex RGB visual review before G5a optimization'})
  for i,j in itertools.permutations(range(3),2):
   line=candidates[i][obs[i]].reshape(2,2);target=candidates[j][obs[j]].reshape(2,2);uv=line[0]+np.linspace(.1,.9,max(3,int(.8*np.linalg.norm(line[1]-line[0])/8)+1))[:,None]*(line[1]-line[0]);dd,good,_=g.m.depth_samples(data,i,uv)
   if not val:
    for side,field in [(0,'uv_i'),(1,'uv_j')]:
     pp=matches[field][matches['validation']&(matches['pair'][:,side]==i)]
     if len(pp):good&=np.linalg.norm(uv[:,None]-pp[None],axis=2).min(1)>2
   coeff=np.cross(np.r_[target[0],1],np.r_[target[1],1]);coeff/=np.linalg.norm(coeff[:2])
   if good.any():lines.append({'structure':name,'src':i,'dst':j,'uv':uv[good].tolist(),'depth':dd[good].tolist(),'target':target.tolist(),'coeff':coeff.tolist(),'validation':val})
 g.c.json_write(st.path/'artifacts/line_tracks.json',tracks);g.c.json_write(st.path/'artifacts/line_samples.json',lines);g.c.json_write(st.path/'artifacts/provenance.json',json.loads((src/'provenance.json').read_text()))
 for i,im in enumerate(rgb):
  im=im.copy()
  for tr in tracks:
   q=np.rint(tr['observations'][str(i)]).astype(int).reshape(2,2);cv2.line(im,tuple(q[0]),tuple(q[1]),(255,0,255) if tr['validation'] else (0,255,0),2)
  g.c.image_write(st.path/f'artifacts/figures/annotation_camera_{i}.png',im)
 g.export(st,data,np.ones(6),st.path/'artifacts/baselines/raw');g.export(st,data,beta,st.path/'artifacts/baselines/C3a_method_proposed')
 results=[]
 for depth in [False,True]:
  for L,Z,label in [(False,False,'P'),(True,False,'PL'),(False,True,'PZ'),(True,True,'PLZ')]:results.append(g.optimize(st,data,matches,lines,('D-' if depth else 'F-')+label,depth,L,Z))
 st.finish({'decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','frame_indices':[100,110,120],'baseline_beta':beta.tolist(),'point_support':support,'line_tracks':tracks,'line_support_passed':False,'arms':results,'wall_evaluation':'NOT_APPLICABLE: no shared unobstructed wall in this view; desk scene'},'# G5a 고정 추가 실내 구간\n\n100/110/120 원본 3장을 함께 추론하고 기존과 동일한 점 매칭·FoV 방법으로 기준선을 생성한 뒤 8군을 비교했다. 두 선 구조만 확인돼 지원 부족 진단이다. 벽 ROI는 보이지 않아 평가하지 않았다.\n\n'+g.table(results))
except Exception as e:st.fail(e);raise
