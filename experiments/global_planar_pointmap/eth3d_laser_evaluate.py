"""I20: official laser-rendered camera-Z GT with explicit distortion transfer."""
from core import *
from eth3d_laser import DATA, PLAN, DATASETS, extract_archive
from evaluate_gt import camera_z, depth_metrics, point_metrics, fit_sim3
from evaluate_photometric_planes import error_figure, ARMS
from eth3d_laser_download import OFFICIAL_SOURCES

OFFICIAL_FILES=OFFICIAL_SOURCES
GT_STATUS='GT_DEPTH_AND_REGISTERED_POINTMAP_EVALUATED'

def distort(xy,params):
    fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,sx,sy=params
    x,y=xy.T;r=np.sqrt(x*x+y*y);theta=np.arctan(r);factor=np.divide(theta,r,out=np.ones_like(r),where=r>1e-15)
    a=x*factor;b=y*factor;t2=theta**2
    radial=1+t2*(k1+t2*(k2+t2*(k3+t2*k4)))
    dx=a*radial+2*p1*a*b+p2*(t2+2*a*a)+sx*t2
    dy=b*radial+2*p2*a*b+p1*(t2+2*b*b)+sy*t2
    return np.c_[fx*dx+cx,fy*dy+cy]

def pixel_map(frame,h,w):
    # COLMAP uses corner-origin coordinates; model UV arrays use pixel index centers.
    uv=np.indices((h,w))[::-1].reshape(2,-1).T.astype(float)
    camera=frame['camera'];fx,fy,cx,cy=camera['params'];W,H=camera['width'],camera['height']
    native=(uv+.5)*np.array([W/w,H/h])
    rays=(native-np.array([cx,cy]))/np.array([fx,fy])
    distorted=distort(rays,frame['original_camera']['params'])
    return rays,native,distorted

def official_binary():
    directory=DATA/'official_camera';directory.mkdir(exist_ok=True)
    for name in OFFICIAL_FILES:
        if not (directory/name).exists():
            raise FileNotFoundError('Run eth3d_laser_download.py outside sandbox first: '+name)
    binary=directory/'camera_probe';probe=SOURCE/'eth3d_camera_probe.cpp'
    if not binary.exists() or binary.stat().st_mtime<probe.stat().st_mtime:
        subprocess.run(['g++','-std=c++14','-O2','-I',str(directory),str(probe),str(directory/'camera.cc'),'-o',str(binary)],check=True,capture_output=True)
    return directory,binary

def controls(dataset):
    directory,binary=official_binary();d=load(dataset);n,h,w=d['depth'].shape;scene=dataset.removeprefix('eth3d-')
    names={f['name'] for f in d['frames']}
    extract_archive(DATA/'archives'/f'{scene}_dslr_jpg.7z',DATA/'extracted',lambda path:Path(path).name in names)
    checks=[]
    for frame in d['frames']:
        rays,native,distorted=pixel_map(frame,h,w);idx=np.linspace(0,len(rays)-1,4096,dtype=int);cam=frame['original_camera']
        txt=f"{cam['width']} {cam['height']}\n"+' '.join(map(str,cam['params']))+'\n'+'\n'.join(f'{x:.14g} {y:.14g}' for x,y in rays[idx])+'\n'
        output=subprocess.check_output([str(binary)],input=txt,text=True)
        independent=np.array([list(map(float,line.split())) for line in output.splitlines()])
        error=float(abs(independent-distorted[idx]).max());assert error<.003,error
        original=DATA/'extracted'/scene/'images'/frame['original_image']
        native_image=c.cv2.imread(frame['original_path']);source=c.cv2.imread(str(original));assert source is not None
        maps=distorted[idx]-.5;native_maps=native[idx]-.5
        sample=c.cv2.remap(source,maps[:,0].astype('float32')[:,None],maps[:,1].astype('float32')[:,None],c.cv2.INTER_LINEAR)[:,0]
        expected=c.cv2.remap(native_image,native_maps[:,0].astype('float32')[:,None],native_maps[:,1].astype('float32')[:,None],c.cv2.INTER_LINEAR)[:,0]
        delta=abs(sample.astype(float)-expected.astype(float))/255.
        mae=float(delta.mean());assert mae<.05,(frame['name'],mae)
        checks.append(dict(frame=frame['name'],official_cpp_max_pixel_error=error,undistorted_vs_original_RGB_MAE=mae,
            raw_shape=list(source.shape),undistorted_shape=list(native_image.shape),original_RGB=c.record(original)))
    return dict(checks=checks,pixel_origin='COLMAP corner; official class uses center, cx/cy shifted -0.5; original nearest array index=floor(projected corner coord)',
        official_sources=[c.record(directory/name) for name in OFFICIAL_FILES],
        camera_source_commit='d1bb0163229925f44ce9b52b384ab458f42712ba',
        camera_source_url='https://github.com/ETH3D/camera-model-implementations/tree/d1bb0163229925f44ce9b52b384ab458f42712ba',
        depth_source_url='https://github.com/ETH3D/dataset-pipeline/blob/e09275b39b30c9c59abf535b849fcc539dc03efd/src/exe/ground_truth_creator.cc',
        depth_definition='gt_depth_map(iy,ix)=min(..., image_point.z()); observed in >=2 images, occlusion and masks checked')

