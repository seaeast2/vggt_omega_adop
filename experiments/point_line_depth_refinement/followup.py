"""G4 external prior and G5 pre-fixed sensitivity sweeps."""
import run as g
import numpy as np,json

def g4(st):
 data,matches=g.load();obs=g.latest('G1')/'artifacts/observations';src=g.ROOT/'results/point_line_depth_refinement/external_moge2';external=np.load(src/'depth.npz');dep=external['depth'];good=external['mask'].astype(bool)&np.isfinite(dep)&(dep>0)
 tiles=np.load(obs/'fit_tiles.npz')['tiles'];y,x=np.indices((384,512));fit=np.stack([tiles[i,y//32,x//32]==1 for i in range(3)])&good
 for i in range(3):fit[i]&=np.isfinite(data['conf'][i])&(data['conf'][i]>=np.percentile(data['conf'][i],10))
 scale=float(np.median((data['depth']/dep)[fit]));aligned=dep*scale
 # Fixed 4px raster stride for bounded computation; all fit pixels used for scale calibration.
 fit&=(y[None]%4==0)&(x[None]%4==0)
 assert all(fit.reshape(3,-1).sum(1)>0)
 np.savez_compressed(st.path/'artifacts/external_prior.npz',depth=aligned,mask=fit,scale=scale)
 g.c.json_write(st.path/'artifacts/external_provenance.json',json.loads((src/'provenance.json').read_text())|{'common_scale':scale,'fit_pixel_counts':fit.reshape(3,-1).sum(1).tolist(),'fit_sampling':'fixed 4px stride; scale uses all fit pixels; validation tiles excluded'})
 g.run_arms(st,True,(aligned,fit))
def g5(st):
 data,matches=g.load();lines=json.loads((g.latest('G1')/'artifacts/observations/line_samples.json').read_text());rows=[]
 for depth in [False,True]:
  for L,Z,label in [(False,False,'P'),(True,False,'PL'),(False,True,'PZ'),(True,True,'PLZ')]:rows.append(g.optimize(st,data,matches,lines,('D-' if depth else 'F-')+label+'_start_raw',depth,L,Z,start=np.ones(6),save=False))
 for depth in [False,True]:
  for kind in ['L','Z']:
   for weight in [.1,.25,1.]:rows.append(g.optimize(st,data,matches,lines,f'sensitivity_{depth}_{kind}_{weight}',depth,True,True,wL=weight if kind=='L' else .25,wZ=weight if kind=='Z' else .25,save=False))
 g.c.json_write(st.path/'evaluation/sensitivity.json',rows)
 g.c.json_write(st.path/'evaluation/additional_window.json',{'status':'separate G5a','indices':[100,110,120]})
 st.finish({'decision':'LOW_SUPPORT_DIAGNOSTIC_ONLY','arms':rows},'# G5 초기값·가중치 안정성\n\nβ=1 초기값 8군과 L/Z 가중치 0.1/0.25/1.0 민감도를 한 항씩 비교했다. 주 결과 선택에는 사용하지 않았다. 새 실내 구간은 G5a로 별도 기록한다.\n\n'+g.table(rows))
if __name__=='__main__':
 import sys
 code=sys.argv[1];st=g.Stage(code)
 try:
  if code=='G4':g4(st)
  elif code=='G5':g5(st)
  else:raise ValueError(code)
 except Exception as e:st.fail(e);raise
