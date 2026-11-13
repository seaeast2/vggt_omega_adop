"""I-series contracts and geometry. All geometry is float64 in Omega world units."""
from __future__ import annotations
import hashlib, itertools, json, os, platform, resource, shutil, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/camera_fov_alignment'))
import common as c
import matching as m
FAMILY = ROOT/'results/global_planar_pointmap'
DOC = ROOT/'docs/experiments/global_planar_pointmap'
SOURCE = Path(__file__).parent
HIST = ROOT/'results/camera_fov_alignment/tum-freiburg1_desk-C3a-20261112-001/stages/C3a/artifacts/fit'
EXTRA = ROOT/'results/point_line_depth_refinement/extra_indoor_100_110_120'
CFG = dict(seed=0, schema_version='1.0', prompt='wall. floor. ceiling. door. window. table. cabinet. shelf. screen. whiteboard. blackboard.',
    box_threshold=.25, text_threshold=.2, points_per_side=32, points_per_batch=16, crop_n_layers=0,
    pred_iou_thresh=.88, stability_score_thresh=.95, box_nms_thresh=.7, crop_nms_thresh=.7,
    minimum_area_fraction=.001, minimum_fit=50, inlier_scale=.005, minimum_inlier_fraction=.7,
    ransac_iterations=2000, irls_iterations=20, minimum_ray_cosine=1e-8, max_relative_move=None,
    normal_windows=[7,21], fit_erosion_px=3, holdout_halo_px=3, normal_holdout_halo_px=10,
    fit_sample_cap=4096, solve_sample_per_plane_frame=96, outer_iterations=20, inner_max_nfev=200,
    relative_decrease=1e-5, assignment_change=.001, patience=3, coverage_loss_limit=.005,
    pixel_scale=2., angle_scale_degree=15., association_angle_degree=15., association_overlap=.2,
    lambda_image=.2, lambda_raw=1., lambda_normal=.05, lambda_cross=.2, lambda_edge=.1,
    lambda_struct=.05, lambda_complex=.02, lambda_unknown=.6,
    gt_status='GT_NOT_EVALUATED', evaluation_annotation='NONE: no surface GT; no manual ROI input',
    fov_policy='historical C3a reproduced; main fit removes holdout contamination if present')

def ahash(a):
    a=np.ascontiguousarray(a)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()

def latest(code,dataset='tum-freiburg1_desk'):
    ps=sorted(FAMILY.glob(f'{dataset}-{code}-*/stages/{code}'))
    ps=[p for p in ps if (p/'manifest.json').exists() and json.loads((p/'manifest.json').read_text())['status']=='completed']
    if not ps: raise FileNotFoundError(f'No completed {dataset} {code}')
    return ps[-1]