def run(dataset):
    source=latest('I12',dataset);st=Stage('I20',dataset,[source,latest('I14',dataset),latest('I15',dataset)],
        dict(gt_status=GT_STATUS,evaluation_annotation='Independent FARO laser-scan rendered ETH3D camera-Z; not Kinect depth',protocol='ETH3D transfer v1; same I12 success thresholds'))
    try:
        st.config.update(gt_status=GT_STATUS,evaluation_annotation='Independent FARO laser-scan rendered ETH3D camera-Z; not Kinect depth')
        c.json_write(st.path/'config_resolved.json',st.config)
        assert json.loads((source/'manifest.json').read_text())['status']=='completed'
        opt=json.loads((source/'evaluation/metrics.json').read_text());assert not opt['GT_read_during_optimization']
        d=load(dataset,True);n,h,w=d['depth'].shape;N=len(d['ids']);scene=dataset.removeprefix('eth3d-')
        calibration_checks=controls(dataset);c.json_write(st.path/'evaluation/calibration_checks.json',calibration_checks)
        official_dir,_=official_binary();shutil.copytree(official_dir,st.path/'artifacts/source/official_camera',ignore=shutil.ignore_patterns('camera_probe'))
        shutil.copy2(SOURCE/'eth3d_camera_probe.cpp',st.path/'artifacts/source/eth3d_camera_probe.cpp')
        names={f['name'] for f in d['frames']}
        st.log('open_laser_GT_after_optimizer',source_run=source.parents[1].name)
        files=extract_archive(DATA/'archives'/f'{scene}_dslr_depth.7z',DATA/'extracted',lambda path:Path(path).name in names)
        gt=[];world=[];smooth=[];mapping=[];input_gt=[]
        for frame in d['frames']:
            path=next(p for p in files if p.name==frame['name']);cam=frame['original_camera'];ow,oh=cam['width'],cam['height']
            assert path.stat().st_size==ow*oh*4,(path,path.stat().st_size,ow,oh)
            depth=np.memmap(path,dtype='<f4',mode='r',shape=(oh,ow));rays,native,xy=pixel_map(frame,h,w)
            ij=np.floor(xy).astype(int);inside=(ij[:,0]>=0)&(ij[:,0]<ow)&(ij[:,1]>=0)&(ij[:,1]<oh)
            x=ij[:,0].clip(0,ow-1);y=ij[:,1].clip(0,oh-1);z=np.asarray(depth[y,x],float);z[~inside]=np.inf
            support=np.array([depth[(y+dy).clip(0,oh-1),(x+dx).clip(0,ow-1)] for dy,dx in itertools.product([-1,0,1],repeat=2)])
            ok=np.isfinite(support).all(0)&(support>0).all(0)&inside
            span=np.full(len(z),np.inf);span[ok]=np.ptp(support[:,ok],axis=0);smooth.append(ok&(span<=.05))
            e=np.array(frame['dataset_extrinsics']);camera=np.c_[rays,np.ones(len(rays))]*np.where(np.isfinite(z),z,0)[:,None]
            world.append((camera-e[:,3])@np.linalg.inv(e[:,:3]).T);gt.append(z);mapping.append(xy);input_gt.append(c.record(path));del depth,support
        gt=np.concatenate(gt);world=np.vstack(world);stable=np.concatenate(smooth);valid=np.isfinite(gt)&(gt>0)
        sp=split_load(dataset);fit=sp['fit']&valid;test=sp['validation']&valid;assert not np.any(fit&test)
        assert fit.sum()>=500 and test.sum()>=500,(int(fit.sum()),int(test.sum()))
        maps={};inputs=[c.record(source/'manifest.json'),c.record(PLAN),c.record(split_path(dataset)/'split.npz')]+input_gt
        for arm in ARMS:
            path=source/'artifacts/photometric'/arm/'pointmap.npz';inputs.append(c.record(path))
            with np.load(path) as z:maps[arm]={k:z[k] for k in z.files}
            for key,v in [('rgb',d['raw_rgb']),('frame_id',d['fid']),('pixel_uv',d['uv']),('intrinsics',d['k']),('extrinsics',d['e']),('observation_id',d['ids'])]:assert np.array_equal(maps[arm][key],v),(arm,key)
        pred={a:camera_z(z['xyz'],d['e'],d['fid']) for a,z in maps.items()}
        scale=float(np.median(gt[fit]/pred['initial'][fit]));sample=np.flatnonzero(fit);sample=sample[np.linspace(0,len(sample)-1,min(len(sample),30000),dtype=int)]
        simscale,rot,trans=fit_sim3(maps['initial']['xyz'][sample],world[sample])
        with np.load(source/'artifacts/photometric/support.npz') as z:optimized=z['optimized_mask']
        label=maps['plane_fixed']['plane_id'];planes=json.loads((latest('I10',dataset)/'artifacts/named_or/named_OR/planes.json').read_text())['planes']
        subsets={'all':np.ones(N,bool),'projected':label>=0,'optimized':optimized,'unknown_untouched':label<0}
        for tag in ['wall','table','screen']:subsets[tag]=np.isin(label,[p['plane_id'] for p in planes if p['semantic_tag']==tag])&(label>=0)
        metrics={}
        for arm,mp in maps.items():
            wx=simscale*mp['xyz']@rot.T+trans;metrics[arm]={}
            for name,mask in subsets.items():
                take=test&mask;metrics[arm][name]=dict(depth=depth_metrics(scale*pred[arm],gt,take),
                    depth_smooth=depth_metrics(scale*pred[arm],gt,take&stable),world_point=point_metrics(wx,world,take))
            metrics[arm]['per_frame']=[depth_metrics(scale*pred[arm],gt,test&(d['fid']==i)) for i in range(3)]
        primary=metrics['plane_distance_normal']['all']['depth'];comparison={}
        for arm in ['initial','plane_fixed']:
            base=metrics[arm]['all']['depth'];comparison[arm]=dict(mae_relative_gain=1-primary['mae_m']/base['mae_m'],rmse_change_m=primary['rmse_m']-base['rmse_m'])
        count=int((test&optimized).sum());success=all(x['mae_relative_gain']>=.01 and x['rmse_change_m']<=0 for x in comparison.values()) and opt['primary_passes_rgb_visibility']
        decision='INSUFFICIENT_SUPPORT' if count<500 else ('GT_IMPROVED' if success else 'NO_CONFIRMED_GAIN')
        checks=dict(shared_metadata=True,disjoint_scale_evaluation=True,
            unchanged_unknown=all(np.array_equal(z['xyz'][label<0],d['xyz'][label<0]) for z in maps.values()),
            unchanged_unsupported=all(np.array_equal(maps[a]['xyz'][(label>=0)&~optimized],maps['plane_fixed']['xyz'][(label>=0)&~optimized]) for a in ['plane_distance','plane_distance_normal']))
        assert all(checks.values()),checks
        alignment=dict(depth_scale=scale,depth_shift=0,fit_count=int(fit.sum()),fit_hash=ahash(fit),evaluation_hash=ahash(test),
            sim3_scale=simscale,sim3_rotation=rot.tolist(),sim3_translation=trans.tolist(),sim3_fit_indices_hash=ahash(sample))
        out=st.path/'artifacts/laser_GT';out.mkdir();np.savez_compressed(out/'evaluation_arrays.npz',gt=gt,world_gt=world,
            native_distorted_xy=np.vstack(mapping),valid=valid,fit_mask=fit,test_mask=test,smooth_mask=stable,optimized_mask=optimized,
            **{'depth_'+a:p for a,p in pred.items()})
        c.json_write(st.path/'evaluation/alignment.json',alignment)
        error_figure(st,d,gt,valid,pred,scale)
        result=dict(decision=decision,dataset=dataset,GT_sensor='FARO Focus X330 laser scanner; official occlusion-aware rendered depth',
            metrics=metrics,comparison=comparison,alignment=alignment,checks=checks,inputs=inputs,calibration=calibration_checks,
            optimized_GT_count=count,evaluation_count=int(test.sum()),valid_GT_count=int(valid.sum()),total_observations=N,
            optimized_planes=opt['optimized_plane_count'],optimized_observations=opt['optimized_observations'],
            rgb_validation_relative_gain=opt['validation_relative_gain'],rgb_validation=opt['validation_photo'],
            rgb_visibility_pass=opt['primary_passes_rgb_visibility'],retained=opt['retained'],source_run=source.parents[1].name)
        report=[f'# I20 — {dataset} 레이저 GT 평가',f'\n**{decision}**. 원래 Kinect 장면이 아닌 ETH3D 실내 레이저 GT로 같은 평면 RGB 최적화를 평가했다.',
            f"\n최적화 평면 {opt['optimized_plane_count']}개, 소속 {opt['optimized_observations']:,}점, optimized GT validation {count:,}개. 전체 GT validation {test.sum():,}개. 유효 GT {valid.sum():,}/{N:,}.",
            f"\n보류 RGB 상대 감소 {opt['validation_relative_gain']:.4%}, RGB/가시성 통과={opt['primary_passes_rgb_visibility']}, retained=`{opt['retained']}`.",
            '\n## 전체 camera-Z 깊이 정확도',
            '\n| 출력 | MAE (cm) ↓ | RMSE (cm) ↓ | AbsRel ↓ | δ<1.25 ↑ |\n|---|---:|---:|---:|---:|']
        for arm in ARMS:
            mm=metrics[arm]['all']['depth'];report.append(f"| {arm} | {100*mm['mae_m']:.5f} | {100*mm['rmse_m']:.5f} | {mm['abs_rel']:.7f} | {100*mm['delta_1_25']:.3f}% |")
        report+=['\n## 영역별 plane_fixed → 거리 → 거리·법선',
            '\n| 영역 | GT 픽셀 | fixed MAE(cm) | 거리 MAE(cm) | 거리·법선 MAE(cm) |\n|---|---:|---:|---:|---:|']
        for name in subsets:
            ms=[metrics[a][name]['depth'] for a in ['plane_fixed','plane_distance','plane_distance_normal']]
            if ms[0]['count']:report.append(f"| {name} | {ms[0]['count']:,} | {100*ms[0]['mae_m']:.5f} | {100*ms[1]['mae_m']:.5f} | {100*ms[2]['mae_m']:.5f} |")
        report+=['\n## 보정·정렬 검증과 제한',
            f"\n원본 왜곡된 RGB 격자의 4-byte camera-Z depth를 읽었다. processed pixel center→공식 PINHOLE 광선→공식 THIN_PRISM_FISHEYE→원본 depth 순서로 대응했다. 결측 infinity/비양수는 제외하고 보간·hole filling은 하지 않았다. COLMAP corner-origin과 공식 loader의 -0.5 pixel center shift를 일치시켰다. 각 이미지의 4096개 광선을 수정하지 않은 공식 standalone C++ 카메라 구현과 0.003 px 이하로 대조했고 원본/undistorted RGB 대응도 확인했다.",
            f"\ninitial FIT {fit.sum():,}개에서 단일 scale={scale:.10f}을 구해 모든 비교군에 고정했다. validation과 분리했으며 비교군별 재정렬·GT 기반 보정은 없다. 대응 3D 보조 지표는 동일 baseline FIT-only Sim(3)로 별도 저장했다. 원래 왜곡 픽셀의 최근접 샘플과 processed 중심 광선의 미세 차이가 남는다.",
            '\nSAM은 DSLR 전체 해상도 대신 동일 processed RGB에서 실행했다. 태그 허용은 wall/table/screen 그대로이며 floor·파이프·다른 primitive를 추가하지 않았다. most plane IDs는 단일 view 패치일 수 있고 RGB/geometry/의미 GT의 역할을 구분한다. 저텍스처·가림·반사·JPEG·카메라 추정 오차가 남는다. 공개 training split 샘플의 3장 소규모 평가이며 ETH3D 공식 benchmark 점수나 전체 SLAM 성능이 아니다.',
            '\n[데이터 규약](https://eth3d.ethz.ch/documentation) · [공식 depth 생성 코드](https://github.com/ETH3D/dataset-pipeline/blob/master/src/exe/ground_truth_creator.cc)',
            '\n![레이저 GT 오차: 전체 유효 픽셀 표시, 수치는 validation](figures/gt_depth_error.png)']
        st.finish(result,'\n'.join(report),gt_status=GT_STATUS);return st
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--controls-only',action='store_true');p.add_argument('--scene',choices=['office','pipes','all'],default='all');args=p.parse_args()
    for ds in (DATASETS if args.scene=='all' else ['eth3d-'+args.scene]):
        if args.controls_only:print(json.dumps(dict(dataset=ds,**controls(ds))))
        else:run(ds)
