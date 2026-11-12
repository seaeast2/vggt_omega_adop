"""Frozen-depth FoV experiments. Float64 geometry; CPU only; no GT fitting."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PALETTE = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], np.uint8)
LOW, HIGH = 1 / 1.10, 1 / .90
DATASETS = {
    'tum-freiburg1_desk': ('tum-freiburg1_desk-E0-20261112-001', 'E0',
        'd820f18f5bb683efb89d331f82262b68e5cec55a7bbadf379d8091721a26afa4'),
    'hkairport01': ('hkairport01-E0d-20261112-001', 'E0d',
        '1a41d0be481e244afca2cf664a090e837dc4dcf75992da38e1e5a3649d91abbe'),
    'amtown01': ('amtown01-E0d-20261112-001', 'E0d',
        'b3c2a8982d34082ac8a3c32fe5d2a604e6a1813cc32e8682bc664eb7a46b79b5'),
}
DEFAULTS = {
    'seed': 0, 'sift_features': 8192, 'ratio': .75, 'ransac_px': 1.5,
    'ransac_confidence': .999, 'ransac_max_iters': 10000,
    'confidence_percentile': 10, 'depth_support_range': .03,
    'anchor_tiles': [16, 12], 'coverage_tiles': [4, 4],
    'minimum_pair_total': 100, 'minimum_pair_fit': 50,
    'minimum_pair_validation': 20, 'minimum_occupied_cells': 6,
    'beta_bounds': [LOW, HIGH], 'huber_delta': .01, 'prior_lambda': .001,
    'z_sqrt_weight': 2., 'irls_iterations': 20,
    'beta_tolerance': 1e-8, 'loss_relative_tolerance': 1e-8,
    'coverage_loss_limit': .005, 'rank_relative_tolerance': 1e-6,
    'condition_limit': 1e6, 'bound_tolerance': 1e-4,
    'fusion_color_range': 30, 'fusion_depth_range': .03,
    'fusion_depth_tolerance': 1e-8,
    'nn_query_count_per_frame': 512,
    'nearest_neighbor_backend': 'OpenCV exact brute-force float32 L2; full target, fixed source queries',
    'execution_context': 'host CPU; no CUDA or model inference',
}


def stamp():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def json_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def record(path):
    path = Path(path)
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Stage:
    def __init__(self, code, dataset='synthetic', parents=(), extra=None):
        self.code, self.dataset = code, dataset
        date = datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d')
        root = ROOT / 'results/camera_fov_alignment'
        seq = 1
        while (root / f'{dataset}-{code}-{date}-{seq:03}').exists():
            seq += 1
        self.run_id = f'{dataset}-{code}-{date}-{seq:03}'
        self.path = root / self.run_id / 'stages' / code
        self.path.mkdir(parents=True, exist_ok=False)
        self.doc = ROOT / 'docs/experiments/camera_fov_alignment' / code / self.run_id
        self.doc.mkdir(parents=True, exist_ok=False)
        for name in ['logs', 'evaluation', 'artifacts/source', 'artifacts/figures']:
            (self.path / name).mkdir(parents=True)
        self.started = time.perf_counter()
        self.manifest = {'status': 'running', 'experiment_code': code,
            'run_id': self.run_id, 'dataset': dataset, 'started_at': stamp(),
            'parents': [record(Path(p) / 'manifest.json') for p in parents],
            'project_commit_at_start': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'gt_accuracy_evaluated': False}
        self.config = DEFAULTS | {'experiment_code': code, 'dataset': dataset,
            'run_id': self.run_id} | (extra or {})
        json_write(self.path / 'config_resolved.json', self.config)
        self.source_snapshot()
        json_write(self.path / 'environment.json', {
            'python': sys.version, 'platform': platform.platform(),
            'numpy': np.__version__, 'opencv': cv2.__version__,
            'execution_context': DEFAULTS['execution_context'],
            'thread_env': {k: os.environ.get(k) for k in
                ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS']},
            'scipy_required': False})
        self.save_manifest()
        self.log('registered', config=self.config)

    def source_snapshot(self):
        src = ROOT / 'experiments/camera_fov_alignment'
        for p in sorted(src.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                dest = self.path / 'artifacts/source' / p.relative_to(src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        shutil.copy2(ROOT / 'docs/vggt_omega_fov_pointmap_alignment_experiment_plan.md',
                     self.path / 'artifacts/source/experiment_plan.md')

    def log(self, event, **data):
        value = {'time': stamp(), 'event': event} | data
        message = json.dumps(value, ensure_ascii=False)
        print(message, flush=True)
        with (self.path / 'logs/run.log').open('a') as f:
            f.write(message + '\n')

    def save_manifest(self):
        json_write(self.path / 'manifest.json', self.manifest)

    def finish(self, metrics, report):
        metrics |= {'gt_accuracy_evaluated': False,
            'elapsed_seconds': time.perf_counter() - self.started,
            'process_peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
        json_write(self.path / 'evaluation/metrics.json', metrics)
        self.log('completed', decision=metrics.get('decision', 'COMPLETED'))
        self.manifest |= {'status': 'completed', 'ended_at': stamp(),
            'decision': metrics.get('decision', 'COMPLETED'),
            'execution_completed': True,
            'scientific_improvement': metrics.get('scientific_improvement', False)}
        self.manifest['artifacts'] = [record(p) for p in sorted(self.path.rglob('*'))
            if p.is_file() and p.name != 'manifest.json']
        self.save_manifest()
        (self.doc / 'report.md').write_text(report + '\n\n' +
            f'실행 Stage: `{self.path.relative_to(ROOT)}`. '
            '대형 NPZ/PLY는 기존 규칙대로 results에 보관한다. '
            'GT 기하 정확도는 평가하지 않았다.\n')
        for name in ['config_resolved.json', 'environment.json', 'manifest.json']:
            shutil.copy2(self.path / name, self.doc / name)
        for p in sorted((self.path / 'evaluation').rglob('*')):
            if p.is_file() and p.suffix == '.json':
                dest = self.doc / 'evaluation' / p.relative_to(self.path / 'evaluation')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        shutil.copy2(self.path / 'logs/run.log', self.doc / 'run.log')
        figs = self.path / 'artifacts/figures'
        if figs.exists():
            shutil.copytree(figs, self.doc / 'figures', dirs_exist_ok=True)
        return self.path

    def fail(self, error):
        self.manifest |= {'status': 'failed', 'ended_at': stamp(),
            'error': str(error), 'traceback': traceback.format_exc()}
        self.save_manifest()
        self.log('failed', error=str(error))
        shutil.copy2(self.path / 'manifest.json', self.doc / 'manifest.json')
        (self.doc / 'report.md').write_text(f'# {self.code} 실행 실패\n\n`{self.run_id}`\n\n'
            f'````text\n{traceback.format_exc()}\n````\n')


def load_data(dataset):
    run, code, expected = DATASETS[dataset]
    parent = ROOT / 'results/pointmap_refinement' / run / 'stages' / code
    base = parent / 'artifacts/baseline'
    assert json.loads((parent / 'manifest.json').read_text())['status'] == 'completed'
    raw_path = base / 'vggt_omega_raw.npz'
    assert record(raw_path)['sha256'] == expected
    with np.load(raw_path) as raw:
        data = {'depth': raw['depth'][0, ..., 0].astype(float),
            'conf': raw['depth_conf'][0].copy(),
            'k': raw['intrinsics'][0].astype(float),
            'e': raw['extrinsics'][0].astype(float),
            'pose_enc': raw['pose_enc'].copy(),
            'rgb': np.rint(raw['images'][0].transpose(0, 2, 3, 1) * 255).clip(0,255).astype(np.uint8)}
    with np.load(base / 'observations.npz') as obs:
        data |= {'reference_xyz': obs['world_xyz_initial'].copy(),
            'fid': obs['frame_id'].copy(), 'uv': obs['pixel_uv'].copy(),
            'raw_rgb': obs['rgb'].copy()}
    data |= {'parent': parent, 'dataset': dataset,
        'frames': json.loads((base / 'frames.json').read_text()),
        'inputs': [record(p) for p in [raw_path, base/'observations.npz',
                    base/'frames.json', parent/'manifest.json']]}
    n,h,w = data['depth'].shape
    assert n == 3 and np.isfinite(data['depth']).all() and (data['depth'] > 0).all()
    assert np.array_equal(data['fid'], np.repeat(np.arange(n),h*w))
    assert np.array_equal(data['raw_rgb'], data['rgb'].reshape(-1,3))
    data['centers'] = np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in data['e']])
    return data


def unproject(uv, depth, k, e):
    pixels = np.column_stack([uv, np.ones(len(uv))])
    camera = (pixels @ np.linalg.inv(k).T) * np.asarray(depth)[:,None]
    return (camera-e[:,3]) @ np.linalg.inv(e[:,:3]).T


def corrected_k(k0, beta):
    out = k0.copy()
    beta = np.broadcast_to(np.asarray(beta), (len(k0),2))
    out[:,0,0] /= beta[:,0]
    out[:,1,1] /= beta[:,1]
    return out


def points(data, beta):
    k = corrected_k(data['k'], np.asarray(beta).reshape(-1,2))
    n,h,w = data['depth'].shape
    uv = data['uv'][:h*w]
    return np.vstack([unproject(uv, data['depth'][i].ravel(), k[i], data['e'][i])
                      for i in range(n)])


def project(xyz, k, e, h, w):
    camera = xyz @ e[:,:3].T + e[:,3]
    z = camera[:,2]
    with np.errstate(divide='ignore',invalid='ignore'):
        uv = (camera @ k.T)[:,:2] / z[:,None]
    valid = (z > 0) & np.isfinite(uv).all(1) & (uv[:,0] >= -.5) & \
        (uv[:,0] < w-.5) & (uv[:,1] >= -.5) & (uv[:,1] < h-.5)
    return uv,z,valid


def front(xyz, k, e, h, w):
    uv,z,valid = project(xyz,k,e,h,w)
    ids = np.flatnonzero(valid)
    xy = np.rint(uv[ids]).astype(np.int64)
    flat = xy[:,1]*w+xy[:,0]
    order = np.lexsort((ids,z[ids],flat))
    ids,flat = ids[order],flat[order]
    first = np.r_[True,flat[1:] != flat[:-1]] if len(flat) else np.zeros(0,bool)
    win = np.full(h*w,-1,np.int64)
    depth = np.full(h*w,np.inf)
    win[flat[first]],depth[flat[first]] = ids[first],z[ids[first]]
    return depth.reshape(h,w),win.reshape(h,w),valid


def image_write(path,rgb):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    assert cv2.imwrite(str(path),np.asarray(rgb,np.uint8)[...,::-1])
    assert np.array_equal(cv2.imread(str(path))[...,::-1],rgb)


def panel(path, rows, titles):
    h,w = rows[0][0].shape[:2]
    head,label = 42,30
    image = np.full((head+len(rows)*(h+label),len(titles)*w,3),245,np.uint8)
    for j,title in enumerate(titles):
        cv2.putText(image,title,(j*w+6,27),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1,cv2.LINE_AA)
    for i,row in enumerate(rows):
        for j,cell in enumerate(row):
            y = head+i*(h+label)
            cv2.putText(image,f'camera {i}',(j*w+6,y+21),cv2.FONT_HERSHEY_SIMPLEX,.5,(20,20,20),1,cv2.LINE_AA)
            image[y+label:y+label+h,j*w:(j+1)*w] = cell
    image_write(path,image)


def stats(values):
    values = np.asarray(values)
    assert np.isfinite(values).all()
    return {'count':int(values.size),'mean':float(values.mean()),
        'median':float(np.median(values)),'p90':float(np.percentile(values,90)),
        'max':float(values.max())} if values.size else {'count':0}


def ply_write(path, xyz, rgb, owner, counts=None, bits=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),
                    ('blue','u1'),('owner','<i2'),('n_observed','<u4'),('source_mask','u1')])
    out=np.empty(len(xyz),dtype)
    for j,key in enumerate(['x','y','z']):out[key]=xyz[:,j]
    for j,key in enumerate(['red','green','blue']):out[key]=rgb[:,j]
    out['owner']=owner
    out['n_observed']=np.ones(len(xyz),np.uint32) if counts is None else counts
    out['source_mask']=(1<<owner).astype(np.uint8) if bits is None else bits
    head=('ply\nformat binary_little_endian 1.0\ncomment camera FoV alignment; model units\n'
        f'element vertex {len(out)}\nproperty double x\nproperty double y\nproperty double z\n'
        'property uchar red\nproperty uchar green\nproperty uchar blue\nproperty short owner\n'
        'property uint n_observed\nproperty uchar source_mask\nend_header\n')
    with path.open('xb') as f:
        f.write(head.encode());out.tofile(f)
    with path.open('rb') as f:
        while f.readline()!=b'end_header\n':pass
        assert np.array_equal(np.fromfile(f,dtype),out)


def affine_observation(uv, depth, k, e):
    inv=np.linalg.inv(e[:,:3])
    ax=np.column_stack([depth*(uv[:,0]-k[0,2])/k[0,0],np.zeros(len(depth)),np.zeros(len(depth))]) @ inv.T
    ay=np.column_stack([np.zeros(len(depth)),depth*(uv[:,1]-k[1,2])/k[1,1],np.zeros(len(depth))]) @ inv.T
    return unproject(uv,depth,k,e), np.stack([ax,ay],axis=-1)


def build_system(data, matches):
    """Each block is a 3-vector camera-relative residual; beta variables are absolute."""
    blocks, constants, weights, row_pair = [],[],[],[]
    n=len(matches['pair'])
    for i,j in itertools.combinations(range(3),2):
        ids=np.flatnonzero((matches['pair'][:,0]==i)&(matches['pair'][:,1]==j))
        if not len(ids):continue
        pi,ai=affine_observation(matches['uv_i'][ids],matches['di'][ids],data['k'][i],data['e'][i])
        pj,aj=affine_observation(matches['uv_j'][ids],matches['dj'][ids],data['k'][j],data['e'][j])
        a=np.zeros((len(ids),3,6));a[:,:,2*i:2*i+2]=ai;a[:,:,2*j:2*j+2]=-aj
        offset=pi-pj-a.sum(-1)
        for camera,depth in [(i,matches['di'][ids]),(j,matches['dj'][ids])]:
            rot=data['e'][camera,:,:3]
            aa=np.einsum('ab,nbk->nak',rot,a)/depth[:,None,None]
            bb=offset@rot.T/depth[:,None]
            aa[:,2,:]*=2;bb[:,2]*=2
            blocks.append(aa);constants.append(bb)
            weights.append(np.full(len(ids),1/(6*len(ids))))
            row_pair.append(ids)
    return np.concatenate(blocks),np.concatenate(constants),np.concatenate(weights),np.concatenate(row_pair)


def huber(norm,delta=.01):
    return np.where(norm<=delta,.5*norm**2,delta*(norm-.5*delta))


def box_lstsq(a,b,low=LOW,high=HIGH):
    """Enumerate active bounds after a QR reduction, never invert normal equations."""
    a=np.asarray(a,float); b=np.asarray(b,float);d=a.shape[1]
    q,r=np.linalg.qr(a,mode='reduced');y=q.T@b
    best=None;bestloss=np.inf
    for status in itertools.product((-1,0,1),repeat=d):
        status=np.array(status);free=status==0;fixed=~free
        x=np.where(status==-1,low,high).astype(float)
        if free.any():
            rhs=y-r[:,fixed]@x[fixed]
            x[free]=np.linalg.lstsq(r[:,free],rhs,rcond=None)[0]
        if (x<low-1e-12).any() or (x>high+1e-12).any():continue
        x=np.clip(x,low,high)
        loss=float(np.sum((r@x-y)**2))
        if loss<bestloss:bestloss,best=loss,x
    assert best is not None
    gradient=a.T@(a@best-b)
    feasible_gradient=gradient.copy()
    feasible_gradient[(best<=low+1e-10)&(gradient>0)]=0
    feasible_gradient[(best>=high-1e-10)&(gradient<0)]=0
    kkt=float(np.max(np.abs(feasible_gradient),initial=0))
    assert kkt<1e-8*max(1.,np.linalg.norm(a)*np.linalg.norm(b)),kkt
    return best,kkt


def solve_irls(a,c,w,dimension=6,prior=.001,maxiter=20):
    if dimension==1:a=a.sum(-1,keepdims=True)
    x=np.ones(dimension)
    history=[];converged=False
    def objective(beta):
        data=float(w@huber(np.linalg.norm(a@beta+c,axis=1)))
        p=float(prior*np.mean((beta-1)**2))
        return data+p,data,p
    old=objective(x)[0]
    history.append({'iteration':0,'beta':x.tolist(),'loss':old,'data_loss':objective(x)[1],
                    'prior_loss':0.,'delta_beta':0.,'relative_loss_change':0.,'kkt':0.})
    for iteration in range(1,maxiter+1):
        norm=np.linalg.norm(a@x+c,axis=1)
        robust=np.minimum(1.,.01/np.maximum(norm,1e-300))
        scale=np.sqrt(w*robust)
        aa=(a*scale[:,None,None]).reshape(-1,dimension)
        bb=(-c*scale[:,None]).ravel()
        if prior:
            aa=np.vstack([aa,np.eye(dimension)*np.sqrt(2*prior/dimension)])
            bb=np.r_[bb,np.ones(dimension)*np.sqrt(2*prior/dimension)]
        candidate,kkt=box_lstsq(aa,bb)
        loss,data,p=objective(candidate)
        change=float(np.max(np.abs(candidate-x)))
        relative=abs(loss-old)/max(abs(old),1e-16)
        assert loss <= old+1e-12,(loss,old)
        history.append({'iteration':iteration,'beta':candidate.tolist(),'loss':loss,
            'data_loss':data,'prior_loss':p,'delta_beta':change,
            'relative_loss_change':relative,'kkt':kkt})
        x,old=candidate,loss
        if change<1e-8 and relative<1e-8:
            converged=True;break
    return x,history,converged


def rank_info(a):
    s=np.linalg.svd(a.reshape(-1,a.shape[-1]),compute_uv=False)
    rank=int(np.sum(s>s[0]*1e-6)) if len(s) and s[0]>0 else 0
    condition=float(s[0]/s[-1]) if len(s) and s[-1]>0 else None
    return {'rank':rank,'dimension':a.shape[-1],'singular_values':s.tolist(),
        'condition':condition,'identifiable':rank==a.shape[-1] and condition is not None and condition<=1e6}
