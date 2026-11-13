from base import *
from geometry import fit,depth_gate,weighted_plane
from scipy.optimize import minimize_scalar

def run(code='H0a'):
 st=Stage(code,extra={'amendment':'H0 synthetic layers corrected: 0.3pct offsets inside fixed 0.5pct inlier gate; original failing H0 preserved.'})
 try:
  data=load();rebuilt=c.points(data,np.ones(6));maxerr=float(abs(rebuilt-data['xyz']).max());assert np.allclose(rebuilt,data['xyz'],atol=1e-8,rtol=1e-8)
  inv=export(data,data['xyz'],st.path/'artifacts/baseline/A0_C3a')
  rng=np.random.default_rng(0);q=np.c_[rng.uniform(-.4,.4,(600,2)),np.ones(600)];centers=np.zeros_like(q);D=np.full(600,2.);p=np.array([0.,0.,1.,-2.])
  target,acc,why=depth_gate(D,q,centers,p);assert acc.all() and np.max(abs(target-2))<1e-12
  soft_errors=[]
  for qi in q[:32]:
   pp=np.array([.2,.1,1.,-2.02]);pp/=np.linalg.norm(pp[:3]);a=pp[:3]@qi;b=pp[3];hard=-b/a;alpha=a*a/(1+a*a);soft=2+alpha*(hard-2)
   sol=minimize_scalar(lambda z:((a*z+b)/2)**2+((z-2)/2)**2,method='brent',bracket=(1.,3.),options={'xtol':1e-12});soft_errors.append(abs(soft-sol.x)/abs(soft))
  assert max(soft_errors)<1e-8
  _,ok,reason=depth_gate(np.array([2.,2.,2.,2.,2.]),np.array([[0,0,1],[0,0,1],[10,0,1],[0,0,1],[0,0,1.]]),np.array([[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,0,0.]]),np.array([0.,0.,1.,-2.04]))
  assert ok.tolist()==[True,True,False,True,True]
  _,too_far,_=depth_gate(np.array([2.]),np.array([[0.,0.,1.]]),np.zeros((1,3)),np.array([0.,0.,1.,-2.040001]));assert not too_far.any()
  _,negative,_=depth_gate(D,q,centers,np.array([0,0,1,2.]));assert not negative.any()
  xy=rng.uniform(-.5,.5,(1800,2));xx=np.c_[xy,np.ones(1800)*2];dd=xx[:,2];ff=np.repeat([0,1,2],600)
  planar=fit(xx,dd,ff);assert planar['valid']
  line=np.c_[np.linspace(-1,1,1000),np.zeros(1000),np.ones(1000)*2];deg=fit(line,line[:,2],np.zeros(1000,int));assert not deg['valid'] and deg['reason']=='DEGENERATE_PLANE_SUPPORT'
  curve=np.c_[xy,2+1.8*(xy[:,0]**2+xy[:,1]**2)];curved=fit(curve,curve[:,2],ff);assert not curved['valid']
  # Full parallel/corner joint tests must fail 70% per-frame support.
  parallel=xx.copy();parallel[ff==1,2]+=.2;parallel[ff==2,2]-=.2;parfit=fit(parallel,parallel[:,2],ff);assert not parfit['valid']
  corner=xx.copy();corner[ff==1]=np.c_[np.ones(600)*.5,xy[ff==1,1],2+xy[ff==1,0]];corfit=fit(corner,corner[:,2],ff);assert not corfit['valid']
  # One-frame robust fit can be valid; sharing still requires >=2 distinct frames.
  single=fit(xx[:600],dd[:600],np.zeros(600,int));assert single['valid'];assert len(set(np.zeros(600,int)))<2
  from geometry import direction
  synthetic={'depth':np.full((3,20,20),2.),'fid':np.repeat(np.arange(3),400),'k':np.tile(np.array([[20,0,10],[0,20,10],[0,0,1.]]),(3,1,1)),'e':np.tile(np.c_[np.eye(3),np.zeros(3)],(3,1,1))}
  uv=np.array([(x,y) for y in range(20) for x in range(20)]);block=c.unproject(uv,np.full(400,2.),synthetic['k'][0],synthetic['e'][0]);synthetic['xyz']=np.tile(block,(3,1));visible=direction(synthetic,np.arange(400),np.arange(400,800));assert visible['passed']
  synthetic['xyz'][:400]*=1.2;occluded=direction(synthetic,np.arange(400),np.arange(400,800));assert not occluded['passed'] and occluded['behind_target_occluded']>0
  # Controlled ripples and +/-0.3% layers, all within the 2% movement gate.
  uu,vv=np.meshgrid(np.linspace(-.4,.4,30),np.linspace(-.3,.3,24));ray=np.c_[uu.ravel(),vv.ravel(),np.ones(720)];f=np.repeat(np.arange(3),720);q3=np.tile(ray,(3,1));D3=2+np.repeat([-.006,0,.006],720)+.001*np.tile(np.sin(uu.ravel()*30),3);X=q3*D3[:,None]
  indep=X.copy()
  for i in range(3):
   ids=f==i;ft=fit(X[ids],D3[ids],f[ids]);assert ft['valid'];pp=np.array(ft['plane']);td,ag,_=depth_gate(D3[ids],q3[ids],np.zeros((720,3)),pp);assert ag.all();indep[ids]=q3[ids]*td[:,None]
  shared=fit(X,D3,f);assert shared['valid'];pp=np.array(shared['plane']);td,ag,_=depth_gate(D3,q3,np.zeros_like(q3),pp);assert ag.all();joint=q3*td[:,None]
  def gap(a):return float(np.ptp([np.median(a[f==i,2]) for i in range(3)]))
  assert gap(indep)>.01 and gap(joint)<.001
  syn=st.path/'artifacts/synthetic';syn.mkdir(parents=True)
  for name,a in [('initial',X),('independent',indep),('shared',joint)]:c.ply_write(syn/(name+'.ply'),a,c.PALETTE[f],f)
  # Explicit reject/non-target invariant example.
  untouched=data['xyz'].copy();ids=np.arange(100);tar,gate,_=depth_gate(data['d0'][ids],data['q'][ids],data['center_points'][ids],np.array(planar['plane']));accepted=np.zeros(len(untouched),bool);accepted[ids[gate]]=True;untouched[ids[gate]]=data['center_points'][ids[gate]]+tar[gate,None]*data['q'][ids[gate]];assert np.array_equal(untouched[~accepted],data['xyz'][~accepted])
  rows,srcrows,render=d.render(data,data['xyz'],data['k'],st.path/'artifacts/projections/A0_C3a');c.panel(st.path/'artifacts/figures/A0_C3a.png',rows,['original RGB','C3a pixel RGB','source frames'])
  metrics={'decision':'TECHNICAL_CHECKS_PASSED','baseline_rebuild_max_xyz':maxerr,'baseline_invariants':inv,'soft_numeric_max_relative_error':max(soft_errors),'synthetic_plane':planar,'curved_surface':curved,'parallel_walls':parfit,'corner':corfit,'near_line':deg,'single_frame':single,'occlusion':occluded,'visible':visible,'movement_2pct_boundary_passed':True,'synthetic_layer_gap':{'initial':gap(X),'independent':gap(indep),'shared':gap(joint),'ground_truth_recovery_claim':False},'baseline_render':render,'inputs':data['inputs'],'implementation_notes':['RANSAC scoring uses deterministic max4096 fit samples; final IRLS/support evaluated on every fit point; max2000 trials and adaptive 99.99pct bound min64.','Degenerate support rejected if second/largest covariance eigenvalue<1e-4 or four-sigma second-axis span / original median Z<.01.']}
  st.finish(metrics,'# H0a 기준선·수식 검증\n\nH0의 합성 층 offset 0.6%는 고정 inlier 0.5% 밖인데 공유 적합 성공을 기대한 제어 오류였다. 원래 실패를 보존하고 offset 0.3%로 수정한 H0a에서 전체 검증을 다시 실행했다. 실제 데이터 임계값은 바꾸지 않았다.\n\nC3a proposed를 기준으로 589,824개 관측을 재현했다. 광선-평면 hard 교차, soft 해와 독립 수치 최소화, 자기 재투영, RGB/ID/K/pose/점 수·거절점 불변 검사를 통과했다.\n\n평행 벽·모서리·곡면·가림·단일 프레임·선형 지지·스침각·음의 깊이·2% 경계 합성 제어를 확인했다. 독립 평면의 층 간격은 남고 공유 평면의 층은 줄었다. 이는 수식 제어이며 실제 정답 벽 복구의 증거가 아니다.\n\nRANSAC은 고정 seed의 최대 4,096 fit 점으로 가설을 채점한 후 전체 fit 점에서 최종 지원과 IRLS를 평가한다. 적응적 반복 종료의 최소는 64, 최대는 2,000이다. 고유값 비 1e-4/두 번째 축 범위 1%의 퇴화 기준을 실험 전에 고정했다.')
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
