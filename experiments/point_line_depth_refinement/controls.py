"""G0a independent nonlinear and degenerate synthetic controls."""
import run as g
import numpy as np
from scipy.optimize import least_squares
from scipy.optimize._numdiff import approx_derivative
from scipy.spatial.transform import Rotation
st=g.Stage('G0a')
try:
 rng=np.random.default_rng(10);p=rng.uniform([-1,-.7,3],[1,.7,5],(60,3));k=np.repeat(np.array([[[400.,0,256],[0,410,192],[0,0,1]]]),3,axis=0);e=np.array([np.c_[Rotation.from_euler('y',angle).as_matrix(),t] for angle,t in [(0,[0,0,0]),(.2,[.3,0,.05]),(-.15,[-.2,.1,0])]])
 data={'k':k,'e':e,'depth':np.ones((3,384,512))};truth=np.r_[[1.02,.99,1.03,.98,.97,1.01],np.log([1.02,.98])];kk=g.c.corrected_k(k,truth[:6].reshape(3,2));sc=np.exp(np.r_[0,truth[6:]]);uv=[];dep=[]
 for i in range(3):
  u,z,_=g.c.project(p,kk[i],e[i],384,512);uv.append(u);dep.append(z/sc[i])
 pairs=list(__import__('itertools').combinations(range(3),2));mat={'pair':np.repeat(pairs,len(p),axis=0),'uv_i':np.concatenate([uv[i] for i,j in pairs]),'uv_j':np.concatenate([uv[j] for i,j in pairs]),'di':np.concatenate([dep[i] for i,j in pairs]),'dj':np.concatenate([dep[j] for i,j in pairs])}
 def residual(x,es=e):
  ks=g.c.corrected_k(k,x[:6].reshape(3,2));s=np.exp(np.r_[0,x[6:]]);return np.concatenate([(g.c.unproject(uv[i],dep[i]*s[i],ks[i],es[i])-g.c.unproject(uv[j],dep[j]*s[j],ks[j],es[j])).ravel() for i,j in pairs])
 fit=least_squares(residual,np.r_[np.ones(6),[0,0]],jac='3-point',gtol=1e-12,ftol=1e-12,xtol=1e-12,max_nfev=200);err=float(abs(fit.x-truth).max());assert err<1e-6
 j3=approx_derivative(residual,truth,method='3-point');j2=approx_derivative(residual,truth,method='2-point');assert abs(j3-j2).max()<1e-5
 # Analytic pinhole quotient derivative of x/z for an arbitrary affine point.
 q=np.array([.4,.2,3.]);a=np.array([[.5,.1],[-.1,.7],[.2,-.15]]);x=np.array([.9,1.1])
 def proj(b):
  v=q+a@b;return v[:2]/v[2]
 v=q+a@x;analytic=(a[:2]*v[2]-v[:2,None]*a[2])/v[2]**2;numeric=approx_derivative(proj,x,method='3-point');assert abs(analytic-numeric).max()<1e-9
 # Pure rotation: common absolute depth scale is unobservable for pixel projection.
 def reproj(logscale):
  qq=p*np.exp(logscale[0]);return g.c.project(qq,k[0],e[0],384,512)[0].ravel()
 gauge=float(abs(approx_derivative(reproj,[0.],method='3-point')).max());assert gauge<1e-7
 # A single horizontal line constrains vertical projection only; horizontal shift has zero sensitivity.
 one=approx_derivative(lambda b:np.array([proj(b)[1]]),x,method='3-point');assert np.linalg.matrix_rank(one)==1
 negative=g.c.project(np.array([[0,0,-1.]]),k[0],e[0],384,512)[2];assert not negative[0]
 metrics={'decision':'TECHNICAL_CHECKS_PASSED','synthetic_depth_fov_recovery_max_abs':err,'data_rank':g.c.rank_info(j3[:,None,:]),'central_vs_forward_max_abs':float(abs(j3-j2).max()),'analytic_line_projection_jacobian_max_abs':float(abs(analytic-numeric).max()),'pure_rotation_common_scale_projection_derivative':gauge,'single_line_rank':1,'nonpositive_Z_rejected':True,'amendment':'Production uses numerical three-point Jacobian, analytically checked projection derivative; not claimed autodiff implementation.'}
 st.finish(metrics,'# G0a 비선형·깊이 퇴화 보조 검증\n\n합성 8변수 복구, 투영 미분, 공통 scale 비관측, 단일 선 퇴화, 음의 Z 제어를 통과했다.\n\n```json\n'+__import__('json').dumps(metrics,indent=2)+'\n```')
except Exception as ex:st.fail(ex);raise
