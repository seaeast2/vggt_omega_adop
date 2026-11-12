"""Freeze P0/P1 observations as an E0 baseline; CPU-only scientific previews."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import cv2
import numpy as np


def record(p):
    with Path(p).open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(p),'bytes':Path(p).stat().st_size,'sha256':digest}


def verify_parent(stage):
    m=json.loads((stage/'manifest.json').read_text())
    assert m['status']=='completed' and m['completion_criteria_met']
    for row in m['artifacts']:
        assert record(row['path'])==row, row['path']
    return record(stage/'manifest.json')


DT=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('frame_id','<i2'),('u','<i4'),('v','<i4')])


def ply(path,xyz,rgb,frame,uv):
    a=np.empty(len(xyz),dtype=DT)
    for j,key in enumerate(['x','y','z']):a[key]=xyz[:,j]
    for j,key in enumerate(['red','green','blue']):a[key]=rgb[:,j]
    a['frame_id']=frame;a['u']=uv[:,0];a['v']=uv[:,1]
    header='ply\nformat binary_little_endian 1.0\ncomment E0 raw observations; no fusion; arbitrary model world scale\nelement vertex '+str(len(a))+'\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty short frame_id\nproperty int u\nproperty int v\nend_header\n'
    with path.open('xb') as f:f.write(header.encode());a.tofile(f)
    with path.open('rb') as f:
        while f.readline()!=b'end_header\n':pass
        b=np.fromfile(f,dtype=DT)
    assert np.array_equal(a,b)


def summary(a):
    return {str(q):float(np.percentile(a,q)) for q in [0,.5,50,95,99.5,100]}


def label(canvas,text,x,y):
    cv2.putText(canvas,text,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.5,(20,20,20),1,cv2.LINE_AA)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);args=p.parse_args()
    start=time.perf_counter();stamp=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    cfg=json.loads(Path('experiments/pointmap_refinement/E0/config.json').read_text())
    stage=Path('results/pointmap_refinement')/args.run_id/'stages/E0';stage.mkdir(parents=True,exist_ok=False)
    for n in ['artifacts/baseline','artifacts/geometry','artifacts/previews','artifacts/source','evaluation','logs']:(stage/n).mkdir(parents=True)
    (stage/'config_resolved.json').write_text(json.dumps(cfg|{'run_id':args.run_id},indent=2)+'\n')
    (stage/'manifest.json').write_text(json.dumps({'status':'running','started_at':stamp}))
    try:
        p0=Path(cfg['p0_stage']);p1=Path(cfg['p1_stage'])
        parents=[verify_parent(p0),verify_parent(p1)]
        raw=p0/'artifacts/inference/max_size_n03/vggt_omega_raw.npz';assert record(raw)['sha256']==cfg['raw_npz_sha256']
        obs_source=p1/'artifacts/geometry/observations.npz'
        for src,name in [(raw,'vggt_omega_raw.npz'),(obs_source,'observations.npz'),(p1/'artifacts/geometry/frames.json','frames.json')]:
            target=stage/'artifacts/baseline'/name;shutil.copy2(src,target);assert record(src)['sha256']==record(target)['sha256']
        with np.load(raw) as data:
            depth=data['depth'][0,...,0];conf=data['depth_conf'][0];rgb=data['images'][0].transpose(0,2,3,1);k=data['intrinsics'][0];e=data['extrinsics'][0]
            arrays={key:data[key] for key in data.files}
        with np.load(obs_source) as data:obs={key:data[key] for key in data.files}
        xyz=obs['world_xyz_initial'];color=obs['rgb'];fid=obs['frame_id'];uv=obs['pixel_uv'];n,h,w=depth.shape
        assert len(xyz)==n*h*w and np.isfinite(xyz).all()
        assert np.array_equal(obs['depth_initial'],depth[fid,uv[:,1],uv[:,0]])
        assert np.array_equal(color,np.rint(rgb[fid,uv[:,1],uv[:,0]]*255).astype('uint8'))
        rows=[]
        for i in range(n):
            mask=fid==i
            payload={key:value[mask] for key,value in obs.items()}
            payload.update(intrinsics=k[i],extrinsics=e[i],depth=depth[i],depth_conf=conf[i],image_rgb=rgb[i])
            path=stage/'artifacts/baseline'/f'frame_{i:02d}.npz';np.savez_compressed(path,**payload)
            with np.load(path) as saved:
                for key in payload:assert np.array_equal(saved[key],payload[key])
            ply(stage/'artifacts/geometry'/f'frame_{i:02d}.ply',xyz[mask],color[mask],fid[mask],uv[mask])
            rows.append({'frame':i,'points':int(mask.sum()),'depth_model_units':summary(depth[i]),'confidence_raw':summary(conf[i]),'xyz_min':xyz[mask].min(0).tolist(),'xyz_max':xyz[mask].max(0).tolist(),'camera_center_world':(-e[i,:,:3].T@e[i,:,3]).tolist()})
        ply(stage/'artifacts/geometry/all_observations.ply',xyz,color,fid,uv)
        # Scientific panel: source RGB and predicted depth/confidence; shared display scales only.
        limits={name:np.percentile(values,cfg['visualization_percentiles']).tolist() for name,values in [('depth',depth),('confidence',conf)]}
        panel=np.full((n*(h+35)+30,3*w,3),255,np.uint8)
        label(panel,'E0 input RGB | predicted Z-depth | raw confidence (display-only scales)',8,20)
        for i in range(n):
            y=30+i*(h+35)
            for j,name in enumerate(['RGB','depth','confidence']):label(panel,f'frame {i} {name}',j*w+8,y+22)
            panel[y+35:y+35+h,:w]=np.rint(rgb[i]*255).astype('uint8')[...,::-1]
            for col,name,values in [(1,'depth',depth[i]),(2,'confidence',conf[i])]:
                lo,hi=limits[name];v=((values-lo)/max(hi-lo,1e-12)*255).clip(0,255).astype('uint8')
                panel[y+35:y+35+h,col*w:(col+1)*w]=cv2.applyColorMap(v,cv2.COLORMAP_TURBO)
        assert cv2.imwrite(str(stage/'artifacts/previews/input_depth_confidence.png'),panel)
        # Orthographic scatter previews with world axes, never a camera RGB reconstruction.
        bounds=np.percentile(xyz,cfg['visualization_percentiles'],axis=0);side=480
        canvas=np.full((550,side*3,3),255,np.uint8);view_rows=[]
        for t,(a,b) in enumerate([(0,1),(0,2),(1,2)]):
            keep=(xyz[:,a]>=bounds[0,a])&(xyz[:,a]<=bounds[1,a])&(xyz[:,b]>=bounds[0,b])&(xyz[:,b]<=bounds[1,b])
            coords=(xyz[keep][:,[a,b]]-bounds[0,[a,b]])/(bounds[1,[a,b]]-bounds[0,[a,b]])
            pix=np.rint(coords*(side-35)).astype(int);xx=pix[:,0]+t*side+15;yy=500-pix[:,1]
            canvas[yy,xx]=color[keep][:,::-1]
            label(canvas,f'world {"XYZ"[a]} / {"XYZ"[b]} (orthographic)',t*side+10,25)
            label(canvas,f'{int(keep.sum())} displayed / {len(xyz)}',t*side+10,530)
            view_rows.append({'axes':['XYZ'[a],'XYZ'[b]],'displayed':int(keep.sum()),'total':len(xyz)})
        assert cv2.imwrite(str(stage/'artifacts/previews/orthographic_scatter.png'),canvas)
        metrics={'point_count':len(xyz),'frames':rows,'all_xyz_finite':True,'raw_npz_byte_identical':True,'observations_npz_byte_identical':True,'per_frame_npz_reload':'passed','ply_reload':'passed','source_rgb_depth_provenance':'passed','display_limits':limits,'orthographic_world_bounds':bounds.tolist(),'orthographic_views':view_rows,'display_note':'percentile clipping affects previews only; last-write raster overlap; no physical visibility model','camera_rgb_rerender_performed':False,'fusion_performed':False,'optimization_performed':False,'gt_accuracy_evaluated':False,'cpu_packaging_seconds':time.perf_counter()-start}
        (stage/'evaluation/metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
        handoff={'experiment_code':'E0','run_id':args.run_id,'canonical_raw_npz':record(stage/'artifacts/baseline/vggt_omega_raw.npz'),'canonical_observations':record(stage/'artifacts/baseline/observations.npz'),'canonical_ply':record(stage/'artifacts/geometry/all_observations.ply'),'parents':parents,'coordinate_system':'OpenCV camera-from-world; camera Z depth; model world arbitrary scale','units':'model units, not metres','correspondence':'one observation per frame,pixel; no fusion','freeze':'read-only baseline; follow-up must write a new experiment/run directory'}
        (stage/'evaluation/baseline.json').write_text(json.dumps(handoff,indent=2)+'\n')
        (stage/'environment.json').write_text(json.dumps({'platform':platform.platform(),'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,'execution_context':'host CPU only; no GPU inference','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2))
        m={'status':'completed','experiment_code':'E0','run_id':args.run_id,'started_at':stamp,'ended_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'completion_criteria_met':True,'parent_manifests':parents}
        (stage/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(metrics,indent=2))
    except Exception as ex:
        (stage/'manifest.json').write_text(json.dumps({'status':'failed','started_at':stamp,'error':str(ex)},indent=2));raise


if __name__=='__main__':main()
