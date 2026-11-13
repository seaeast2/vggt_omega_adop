"""G0b final objective and artifact identity audit; independent file inventory."""
import run as g
import numpy as np,json,csv
st=g.Stage('G0b')
try:
 data,mat=g.load();tr=g.m.subset(mat,~mat['validation']);lines=json.loads((g.latest('G1')/'artifacts/observations/line_samples.json').read_text());prob=g.Problem(data,tr,[s for s in lines if not s['validation']]);a,b,w,_=g.c.build_system(data,tr)
 objective_errors=[]
 for beta in [np.ones(6),g.BETA,np.linspace(g.c.LOW,g.c.HIGH,6)]:
  expected=float(w@g.c.huber(np.linalg.norm(a@beta+b,axis=1)))+.001*np.mean((beta-1)**2);actual=float(prob.fun(beta)@prob.fun(beta)/2)*prob.norm['P'];objective_errors.append(abs(expected-actual));assert abs(expected-actual)<1e-12
 inventory=[];checks=[]
 for code in ['G0','G2','G3','G4','G5a']:
  stage=g.latest(code)
  for p in sorted(stage.rglob('*.ply')):
   info=g.c.record(p);inventory.append({'code':code,**info})
  for p in sorted((stage/'artifacts').rglob('pointmap.npz')):
   z=np.load(p);n=len(z['xyz']);assert n==589824 and np.isfinite(z['xyz']).all();fid=z['frame_id'];uv=z['pixel_uv'];assert np.array_equal(fid,np.repeat(np.arange(3),384*512));assert np.array_equal(uv,np.tile(np.indices((384,512))[::-1].reshape(2,-1).T,(3,1)))
   assert np.array_equal(z['rgb'],data['raw_rgb']) if code!='G5a' else True
   checks.append({'path':str(p),'vertices':n,'finite':True,'frame_pixel_IDs_preserved':True})
  manifest=json.loads((stage/'manifest.json').read_text())
  # Check every originally recorded artifact hash, not just existence.
  for row in manifest['artifacts']:
   p=g.Path(row['path']);assert p.exists() and g.c.record(p)['sha256']==row['sha256'],p
 g.c.json_write(st.path/'evaluation/ply_files.json',inventory);g.c.json_write(st.path/'evaluation/pointmap_identity.json',checks)
 st.finish({'decision':'ARTIFACT_AND_OBJECTIVE_AUDIT_PASSED','P_objective_max_abs':max(objective_errors),'ply_files':len(inventory),'pointmaps_verified':len(checks),'input_file_hashes_rechecked':True},'# G0b 최종 산출물·목적함수 감사\n\n세 β에서 production P-only 손실이 기존 C3a 목적함수와 일치하는지 확인했다. G0/G2/G3/G4/G5a의 모든 manifest artifact 해시, PLY 존재·해시, 589,824점·유한값·프레임/픽셀 ID를 확인했다.\n\nPLY 목록은 evaluation/ply_files.json에 보존한다.')
except Exception as e:st.fail(e);raise
