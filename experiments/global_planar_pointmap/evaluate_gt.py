"""I11: post-hoc TUM sensor-GT evaluation of frozen I10 outputs. CPU only.

No reconstruction is modified. Alignment uses baseline FIT pixels only; metrics
use the original I0 validation mask, shared across arms (no per-arm alignment).
"""
from core import *
import io
import tarfile
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation, Slerp

ARCHIVE=ROOT/'data/pointmap_refinement/tum/rgbd_dataset_freiburg1_desk.tgz'
PREFIX='rgbd_dataset_freiburg1_desk/'
SOURCE_URL='https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats'
ARMS=['initial','named_local','named_OR','retained']
GT_STATUS='GT_DEPTH_AND_REGISTERED_POINTMAP_EVALUATED'
PROTOCOL=dict(version='I11.2',gt_status=GT_STATUS,source_url=SOURCE_URL,
    evaluation_annotation='TUM registered sensor depth and mocap poses; no semantic or ideal-surface GT; no manual ROI',
    primary='camera-Z depth, common baseline median-ratio scale, no shift',
    secondary='corresponding world points, baseline FIT-only least-squares Sim(3), ROS default K',
    depth_divisor=5000.,additional_depth_correction=1.,rgb_depth_max_dt_seconds=.020,
    pose_max_bracket_gap_seconds=.040,resize='PIL bicubic RGB 640x480 -> 512x384; no crop',
    depth_sampling='nearest source pixel at half-pixel resize centers; no depth interpolation',
    gt_intrinsics_native=[[525.,0.,319.5],[0.,525.,239.5],[0.,0.,1.]],
    distortion='no rectification, ROS default per TUM recommendation; secondary 3D calibration approximate',
    fit_mask='I0 FIT AND valid sensor depth; baseline only',
    evaluation_mask='I0 validation AND valid sensor depth; identical for every arm',
    edge_sensitivity='additional fixed sensor mask: 3x3 all valid, max-min <= 0.05 metres',
    sim3_fit_cap=30000,subsets='all, OR projected, OR rescue, eligible, all-views-unknown, each assigned named tag',
    uncertainty='sensor depth reference, not semantic or ideal-surface GT; six RGB frames only; no SLAM benchmark')

def text_rows(raw):
    return [line.split() for line in raw.decode().splitlines() if line.strip() and not line.startswith('#')]

def collect_gt(frames):
    # Pass 1 gets timestamp tables. Pass 2 collects only selected images in one traversal.
    tables={}
    with tarfile.open(ARCHIVE,'r|gz') as tar:
        for item in tar:
            if item.name in [PREFIX+x for x in ['rgb.txt','depth.txt','groundtruth.txt']]:
                tables[Path(item.name).name]=tar.extractfile(item).read()
    depths=text_rows(tables['depth.txt']);dt=np.array([float(r[0]) for r in depths])
    rgb_table={r[0]:r[1] for r in text_rows(tables['rgb.txt'])}
    associations=[];wanted=set()
    for f in frames:
        stamp=Path(f['source_member']).stem;ts=float(stamp);j=int(np.argmin(abs(dt-ts)))
        assert abs(dt[j]-ts)<=PROTOCOL['rgb_depth_max_dt_seconds'],(ts,dt[j])
        assert rgb_table[stamp].endswith(Path(f['source_member']).name)
        row=dict(rgb_timestamp=ts,rgb_member=PREFIX+rgb_table[stamp],depth_timestamp=dt[j],
                 depth_member=PREFIX+depths[j][1],delta_seconds=float(dt[j]-ts),rgb_sha256=f['sha256'])
        associations.append(row);wanted|={row['rgb_member'],row['depth_member']}
    blobs={}
    with tarfile.open(ARCHIVE,'r|gz') as tar:
        for item in tar:
            if item.name in wanted:blobs[item.name]=tar.extractfile(item).read()
    assert set(blobs)==wanted
    for row in associations:
        assert hashlib.sha256(blobs[row['rgb_member']]).hexdigest()==row['rgb_sha256']
        row['depth_png_sha256']=hashlib.sha256(blobs[row['depth_member']]).hexdigest()
    return associations,blobs,tables

def camera_z(xyz,e,fid):
    return np.einsum('ni,ni->n',xyz,e[fid,2,:3])+e[fid,2,3]