class Stage:
    def __init__(self,code,dataset='tum-freiburg1_desk',parents=(),extra=None):
        self.code,self.dataset=code,dataset
        date=c.stamp()[:10].replace('-','');seq=1
        while (FAMILY/f'{dataset}-{code}-{date}-{seq:03}').exists(): seq+=1
        self.run_id=f'{dataset}-{code}-{date}-{seq:03}'
        self.path=FAMILY/self.run_id/'stages'/code; self.path.mkdir(parents=True)
        self.doc=DOC/code/self.run_id; self.doc.mkdir(parents=True)
        for p in ['logs','evaluation','artifacts/source','artifacts/figures']: (self.path/p).mkdir(parents=True)
        self.started=time.perf_counter();self.config=CFG|dict(experiment_code=code,dataset=dataset,run_id=self.run_id)|(extra or {})
        if code!='I0':
            frozen=json.loads((latest('I0')/'artifacts/contract/config_resolved.json').read_text())
            self.config|=frozen
        self.manifest=dict(status='running',run_id=self.run_id,experiment_code=code,dataset=dataset,
            started_at=c.stamp(),parents=[c.record(p/'manifest.json') for p in parents],
            project_commit_at_start=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            gt_accuracy_evaluated=False,completion_criteria_met=False)
        for p in SOURCE.rglob('*.py'):
            dest=self.path/'artifacts/source'/p.relative_to(SOURCE);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        for name in ['common.py','matching.py']:
            shutil.copy2(ROOT/'experiments/camera_fov_alignment'/name,self.path/'artifacts/source'/name)
        shutil.copy2(ROOT/'docs/vggt_omega_global_planar_pointmap_experiment_plan.md',self.path/'artifacts/source/plan.md')
        c.json_write(self.path/'config_resolved.json',self.config)
        c.json_write(self.path/'environment.json',dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,
            scipy=__import__('scipy').__version__,opencv=c.cv2.__version__,execution_context='CPU geometry; GPU I1 must run host outside sandbox',
            thread_env={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS']}))
        c.json_write(self.path/'manifest.json',self.manifest);self.log('registered',run_id=self.run_id)
    def log(self,event,**data):
        row=json.dumps(dict(time=c.stamp(),event=event)|data,ensure_ascii=False)
        print(row,flush=True)
        with (self.path/'logs/run.log').open('a') as f:f.write(row+'\n')
    def finish(self,metrics,report,criteria=True):
        metrics|=dict(elapsed_seconds=time.perf_counter()-self.started,process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                      gt_status='GT_NOT_EVALUATED',completion_criteria_met=criteria)
        c.json_write(self.path/'evaluation/metrics.json',metrics);self.log('completed',decision=metrics['decision'],criteria=criteria)
        self.manifest|=dict(status='completed',execution_completed=True,completion_criteria_met=criteria,decision=metrics['decision'],ended_at=c.stamp())
        self.manifest['artifacts']=[c.record(p) for p in sorted(self.path.rglob('*')) if p.is_file() and p.name!='manifest.json']
        c.json_write(self.path/'manifest.json',self.manifest)
        (self.doc/'report.md').write_text(report+f'\n\nStage: `{self.path.relative_to(ROOT)}`. GT_NOT_EVALUATED.\n')
        for name in ['manifest.json','config_resolved.json','environment.json']:shutil.copy2(self.path/name,self.doc/name)
        for p in (self.path/'evaluation').rglob('*.json'):
            dst=self.doc/'evaluation'/p.relative_to(self.path/'evaluation');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
        shutil.copy2(self.path/'logs/run.log',self.doc/'run.log')
        shutil.copytree(self.path/'artifacts/figures',self.doc/'figures',dirs_exist_ok=True)
    def fail(self,e):
        self.log('failed',error=str(e));self.manifest|=dict(status='failed',error=str(e),traceback=traceback.format_exc(),ended_at=c.stamp())
        c.json_write(self.path/'manifest.json',self.manifest);shutil.copy2(self.path/'manifest.json',self.doc/'manifest.json')
        (self.doc/'report.md').write_text(f'# {self.code} 실패\n\n실패 보존: `{self.run_id}`\n\n```text\n{traceback.format_exc()}\n```\n')

def load(dataset='tum-freiburg1_desk',fov=False):
    if dataset=='tum-freiburg1_desk':
        d=c.load_data(dataset)
        d['raw_xyz']=c.points(d,np.ones(6));d['image_paths']=[ROOT/f['path'] for f in d['frames']]
    else:
        with np.load(EXTRA/'raw.npz') as z:
            d=dict(depth=z['depth'][0,...,0].astype(float),conf=z['depth_conf'][0],k=z['intrinsics'][0].astype(float),e=z['extrinsics'][0].astype(float),
                rgb=np.rint(z['images'][0].transpose(0,2,3,1)*255).clip(0,255).astype('uint8'))
        n,h,w=d['depth'].shape;d|=dict(fid=np.repeat(np.arange(n,dtype=np.int16),h*w),uv=np.tile(np.indices((h,w))[::-1].reshape(2,-1).T,(n,1)),
            raw_rgb=d['rgb'].reshape(-1,3),dataset=dataset,frames=json.loads((EXTRA/'frames.json').read_text()))
        d['image_paths']=[Path(f['path']) for f in d['frames']];d['inputs']=[c.record(EXTRA/p) for p in ['raw.npz','frames.json','provenance.json']]
        d['raw_xyz']=c.points(d,np.ones(6))
    d['k_raw']=d['k'].copy();d['xyz']=d['raw_xyz'].copy();d['ids']=np.arange(len(d['xyz']),dtype=np.int64)
    d['centers']=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in d['e']]);d['beta']=np.ones(6)
    if fov:
        with np.load(latest('I2',dataset)/'artifacts/fov/pointmap.npz') as z:d['xyz']=z['xyz'];d['k']=z['intrinsics'];d['beta']=z['beta']
    n,h,w=d['depth'].shape
    d['q']=np.vstack([np.c_[d['uv'][i*h*w:(i+1)*h*w],np.ones(h*w)]@np.linalg.inv(d['k'][i]).T@np.linalg.inv(d['e'][i,:,:3]).T for i in range(n)])
    d['center_points']=d['centers'][d['fid']];d['d0']=d['depth'].ravel()
    assert np.max(abs(d['centers'][d['fid']]+d['d0'][:,None]*d['q']-d['xyz']))<1e-8
    return d

