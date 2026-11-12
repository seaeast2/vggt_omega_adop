"""P1 CPU camera contract, provenance-preserving unprojection and diagnostics."""
import argparse
import ast
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import numpy as np
from PIL import Image
import cv2


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def unproject(uv, z, k, e):
    camera = np.column_stack(((uv[:, 0]-k[0, 2])/k[0, 0]*z,
                              (uv[:, 1]-k[1, 2])/k[1, 1]*z, z))
    return (camera-e[:3, 3]) @ e[:3, :3]


def project(x, k, e):
    c = x @ e[:3, :3].T + e[:3, 3]
    with np.errstate(divide='ignore', invalid='ignore'):
        uv = (c @ k.T)[:, :2]/c[:, 2:3]
    return uv, c[:, 2]


def valid_projection(uv, z, h, w, mask):
    inside = np.isfinite(uv).all(1) & (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] <= w-1) & (uv[:, 1] >= 0) & (uv[:, 1] <= h-1)
    ids = np.flatnonzero(inside)
    pix = np.rint(uv[ids]).astype(int)
    inside[ids] &= mask[pix[:, 1], pix[:, 0]]
    return inside


def stats(x):
    return {'count': int(x.size), 'median': float(np.median(x)), 'p95': float(np.quantile(x,.95)), 'max': float(np.max(x))} if x.size else {'count': 0}