def fit_sim3(x,y):
    xm=x.mean(0);ym=y.mean(0);xx=x-xm;yy=y-ym
    u,sv,vt=np.linalg.svd(yy.T@xx/len(x));sign=np.ones(3);sign[-1]=np.linalg.det(u@vt)
    rot=(u*sign)@vt;scale=float((sv*sign).sum()/np.mean(np.sum(xx*xx,axis=1)))
    trans=ym-scale*rot@xm
    assert scale>0 and np.linalg.det(rot)>.999999
    return scale,rot,trans

def depth_metrics(pred,gt,mask):
    p,g=pred[mask],gt[mask];assert np.isfinite(p).all() and np.all(p>0)
    if not len(p):return dict(count=0)
    err=p-g;ae=abs(err);ratio=np.maximum(p/g,g/p)
    return dict(count=int(len(p)),mae_m=float(ae.mean()),rmse_m=float(np.sqrt(np.mean(err**2))),
        abs_rel=float(np.mean(ae/g)),median_abs_error_m=float(np.median(ae)),p95_abs_error_m=float(np.quantile(ae,.95)),
        bias_m=float(err.mean()),delta_1_25=float(np.mean(ratio<1.25)))

def point_metrics(pred,gt,mask):
    err=np.linalg.norm(pred[mask]-gt[mask],axis=1)
    if not len(err):return dict(count=0)
    return dict(count=len(err),mean_m=float(err.mean()),rmse_m=float(np.sqrt(np.mean(err**2))),
        median_m=float(np.median(err)),p95_m=float(np.quantile(err,.95)))

def controls():
    # Closed-form recovery with a proper rotation/scale and metric sanity.
    rng=np.random.default_rng(11);x=rng.normal(size=(100,3));r=Rotation.from_rotvec([.1,-.2,.3]).as_matrix()
    y=2.3*x@r.T+np.array([.7,-.4,1.]);s,q,t=fit_sim3(x,y)
    assert np.max(abs(s*x@q.T+t-y))<1e-12
    m=depth_metrics(np.array([1.,2.]),np.array([1.,1.]),np.ones(2,bool))
    assert m['mae_m']==.5 and abs(m['rmse_m']-np.sqrt(.5))<1e-12
    return dict(sim3_recovery=True,metric_sanity=True)

def figure(st,d,gt,valid,pred,scale):
    n,h,w=d['depth'].shape;canvas=Image.new('RGB',(w*3,(h+32)*n),'white');draw=ImageDraw.Draw(canvas)
    for i in range(n):
        sl=slice(i*h*w,(i+1)*h*w)
        for j,arm in enumerate(['initial','named_OR']):
            error=(scale*pred[arm]-gt)[sl].reshape(h,w);v=valid[sl].reshape(h,w)
            # blue underestimation, red overestimation; saturation at 20 cm.
            t=np.clip(error/.2,-1,1);col=np.full((h,w,3),255.,float)
            col[:,:,0]-=255*np.maximum(-t,0);col[:,:,2]-=255*np.maximum(t,0);col[:,:,1]-=255*abs(t);col[~v]=[70,70,70]
            canvas.paste(Image.fromarray(col.astype('uint8')),((j+1)*w,i*(h+32)+32))
            draw.text(((j+1)*w+5,i*(h+32)+8),arm+' depth error: blue -20cm / red +20cm',fill='black')
        canvas.paste(Image.fromarray(d['rgb'][i]),(0,i*(h+32)+32));draw.text((5,i*(h+32)+8),str(d['frames'][i]['index'])+' RGB; gray = missing GT',fill='black')
    canvas.save(st.path/'artifacts/figures/depth_error.png')