def split_path(dataset): return latest('I0')/'artifacts/contract'/dataset
def split_load(dataset):
    with np.load(split_path(dataset)/'split.npz') as z:return {k:z[k] for k in z.files}

def orient(p):
    p=np.asarray(p,float);p/=np.linalg.norm(p[:3])
    if p[np.argmax(abs(p[:3]))]<0:p=-p
    return p
def svd_plane(x,w):
    center=np.average(x,axis=0,weights=w);a=x-center;ev,v=np.linalg.eigh((a*w[:,None]).T@a/w.sum())
    return orient(np.r_[v[:,0],-v[:,0]@center]),ev,center

def fit_plane(x,z,frame,config=CFG):
    x=np.asarray(x,float);z=np.asarray(z,float);N=len(x)
    if N<config['minimum_fit']:return dict(valid=False,state='low_support',count=N)
    rng=np.random.default_rng(0);ids=np.arange(N) if N<=4096 else np.sort(rng.choice(N,4096,False))
    xx,zz=x[ids],z[ids];ww=np.ones(len(ids))
    for f in np.unique(frame):ww[frame[ids]==f]=1/max(1,np.sum(frame[ids]==f))
    best=-1;bp=None;limit=config['ransac_iterations'];trials=0
    for it in range(limit):
        a,b,cc=x[rng.choice(N,3,False)];n=np.cross(b-a,cc-a);norm=np.linalg.norm(n)
        if norm<1e-12:continue
        n/=norm;p=np.r_[n,-n@a];res=abs(xx@n+p[3])/zz;s=float(ww@(res<=config['inlier_scale'])/ww.sum())
        if s>best:best=s;bp=p
        trials=it+1
        required=2000 if best<=0 else int(np.ceil(np.log(1e-4)/np.log(max(1e-12,1-min(best,.999999)**3))))
        if trials>=max(64,required):break
    if bp is None:return dict(valid=False,state='low_support',count=N,reason='collinear')
    w=np.ones(N)
    for f in np.unique(frame):w[frame==f]=1/np.sum(frame==f)
    p=orient(bp);ev=np.zeros(3);center=x.mean(0)
    for it in range(config['irls_iterations']):
        r=abs(x@p[:3]+p[3])/z;inside=r<=config['inlier_scale']
        if inside.sum()<3:break
        pn,ev,center=svd_plane(x,w*inside*np.minimum(1,config['inlier_scale']/np.maximum(r,1e-15))/z**2)
        delta=np.linalg.norm(pn-p);p=pn
        if delta<1e-10:break
    r=abs(x@p[:3]+p[3])/z;inside=r<=config['inlier_scale']
    ratio=float(ev[1]/max(ev[2],1e-30));span=float(4*np.sqrt(max(0,ev[1]))/np.median(z))
    frac=float(inside.mean());deg=ratio<1e-4 or span<.01
    valid=not deg and frac>=config['minimum_inlier_fraction'] and inside.sum()>=config['minimum_fit']
    return dict(valid=bool(valid),state='planar' if valid else 'low_support' if deg else 'ambiguous',plane=p.tolist(),count=N,
        centroid=center.tolist(),eigenvalues=ev.tolist(),second_first_ratio=ratio,second_axis_span=span,
        inlier_fraction=frac,normalized_residual=c.stats(r),ransac_trials=trials,irls_iterations=it+1,
        reference_depth=float(np.median(z)),uncertainty=dict(normal_rms_radian=float(np.sqrt(max(0,ev[0])/max(ev[1],1e-30)/N)),
            offset_standard_error=float(np.sqrt(max(0,ev[0])/N)),method='linearized covariance conditional on selected support; model bias excluded'))

