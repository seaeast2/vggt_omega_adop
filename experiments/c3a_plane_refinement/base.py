"""H series provenance, frozen C3a baseline, and invariant-preserving exports."""
from pathlib import Path
import sys, json, time, shutil, subprocess, platform, resource, traceback, os
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'camera_fov_alignment'))
import common as c
import diagnostics as d
ROOT=c.ROOT
FAMILY=ROOT/'results/c3a_plane_refinement'
DOC=ROOT/'docs/experiments/c3a_plane_refinement'
BASE=ROOT/'results/camera_fov_alignment/tum-freiburg1_desk-C3a-20261112-001/stages/C3a/artifacts/fit/proposed_not_selected/pointmap.npz'
CFG={'seed':0,'normal_window':7,'normal_sensitivity_window':21,'confidence_percentile':10,'mask_erosion_px':3,'image_border_px':8,'normal_kmeans_clusters':5,'normal_kmeans_iterations':10,'minimum_area_fraction':.005,'minimum_frame_fit_support':100,'minimum_inlier_fraction':.70,'ransac_iterations':2000,'huber_irls_iterations':20,'inlier_relative_distance':.005,'huber_delta':.005,'normal_angle_degree':15,'association_depth_gate':.03,'association_overlap':.20,'association_min_pixels':100,'association_centroid_distance':.01,'max_relative_move':.02,'minimum_ray_cosine':.2,'coverage_loss_limit':.005,'degenerate_second_first_eigen_ratio':1e-4,'minimum_second_axis_span_depth':.01,'fit_tiles':[16,12],'sam_model':'ViT-H','detector':'IDEA-Research/grounding-dino-tiny (Swin-T)','box_threshold':.25,'text_threshold':.2,'prompt':'wall.','multimask_output':False,'execution_context':'host CPU geometry; H1 CUDA outside sandbox','gt_accuracy_evaluated':False}

def latest(code):
 ps=sorted(FAMILY.glob(f'tum-freiburg1_desk-{code}-*/stages/{code}'))
 ps=[p for p in ps if json.loads((p/'manifest.json').read_text()).get('status')=='completed']
 assert ps,code
 return ps[-1]

class Stage(c.Stage):
 def __init__(self,code,parents=(),extra=None):
  self.code=code;self.dataset='tum-freiburg1_desk';date=c.stamp()[:10].replace('-','');seq=1
  while (FAMILY/f'{self.dataset}-{code}-{date}-{seq:03}').exists():seq+=1
  self.run_id=f'{self.dataset}-{code}-{date}-{seq:03}'
  self.path=FAMILY/self.run_id/'stages'/code;self.path.mkdir(parents=True)
  self.doc=DOC/code/self.run_id;self.doc.mkdir(parents=True)
  for name in ['logs','evaluation','artifacts/source','artifacts/figures']:(self.path/name).mkdir(parents=True)
  self.started=time.perf_counter();self.config=CFG|{'experiment_code':code,'run_id':self.run_id}|(extra or {})
  self.manifest={'status':'running','experiment_code':code,'run_id':self.run_id,'started_at':c.stamp(),'project_commit_at_start':subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip(),'parents':[c.record(p/'manifest.json') for p in parents],'baseline':c.record(BASE),'gt_accuracy_evaluated':False}
  c.json_write(self.path/'config_resolved.json',self.config)
  c.json_write(self.path/'environment.json',{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,'opencv':c.cv2.__version__,'scipy':__import__('scipy').__version__,'execution_context':self.config['execution_context'],'thread_env':{k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS']}})
  src=Path(__file__).parent
  for p in sorted(src.rglob('*.py')):
   dest=self.path/'artifacts/source'/p.relative_to(src);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
  for p in [ROOT/'experiments/camera_fov_alignment/common.py',ROOT/'experiments/camera_fov_alignment/diagnostics.py',ROOT/'docs/c3a_planargs_plane_refinement_experiment_plan.md']:
   shutil.copy2(p,self.path/'artifacts/source'/p.name)
  self.save_manifest();self.log('registered',config=self.config)

def load():
 data=c.load_data('tum-freiburg1_desk')
 with np.load(BASE) as z:
  data['k']=z['intrinsics'].copy();data['xyz']=z['xyz'].copy();data['beta']=z['beta'].copy()
  for key,target in [('frame_id','fid'),('pixel_uv','uv'),('rgb','raw_rgb'),('extrinsics','e')]:assert np.array_equal(z[key],data[target]),key
 data['inputs'].append(c.record(BASE))
 n,h,w=data['depth'].shape
 data['q']=np.vstack([np.column_stack([data['uv'][i*h*w:(i+1)*h*w],np.ones(h*w)])@np.linalg.inv(data['k'][i]).T@np.linalg.inv(data['e'][i,:,:3]).T for i in range(n)])
 data['center_points']=data['centers'][data['fid']]
 data['d0']=data['depth'].ravel();data['ids']=np.arange(n*h*w)
 return data

def export(data,xyz,out,accepted=None,local=None,shared=None,target_depth=None):
 out.mkdir(parents=True,exist_ok=True);n=len(xyz)
 if accepted is None:accepted=np.zeros(n,bool)
 assert xyz.shape==data['xyz'].shape and np.isfinite(xyz).all()
 assert np.array_equal(xyz[~accepted],data['xyz'][~accepted])
 Z=np.empty(n);err=0.
 for i in range(3):
  sel=data['fid']==i;uv,z,_=c.project(xyz[sel],data['k'][i],data['e'][i],384,512);Z[sel]=z
  err=max(err,float(np.max(abs(uv-data['uv'][sel]))))
 assert err<1e-5,err
 np.savez_compressed(out/'pointmap.npz',xyz=xyz,depth=Z,depth_initial=data['d0'],observation_id=data['ids'],frame_id=data['fid'],pixel_uv=data['uv'],rgb=data['raw_rgb'],intrinsics=data['k'],extrinsics=data['e'],beta=data['beta'],accepted=accepted,rejected=~accepted,local_plane_id=local if local is not None else np.full(n,-1),shared_plane_id=shared if shared is not None else np.full(n,-1),target_depth=target_depth if target_depth is not None else data['d0'],original_to_corrected=data['ids'])
 c.ply_write(out/'pixel_rgb.ply',xyz,data['raw_rgb'],data['fid']);c.ply_write(out/'frame_colors.ply',xyz,c.PALETTE[data['fid']],data['fid'])
 with np.load(out/'pointmap.npz') as z:
  for key,target in [('observation_id','ids'),('frame_id','fid'),('pixel_uv','uv'),('rgb','raw_rgb'),('intrinsics','k'),('extrinsics','e')]:assert np.array_equal(z[key],data[target]),key
 return {'all_invariants_passed':True,'self_projection_max_pixel':err,'point_count':n,'unchanged_xyz_rejected_bitwise':True}

def commit_stage(code):
 # Called explicitly by shell, not during experiment execution.
 pass