def run(dataset):
    source=latest('I10',dataset);st=Stage('I11',dataset,[source],PROTOCOL)
    try:
        # Stage inherits the old I0 contract; explicitly freeze the new GT protocol separately.
        st.config.update(PROTOCOL);c.json_write(st.path/'config_resolved.json',st.config)
        c.json_write(st.path/'evaluation/gt_protocol.json',PROTOCOL)
        st.log('protocol_frozen',protocol_sha256=c.record(st.path/'evaluation/gt_protocol.json')['sha256'])
        checks=controls();d=load(dataset,True);N=len(d['ids']);n,h,w=d['depth'].shape
        maps={};inputs=[c.record(source/'manifest.json'),c.record(ARCHIVE),c.record(split_path(dataset)/'split.npz')]
        for arm in ARMS:
            p=source/'artifacts/named_or'/arm/'pointmap.npz';inputs.append(c.record(p))
            with np.load(p) as z:maps[arm]={k:z[k] for k in z.files}
            for key,v in [('observation_id',d['ids']),('frame_id',d['fid']),('pixel_uv',d['uv']),('intrinsics',d['k']),('extrinsics',d['e'])]:
                assert ahash(maps[arm][key])==ahash(v),(arm,key)
        assert ahash(maps['initial']['xyz'])==ahash(d['xyz'])
        assoc,blobs,tables=collect_gt(d['frames']);out=st.path/'artifacts/gt';out.mkdir()
        for row in assoc:
            for key in ['rgb_member','depth_member']:
                dest=out/row[key];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blobs[row[key]])
        for name,b in tables.items():(out/name).write_bytes(b)
        poses=np.array(text_rows(tables['groundtruth.txt']),float);times=poses[:,0]
        gt_depth=[];gt_world=[];smooth=[];uv_native=[]
        for i,row in enumerate(assoc):
            dep=np.array(Image.open(io.BytesIO(blobs[row['depth_member']]))).astype(float)/5000.
            assert dep.shape==(480,640)
            uv=d['uv'][i*h*w:(i+1)*h*w];native=(uv+.5)*1.25-.5;nearest=np.floor(native+.5).astype(int)
            z=dep[nearest[:,1],nearest[:,0]];gt_depth.append(z);uv_native.append(native)
            lo=ndimage.minimum_filter(dep,3,mode='constant',cval=0);hi=ndimage.maximum_filter(dep,3,mode='constant',cval=np.inf)
            smooth.append(((lo>0)&(hi-lo<=.05))[nearest[:,1],nearest[:,0]])
            # Poses are sampled at RGB timestamp, sensor depth has the recorded small time offset.
            ts=row['rgb_timestamp'];j=int(np.searchsorted(times,ts));assert 0<j<len(times)
            assert times[j]-times[j-1]<=PROTOCOL['pose_max_bracket_gap_seconds']
            a=(ts-times[j-1])/(times[j]-times[j-1]);t=(1-a)*poses[j-1,1:4]+a*poses[j,1:4]
            rot=Slerp(times[j-1:j+1],Rotation.from_quat(poses[j-1:j+1,4:8]))([ts]).as_matrix()[0]
            # Use the actual sampled source pixel for corresponding sensor points.
            cam=np.c_[(nearest[:,0]-319.5)/525.,(nearest[:,1]-239.5)/525.,np.ones(h*w)]*z[:,None]
            gt_world.append(cam@rot.T+t)
            row.update(pose_bracket=times[j-1:j+1].tolist(),translation=t.tolist(),rotation_camera_to_world=rot.tolist())
        gt=np.concatenate(gt_depth);world=np.vstack(gt_world);stable=np.concatenate(smooth);native=np.vstack(uv_native)
        valid=np.isfinite(gt)&(gt>0);sp=split_load(dataset);fit=sp['fit']&valid;test=sp['validation']&valid
        assert not np.any(fit&test) and fit.sum()>1000 and test.sum()>1000
        pred={a:camera_z(maps[a]['xyz'],d['e'],d['fid']) for a in ARMS}
        for a,p in pred.items():assert np.all(np.isfinite(p)&(p>0)),a
        scale=float(np.median(gt[fit]/pred['initial'][fit]))
        ix=np.flatnonzero(fit);ix=ix[np.linspace(0,len(ix)-1,min(len(ix),PROTOCOL['sim3_fit_cap']),dtype=int)]
        simscale,rot,trans=fit_sim3(maps['initial']['xyz'][ix],world[ix])
        align=dict(depth_scale=scale,depth_shift=0,fit_count=int(fit.sum()),fit_mask_hash=ahash(fit),
            sim3_scale=simscale,sim3_rotation=rot.tolist(),sim3_translation=trans.tolist(),sim3_fit_count=len(ix),
            sim3_fit_indices_hash=ahash(ix),fit_source='initial ONLY; identical transform applied to every arm')
        with np.load(source/'artifacts/named_or/semantic_OR.npz') as z:sem={k:z[k] for k in z.files}
        projected=maps['named_OR']['plane_id']>=0;rescue=projected&~sem['direct_named']
        subsets={'all':np.ones(N,bool),'projected_OR':projected,'rescued_OR':rescue,
                 'eligible_OR':sem['eligible'],'all_views_unknown':~sem['or_supported']&~sem['direct_named']&~sem['blocked_other_named']}
        planes=json.loads((source/'artifacts/named_or/named_OR/planes.json').read_text())['planes']
        for tag in ['wall','table','screen']:
            ids=[p['plane_id'] for p in planes if p['semantic_tag']==tag]
            subsets[tag]=np.isin(maps['named_OR']['plane_id'],ids)&projected
        metrics={}
        for arm in ARMS:
            aligned=simscale*maps[arm]['xyz']@rot.T+trans
            metrics[arm]={}
            for label,mask in subsets.items():
                take=test&mask
                metrics[arm][label]=dict(depth=depth_metrics(scale*pred[arm],gt,take),world_point=point_metrics(aligned,world,take),
                    depth_smooth=depth_metrics(scale*pred[arm],gt,take&stable))
            metrics[arm]['per_frame']=[depth_metrics(scale*pred[arm],gt,test&(d['fid']==i)) for i in range(n)]
        unchanged=~projected
        checks.update(unchanged_OR_xyz_bitwise=ahash(maps['initial']['xyz'][unchanged])==ahash(maps['named_OR']['xyz'][unchanged]),
            shared_metadata=True,shared_gt_mask=True,disjoint_alignment_evaluation=True,
            unknown_xyz_bitwise=ahash(maps['initial']['xyz'][subsets['all_views_unknown']])==ahash(maps['named_OR']['xyz'][subsets['all_views_unknown']]))
        assert all(checks.values()),checks
        baseline=metrics['initial']['all']['depth'];proposal=metrics['named_OR']['all']['depth']
        decision='DEPTH_GT_IMPROVED' if proposal['mae_m']<baseline['mae_m'] and proposal['rmse_m']<baseline['rmse_m'] else 'DEPTH_GT_MIXED_OR_WORSE'
        result=dict(decision=decision,scope='post-hoc frozen I10; 3 RGB frames; TUM sensor-depth reference',
            source_run=source.parents[1].name,protocol=PROTOCOL,alignment=align,associations=assoc,metrics=metrics,checks=checks,
            valid_sensor_count=int(valid.sum()),total_observations=N,evaluation_count=int(test.sum()),
            smooth_evaluation_count=int((test&stable).sum()),retained_equals_initial=ahash(maps['retained']['xyz'])==ahash(maps['initial']['xyz']),
            retained_equals_proposed=ahash(maps['retained']['xyz'])==ahash(maps['named_OR']['xyz']),
            delta_OR_minus_initial={k:proposal[k]-baseline[k] for k in ['mae_m','rmse_m','abs_rel','delta_1_25']},inputs=inputs)
        c.json_write(st.path/'evaluation/associations.json',assoc);c.json_write(st.path/'evaluation/alignment.json',align)
        np.savez_compressed(out/'evaluation_arrays.npz',depth_gt=gt,world_gt=world,uv_native=native,
            valid=valid,fit_mask=fit,test_mask=test,smooth_mask=stable,sim3_fit_indices=ix,**{'subset_'+k:v for k,v in subsets.items()},
            **{'depth_'+a:p for a,p in pred.items()})
        figure(st,d,gt,valid,pred,scale)
        report=['# I11 — 현재 I10 결과의 TUM GT 평가',
            f"\n대상 `{dataset}`. **{decision}**. 재구성·투영·retained 선택은 변경하지 않았다.",
            '\n## 평가 규약',
            f"\nTUM depth PNG / 5000을 m 단위 camera-Z 참조로 사용. 1.035 배율은 배포본에 이미 반영되어 재적용하지 않았다. RGB-depth 최근접 대응 상한 20 ms. 원래 RGB SHA-256도 archive와 일치한다. [TUM 공식 규약]({SOURCE_URL}).",
            f"\n640×480 RGB는 기존 PIL bicubic으로 512×384가 되었으며 crop은 없다. 평가 픽셀 중심을 원본으로 역매핑해 최근접 depth를 읽었다. depth 0은 제외한다. 비교군 공통 유효 센서 픽셀 {valid.sum():,}/{N:,}, 평가 픽셀 {test.sum():,}개.",
            f"\n깊이 scale **{scale:.10f} m/model-unit**는 initial의 기존 I0 FIT 픽셀 {fit.sum():,}개에서 GT/initial의 중앙값으로 한 번만 추정했다. shift 없음. 겹치지 않는 I0 validation에서 모든 비교군에 같은 scale·마스크를 사용했다. 비교군별 재정렬이나 GT를 이용한 모델 보정은 없다.",
            '\n## 깊이 정확도 (공통 validation; 낮을수록 좋음)',
            '\n| 출력 | MAE (cm) | RMSE (cm) | AbsRel | δ<1.25 |\n|---|---:|---:|---:|---:|']
        for a in ARMS:
            m=metrics[a]['all']['depth'];report.append(f"| {a} | {100*m['mae_m']:.4f} | {100*m['rmse_m']:.4f} | {m['abs_rel']:.6f} | {100*m['delta_1_25']:.3f}% |")
        report+=['\n## 영역별 initial → named_OR',
            '\n영역은 OR 결과로 고정한 동일 관측 집합이다. tag는 모델 추정이며 의미 GT가 아니다.',
            '\n| 영역 | GT 평가 픽셀 | MAE 전→후 (cm) | RMSE 전→후 (cm) |\n|---|---:|---:|---:|']
        for key in subsets:
            b=metrics['initial'][key]['depth'];a=metrics['named_OR'][key]['depth']
            if a['count']:report.append(f"| {key} | {a['count']:,} | {100*b['mae_m']:.4f} → {100*a['mae_m']:.4f} | {100*b['rmse_m']:.4f} → {100*a['rmse_m']:.4f} |")
        report+=['\n## 깊이 경계 민감도',
            '\n센서 depth의 원본 3×3 이웃이 모두 유효하고 범위가 5 cm 이하인 고정 마스크로도 측정했다. GT 경계·등록 오차에 대한 보조 진단이며 기본 평가를 대체하지 않는다.',
            '\n| 출력 | 픽셀 | MAE (cm) | RMSE (cm) |\n|---|---:|---:|---:|']
        for a in ARMS:
            m=metrics[a]['all']['depth_smooth'];report.append(f"| {a} | {m['count']:,} | {100*m['mae_m']:.4f} | {100*m['rmse_m']:.4f} |")
        report+=['\n## 대응 3D 점 보조 평가',
            f"\n공식 권장 ROS default K=(525,525,319.5,239.5), 추가 undistortion 없음. RGB timestamp에 mocap translation 선형보간·회전 SLERP. FIT 최대 30,000 대응점에서 initial만 Sim(3) 정렬하고 동일 변환으로 모든 출력의 validation 대응점 거리를 측정했다. scale={simscale:.10f}. 이는 NN Chamfer가 아니라 동일 관측 픽셀의 거리다. K 근사와 RGB-depth 시차의 영향을 포함한다.",
            '\n| 출력 | 3D mean (cm) | 3D RMSE (cm) |\n|---|---:|---:|']
        for a in ARMS:
            m=metrics[a]['all']['world_point'];report.append(f"| {a} | {100*m['mean_m']:.4f} | {100*m['rmse_m']:.4f} |")
        report+=['\n## 해석 범위',
            '\n깊이와 3D 수치는 서로 다른 baseline 공통 정렬을 사용하므로 직접 혼합하지 않는다. 보정되지 않은 metric scale 정확도, semantic GT, 이상적인 평면/직각 형태 정확도, 전체 시퀀스 SLAM 정확도를 입증하지 않는다. 센서 GT는 컵·종이·반사 screen에서 결측/오차가 있으며 결측부 정확도는 알 수 없다. 픽셀 수는 독립 장면 수가 아니므로 통계적 유의성을 주장하지 않는다.',
            '\nGT 평가 전에 선택한 I10 retained는 그대로 평가했다. extra의 visibility 실패 출력은 proposed 진단만 수행하며 retained로 승격하지 않았다. all_views_unknown의 좌표 동일성, FIT/validation 분리, 고정 metadata·마스크, Sim(3) 회복과 metric sanity 검증을 통과했다.',
            '\n![깊이 오차: 파랑 과소·빨강 과대, ±20cm](figures/depth_error.png)']
        st.log('gt_evaluation_saved',mae_initial=baseline['mae_m'],mae_OR=proposal['mae_m'])
        st.finish(result,'\n'.join(report),gt_status=GT_STATUS)
        return st,result
    except Exception as error:
        st.fail(error);raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['tum-freiburg1_desk','tum-freiburg1_desk-extra','all'],default='all');a=p.parse_args()
    for ds in (['tum-freiburg1_desk','tum-freiburg1_desk-extra'] if a.dataset=='all' else [a.dataset]):run(ds)