def intersect(d,ids,p):
    q=d['q'][ids];num=-(d['center_points'][ids]@p[:3]+p[3]);den=q@p[:3]
    with np.errstate(divide='ignore',invalid='ignore'):z=num/den
    ok=np.isfinite(z)&(z>0)&(abs(den)/np.linalg.norm(q,axis=1)>=1e-8)
    return d['center_points'][ids]+np.where(ok,z,0)[:,None]*q,z,ok

def components(mask,minarea):
    labels,_=ndimage.label(mask,np.ones((3,3)));sizes=np.bincount(labels.ravel())
    return [labels==i for i in np.flatnonzero(sizes>=minarea) if i]

def hcost(r):
    a=abs(np.asarray(r));return np.where(a<=1,.5*a*a,a-.5)
def robust_residual(r):return np.sign(r)*np.sqrt(2*hcost(r))

def normals(d,window,excluded):
    n,h,w=d['depth'].shape;out=[];valids=[]
    for i in range(n):
        x=d['xyz'][i*h*w:(i+1)*h*w].reshape(h,w,3)
        # Exclude the whole validation halo from moments; do not compute on heldout XYZ.
        good=(~excluded[i*h*w:(i+1)*h*w].reshape(h,w))&(d['conf'][i]>=np.percentile(d['conf'][i],10))
        count=ndimage.uniform_filter(good.astype(float),window,mode='constant')
        mean=np.stack([ndimage.uniform_filter(x[...,j]*good,window,mode='constant')/np.maximum(count,1e-15) for j in range(3)],-1)
        cov=np.empty((h,w,3,3))
        for j in range(3):
            for k in range(3):cov[...,j,k]=ndimage.uniform_filter(x[...,j]*x[...,k]*good,window,mode='constant')/np.maximum(count,1e-15)-mean[...,j]*mean[...,k]
        ev,vec=np.linalg.eigh(cov);nn=vec[...,0];nn*=np.where(nn[...,2:3]<0,-1,1)
        out.append(nn);valids.append(good&(count>.5))
    return np.array(out),np.array(valids)

def ply_write(path,d,xyz,pids,colors):
    dt=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('observation_id','<i8'),('frame_id','<i2'),('u','<i4'),('v','<i4'),('plane_id','<i4')])
    a=np.empty(len(xyz),dt)
    for j,k in enumerate(['x','y','z']):a[k]=xyz[:,j]
    for j,k in enumerate(['red','green','blue']):a[k]=colors[:,j]
    a['observation_id']=d['ids'];a['frame_id']=d['fid'];a['u']=d['uv'][:,0];a['v']=d['uv'][:,1];a['plane_id']=pids
    types={'f8':'double','u1':'uchar','i8':'int64','i2':'short','i4':'int'}
    header='ply\nformat binary_little_endian 1.0\ncomment Omega world/model units; int64 observation_id; int32 plane_id sentinel -1\nelement vertex '+str(len(a))+'\n'
    header+=''.join(f'property {types[dt.fields[k][0].str[1:]]} {k}\n' for k in dt.names)+'end_header\n'
    with Path(path).open('xb') as f:f.write(header.encode());a.tofile(f)
    with Path(path).open('rb') as f:
        while f.readline()!=b'end_header\n':pass
        restored=np.fromfile(f,dt)
    assert np.array_equal(restored,a)

def plane_basis(p):
    n=p[:3];axis=np.eye(3)[np.argmin(abs(n))];u=np.cross(n,axis);u/=np.linalg.norm(u);return -p[3]*n,u,np.cross(n,u)