def synthetic():
    k = np.array([[90.,0,23.],[0,100.,19.],[0,0,1.]])
    angle=.37; r=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    e=np.column_stack((r,[.3,-.2,.4]))
    uv=np.array([[2.,3.],[40.,32.],[23.,19.],[10.,20.]])
    z=np.full(4,2.5)
    x=unproject(uv,z,k,e); q,d=project(x,k,e)
    assert np.max(np.abs(q-uv))<1e-10 and np.max(np.abs(d-z))<1e-10
    world=np.array([[0.,0.,3.],[1.,.5,3.],[-1.,.4,3.]])
    q,d=project(world,k,e); assert np.max(np.abs(unproject(q,d,k,e)-world))<1e-10
    # Independent analytic plane in a translated camera: expected world=(0.1,0,2).
    et=np.column_stack((np.eye(3),[-.1,0,0])); q,d=project(np.array([[.1,0,2.]]),k,et)
    assert np.array_equal(q,[[23.,19.]]) and d[0]==2
    wrong=(np.column_stack(((uv[:,0]-23)/90*z,(uv[:,1]-19)/100*z,z))-e[:,3])@r.T
    wrong_uv,_=project(wrong,k,e)
    assert np.max(np.abs(wrong_uv-uv))>1
    half,_=project(unproject(uv+.5,z,k,e),k,e)
    assert np.allclose(half-uv,.5)
    ray=np.array([1.,1.,1.]);ray/=np.linalg.norm(ray)
    assert abs((ray*2)[2]-2)>.5  # Range must not be substituted for camera Z.
    mask=np.ones((40,48),bool);mask[0:2]=False
    check=valid_projection(np.array([[5.,5.],[5.,5.],[-1.,5.],[5.,0.]]),np.array([1.,-1.,1.,1.]),40,48,mask)
    assert check.tolist()==[True,False,False,False]
    return {'roundtrip_pixel_max':float(np.max(np.abs(q-[[23.,19.]]))),
            'rotation_negative_control_pixel_max':float(np.max(np.abs(wrong_uv-uv))),
            'half_pixel_negative_control':.5,'plane_and_axis_checks':'passed','positive_depth_frustum_padding_checks':'passed'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
    config=json.loads(Path('experiments/pointmap_refinement/P1/config.json').read_text())
    stage=Path('results/pointmap_refinement')/a.run_id/'stages/P1';stage.mkdir(parents=True,exist_ok=False)
    for sub in ['artifacts/geometry','artifacts/gt','artifacts/source','evaluation','logs']:(stage/sub).mkdir(parents=True)
    started=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    (stage/'manifest.json').write_text(json.dumps({'status':'running','started_at':started}))
    (stage/'config_resolved.json').write_text(json.dumps(config|{'run_id':a.run_id},indent=2))
    try:
        source=Path(config['input']);assert sha(source)==config['input_sha256']
        p0=Path(config['parent_stage']);parent=json.loads((p0/'manifest.json').read_text());assert parent['status']=='completed'
        frame_data=json.loads((p0/'artifacts/data/frames.json').read_text())['frames'][:3]
        with np.load(source) as data:
            depth=data['depth'][0,...,0].astype('float64');k=data['intrinsics'][0].astype('float64');e=data['extrinsics'][0].astype('float64');rgb=data['images'][0].transpose(0,2,3,1);conf=data['depth_conf'][0]
        n,h,w=depth.shape;v,u=np.indices((h,w));uv=np.column_stack((u.ravel(),v.ravel()))
        orth=float(np.max(np.abs(e[:,:,:3]@e[:,:,:3].transpose(0,2,1)-np.eye(3))));assert orth<1e-5
        assert np.allclose(np.linalg.det(e[:,:,:3]),1,atol=1e-5)
        synth=synthetic()
        points=np.stack([unproject(uv,depth[i].ravel(),k[i],e[i]).reshape(h,w,3) for i in range(n)])
        # Execute only the pinned upstream function AST, avoiding optional demo imports.
        official_path=Path('thirdparty/vggt-omega/demo_gradio.py')
        tree=ast.parse(official_path.read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='unproject_depth_map_to_point_map')
        ns={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),str(official_path),'exec'),ns)
        ref=ns[node.name](depth[...,None],e,k);agreement=float(np.max(np.abs(points-ref)));assert agreement<1e-10
        self_rows=[]
        for i in range(n):
            q,z=project(points[i].reshape(-1,3),k[i],e[i]);err=np.linalg.norm(q-uv,axis=1)
            self_rows.append({'frame':i,'pixel_error':stats(err),'z_error':stats(np.abs(z-depth[i].ravel()))})
            assert err.max()<config['pixel_tolerance']
        # Preserve all finite positive observations, without confidence/semantic filtering or fusion.
        valid=np.isfinite(points).all(-1)&np.isfinite(conf)&(depth>0)
        frame_id,yy,xx=np.where(valid);xyz=points[valid];color=np.rint(rgb[valid]*255).clip(0,255).astype('uint8')
        original_uv=np.column_stack(((xx+.5)*640/w-.5,(yy+.5)*480/h-.5))
        obs={'world_xyz_initial':xyz,'frame_id':frame_id.astype('int16'),'pixel_uv':np.column_stack((xx,yy)).astype('int32'),'original_rgb_sample_uv':original_uv,'depth_initial':depth[valid],'depth_conf_raw':conf[valid],'rgb':color}
        out=stage/'artifacts/geometry/observations.npz';np.savez_compressed(out,**obs)
        dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('frame_id','<i2'),('u','<i4'),('v','<i4')]);records=np.empty(len(xyz),dtype=dtype)
        for j,key in enumerate(['x','y','z']):records[key]=xyz[:,j]
        for j,key in enumerate(['red','green','blue']):records[key]=color[:,j]
        records['frame_id']=frame_id;records['u']=xx;records['v']=yy
        header='ply\nformat binary_little_endian 1.0\ncomment P1 raw observations; not fused; arbitrary model scale\nelement vertex '+str(len(xyz))+'\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty short frame_id\nproperty int u\nproperty int v\nend_header\n'
        ply=stage/'artifacts/geometry/observations.ply'
        with ply.open('wb') as f:f.write(header.encode());records.tofile(f)
        with ply.open('rb') as f:
            while f.readline()!=b'end_header\n':pass
            loaded=np.fromfile(f,dtype=dtype)
        assert np.array_equal(loaded,records)
        with np.load(out) as saved:
            for key in obs:assert np.array_equal(saved[key],obs[key])
        cross=[]
        for i in range(n):
            for j in range(n):
                if i==j:continue
                q,z=project(points[i].reshape(-1,3),k[j],e[j]);inside=valid_projection(q,z,h,w,np.ones((h,w),bool));ids=np.flatnonzero(inside);pix=np.rint(q[ids]).astype(int);target=depth[j,pix[:,1],pix[:,0]]
                rel=np.abs(z[ids]-target)/np.maximum(target,1e-8)
                zbuffer=np.full(h*w,np.inf);flat=pix[:,1]*w+pix[:,0];np.minimum.at(zbuffer,flat,z[ids]);front=z[ids]<=zbuffer[flat]+config['zbuffer_relative_tolerance']*zbuffer[flat]
                cross.append({'source':i,'target':j,'total':h*w,'in_frustum_positive':int(inside.sum()),'front_candidates':int(front.sum()),'relative_depth_residual':stats(rel),'agreement_5percent_fraction':float(np.mean(rel<=.05)),'interpretation':'predicted depth consistency, not GT accuracy or confirmed correspondence'})
        # Sensor depth: nearest timestamp <=20ms, registered RGB grid, evaluation-only.
        archive=Path(config['archive']);assert sha(archive)==config['archive_sha256']
        gt_rows=[]
        with tarfile.open(archive,'r:gz') as tar:
            prefix='rgbd_dataset_freiburg1_desk/'
            lines=[x.split() for x in tar.extractfile(prefix+'depth.txt').read().decode().splitlines() if x.strip() and not x.startswith('#')]
            for i,frame in enumerate(frame_data):
                dt,name=min(lines,key=lambda x:abs(float(x[0])-float(frame['timestamp'])));delta=abs(float(dt)-float(frame['timestamp']));assert delta<=.02
                raw=tar.extractfile(prefix+name).read();(stage/'artifacts/gt'/Path(name).name).write_bytes(raw)
                gt=np.array(Image.open(io.BytesIO(raw)));assert gt.shape==(480,640)
                resized=np.array(Image.fromarray(gt).resize((w,h),Image.Resampling.NEAREST));metres=resized.astype('float64')/5000;mask=resized>0
                # Independent centre-based nearest mapping must agree with PIL.
                sy=np.floor((np.arange(h)+.5)*480/h).astype(int);sx=np.floor((np.arange(w)+.5)*640/w).astype(int)
                assert np.array_equal(resized,gt[sy[:,None],sx[None,:]])
                np.savez_compressed(stage/'artifacts/gt'/f'aligned_{i}.npz',depth_m=metres,valid=mask)
                gt_rows.append({'frame':i,'rgb_timestamp':frame['timestamp'],'depth_timestamp':dt,'delta_seconds':delta,'raw_sha256':hashlib.sha256(raw).hexdigest(),'valid_fraction':float(mask.mean()),'shape':[h,w],'resize_mapping_check':'passed'})
        summary={'synthetic':synth,'rotation_orthogonality_max':orth,'official_unprojection_max_difference':agreement,'self_reprojection':self_rows,'point_count':len(xyz),'invalid_count':int(valid.size-valid.sum()),'cross_view':cross,'gt_grid_alignment':gt_rows,'gt_accuracy_evaluated':False,'pixel_convention':'integer u,v as official demo; original RGB resize sampling uses centre mapping','depth_convention':'camera Z, not Euclidean ray distance','world_convention':'OpenCV camera-from-world, arbitrary predicted scale','padding':'none in these same-size input frames; synthetic mask rejection tested'}
        (stage/'evaluation/metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
        (stage/'artifacts/geometry/frames.json').write_text(json.dumps(frame_data,indent=2))
        (stage/'environment.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,'platform':platform.platform(),'execution_context':'host CPU only; no GPU inference','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
        for name in ['demo_gradio.py','vggt_omega/utils/pose_enc.py','vggt_omega/utils/load_fn.py']:
            src=Path('thirdparty/vggt-omega')/name;shutil.copy2(src,stage/'artifacts/source'/src.name)
        m={'status':'completed','run_id':a.run_id,'experiment_code':'P1','started_at':started,'ended_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'input':{'path':str(source),'sha256':sha(source)},'parent_manifest':{'path':str(p0/'manifest.json'),'sha256':sha(p0/'manifest.json')},'completion_criteria_met':True}
        (stage/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(summary,indent=2))
    except Exception as error:
        (stage/'manifest.json').write_text(json.dumps({'status':'failed','error':str(error),'started_at':started},indent=2));raise


if __name__=='__main__':main()
