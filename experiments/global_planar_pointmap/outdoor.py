"""Frozen O0 outdoor transfer; GT is opened only by the I26 evaluator."""
from core import *
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation
from eth3d_laser import infer, freeze, pipeline as full_pipeline

DATASETS=['kitti-city-0005','eth3d-forest-rig']
O0=ROOT/'results/outdoor_lidar_samples/O0-20261114-002'
DATA=ROOT/'data/outdoor_lidar_samples'
PLAN=ROOT/'docs/vggt_omega_outdoor_lidar_experiment_plan.md'
ARMS=['omega_raw','fov','plane_fixed','plane_distance','plane_distance_normal','retained']


def calib_file(path):
    values={}
    for line in path.read_text().splitlines():
        key,value=line.split(':',1)
        try:values[key]=np.array(list(map(float,value.split())))
        except ValueError:pass
    return values


def kitti_poses(names):
    root=DATA/'kitti_city/2011_09_26';seq=root/'2011_09_26_drive_0005_sync'
    cam=calib_file(root/'calib_cam_to_cam.txt');velo=calib_file(root/'calib_velo_to_cam.txt');imu=calib_file(root/'calib_imu_to_velo.txt')
    def matrix(rotation,translation):
        value=np.eye(4);value[:3,:3]=rotation;value[:3,3]=translation;return value
    projection=cam['P_rect_02'].reshape(3,4);K=projection[:,:3]
    camera_from_imu=matrix(np.eye(3),np.linalg.solve(K,projection[:,3]))@matrix(cam['R_rect_00'].reshape(3,3),np.zeros(3))@matrix(velo['R'].reshape(3,3),velo['T'])@matrix(imu['R'].reshape(3,3),imu['T'])
    packets=[np.loadtxt(seq/'oxts/data'/f'{name}.txt') for name in names]
    scale=np.cos(np.deg2rad(packets[0][0]));poses=[];origin=None
    for packet in packets:
        lat,lon,alt,roll,pitch,yaw=packet[:6]
        translation=np.array([scale*6378137.*np.deg2rad(lon),scale*6378137.*np.log(np.tan(np.deg2rad(90+lat)/2)),alt])
        if origin is None:origin=translation.copy()
        rotation=Rotation.from_euler('xyz',[roll,pitch,yaw]).as_matrix()
        poses.append((camera_from_imu@np.linalg.inv(matrix(rotation,translation-origin)))[:3])
    # Compare composed calibration with the original full projection, including camera-02 translation.
    points=np.random.default_rng(0).normal(size=(50,3));points[:,0]+=20
    v=np.c_[points,np.ones(len(points))]
    rect=matrix(cam['R_rect_00'].reshape(3,3),np.zeros(3));vc=matrix(velo['R'].reshape(3,3),velo['T'])
    reference=v@(projection@rect@vc).T
    transform=matrix(np.eye(3),np.linalg.solve(K,projection[:,3]))@rect@vc
    check=v@(K@transform[:3]).T
    assert np.max(abs(reference-check))<1e-9
    return np.array(poses),K,[c.record(root/name) for name in ['calib_cam_to_cam.txt','calib_velo_to_cam.txt','calib_imu_to_velo.txt']]+[c.record(seq/'oxts/data'/f'{name}.txt') for name in names]


def forest_poses(names):
    path=DATA/'eth3d_forest/extracted/forest/rig_calibration_undistorted/images.txt'
    rows=path.read_text().splitlines();poses={};index=0
    while index<len(rows):
        if not rows[index].strip() or rows[index].startswith('#'):index+=1;continue
        row=rows[index].split();assert len(row)==10
        key=row[9].replace('_undistorted/','/')
        if key in names:
            q=np.array(list(map(float,row[1:5])));r=Rotation.from_quat(q[[1,2,3,0]]).as_matrix()
            poses[key]=np.c_[r,np.array(list(map(float,row[5:8])))].tolist()
        index+=2
    assert len(poses)==len(names)
    return np.array([poses[name] for name in names]),[c.record(path),c.record(path.parent/'cameras.txt')]


def prepare(dataset):
    st=Stage('I14',dataset,extra=dict(protocol='outdoor O0 frozen inputs; GT arrays not read'))
    try:
        sample=next(x for x in json.loads((O0/'samples.json').read_text()) if x['dataset']==dataset)
        names=[frame['name'] for frame in sample['frames']]
        if dataset.startswith('kitti-'):poses,K,calibration=kitti_poses(names)
        else:poses,calibration=forest_poses(names)
        frames=[]
        for index,frame in enumerate(sample['frames']):
            path=ROOT/frame['image']['path'];assert c.record(path)['sha256']==frame['image']['sha256']
            width,height=Image.open(path).size
            crop_width=min(width,int(round(height/.5))) if height/width<.5 else width
            crop_height=min(height,int(round(width*2))) if height/width>2 else height
            left,top=(width-crop_width)//2,(height-crop_height)//2
            camera=frame.get('camera') or dict(model='PINHOLE',width=width,height=height,
                params=[float(K[0,0]),float(K[1,1]),float(K[0,2]+.5),float(K[1,2]+.5)])
            frames.append(dict(index=int(frame['name']) if dataset.startswith('kitti-') else index,name=frame['name'],
                path=str(path),sha256=frame['image']['sha256'],original_wh=[width,height],camera=camera,
                original_camera=frame.get('original_camera'),dataset_extrinsics=poses[index].tolist(),
                crop_box=[left,top,left+crop_width,top+crop_height],sample_index=index,
                preprocessing='official Omega central aspect crop then bicubic max_size 512, patch multiple'))
        c.json_write(st.path/'artifacts/frames.json',frames)
        shutil.copy2(PLAN,st.path/'artifacts/source/outdoor_plan.md')
        centers=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in poses])
        baselines=[float(np.linalg.norm(a-b)) for a,b in itertools.combinations(centers,2)]
        st.finish(dict(decision='OUTDOOR_RGB_CAMERA_INPUTS_FROZEN',frames=frames,calibration=calibration,
            pose_baselines_m=baselines,GT_arrays_read=False,selection=c.record(O0/'samples.json'),plan=c.record(PLAN)),
            f'# I14 — {dataset}\n\nO0의 3장을 고정했다. official loader의 crop/resize와 camera/pose 메타데이터를 기록했다. GT 깊이 배열은 열지 않았다. pose baselines(m)={baselines}.')
    except Exception as error:st.fail(error);raise


def processed_camera(frame,h,w):
    fx,fy,cx,cy=frame['camera']['params'];left,top,right,bottom=frame['crop_box']
    sx,sy=w/(right-left),h/(bottom-top)
    # Frame camera uses COLMAP corner origin; output K uses pixel index centers.
    return np.array([[fx*sx,0,(cx-left)*sx-.5],[0,fy*sy,(cy-top)*sy-.5],[0,0,1.]])


def no_named(dataset):
    import named_or,export as ex,photometric_planes
    from visualize_unknown import contact
    parent=latest('I1',dataset);tags=json.loads((parent/'artifacts/tags/mask_registry.json').read_text())
    anchors=[row for row in tags if row['source']=='grounded' and row['semantic_tag'] in named_or.ALLOWED]
    assert not anchors,'Early exit requires zero allowed anchors in ALL views'
    st=Stage('I10',dataset,[parent,latest('I2',dataset)],dict(branch='NO_NAMED_SUPPORT',geometry_search='skipped by exact no-anchor proof'))
    try:
        amendment=ROOT/'docs/vggt_omega_outdoor_lidar_amendment_A1.md';shutil.copy2(amendment,st.path/'artifacts/source/amendment_A1.md')
        d=load(dataset,True);N=len(d['ids']);n,h,w=d['depth'].shape;label=np.full(N,-1,np.int32)
        out=st.path/'artifacts/named_or';out.mkdir();records=[c.record(p/'manifest.json') for p in [parent,latest('I2',dataset)]]
        proof=dict(allowed_tags=sorted(named_or.ALLOWED),allowed_grounded_anchors=0,
            registry=c.record(parent/'artifacts/tags/mask_registry.json'),
            reason='Every I10 plane requires a group with a permitted named anchor. None exist in any view, regardless of geometry candidates or edges.',
            geometry_search_completed=False,amendment=c.record(amendment))
        c.json_write(out/'no_named_proof.json',proof);c.json_write(out/'association.json',dict(groups=[],edges=[],controls=proof))
        zeros=np.zeros(N,bool);np.savez_compressed(out/'semantic_OR.npz',direct_named=zeros,or_supported=zeros,eligible=zeros,blocked_other_named=zeros,observation_id=d['ids'])
        for name in ['initial','named_local','named_OR','retained']:
            named_or.save_map(out/name,d,d['xyz'],label,[],name,records)
            np.savez_compressed(out/name/'fit_support.npz')
            with np.load(out/name/'pointmap.npz') as z:assert np.array_equal(z['xyz'],d['xyz']) and (z['plane_id']==-1).all()
        visibility=ex.visibility(d,d['xyz']);summary=dict(accepted=0,accepted_fraction=0.,rescued_unknown_pixels=0,active_planes=0,
            accepted_by_tag={tag:0 for tag in sorted(named_or.ALLOWED)},visibility=visibility)
        rows=[];captions=[]
        for f in range(n):
            rgb=d['rgb'][f];red=np.rint(.6*rgb+.4*np.array([255,0,0])).astype('uint8')
            rows.append([rgb,red]);captions.append(f'frame {f}: no permitted named anchor')
        contact(st.path/'artifacts/figures/named_OR_mask.png',rows,['Original RGB','RED: excluded from plane projection'],captions)
        st.finish(dict(decision='NO_NAMED_SUPPORT',allowed_tags=sorted(named_or.ALLOWED),arms=dict(named_local=summary,named_OR=summary),
            raw_named_fraction=0.,eligible_OR_fraction=0.,no_named_support_unchanged_bitwise=True,other_named_blocked_bitwise=True,
            OR_order_invariant=True,retained='initial',geometry_types=['plane'],box_cylinder_sphere_applied=False,proof=proof),
            f'# I10 — {dataset}: NO_NAMED_SUPPORT\n\n모든 view에 허용 named anchor가 0개다. A1의 동일 출력 조기 종료를 적용했고 전체 I3/I4 기하 탐색은 완료하지 않았다. 네 출력 군의 XYZ가 FoV 출력과 bitwise 같음을 확인했다.\n\n![제외 영역](figures/named_OR_mask.png)')
    except Exception as error:st.fail(error);raise
    photometric_planes.run(dataset)


def pipeline(dataset):
    import named_or,solve
    tags=json.loads((latest('I1',dataset)/'artifacts/tags/mask_registry.json').read_text())
    if any(row['source']=='grounded' and row['semantic_tag'] in named_or.ALLOWED for row in tags):
        full_pipeline(dataset)
    else:
        solve.fov(dataset)
        no_named(dataset)


def gt_arrays(d):
    from eth3d_laser_evaluate import distort
    n,h,w=d['depth'].shape;uv=d['uv'][:h*w].astype(float);depths=[];worlds=[];smooth=[];records=[]
    sample=next(x for x in json.loads((O0/'samples.json').read_text()) if x['dataset']==d['dataset'])
    for index,(frame,source) in enumerate(zip(d['frames'],sample['frames'])):
        path=ROOT/source['gt_source']['path'];assert c.record(path)['sha256']==source['gt_source']['sha256'];records.append(c.record(path))
        K=processed_camera(frame,h,w);rays=np.c_[uv,np.ones(h*w)]@np.linalg.inv(K).T
        if d['dataset'].startswith('kitti-'):
            depth=np.array(Image.open(path)).astype(float)/256.;depth[depth==0]=np.inf
            left,top,right,bottom=frame['crop_box']
            mapped=(uv+.5)*[(right-left)/w,(bottom-top)/h]+[left,top]
        else:
            camera=frame['original_camera'];depth=np.memmap(path,dtype='<f4',mode='r',shape=(camera['height'],camera['width']))
            mapped=distort(rays[:,:2],camera['params'])
        ij=np.floor(mapped).astype(int);H,W=depth.shape
        inside=(ij[:,0]>=0)&(ij[:,0]<W)&(ij[:,1]>=0)&(ij[:,1]<H)
        x=ij[:,0].clip(0,W-1);y=ij[:,1].clip(0,H-1);z=np.array(depth[y,x],float);z[~inside]=np.inf
        neighborhood=np.array([depth[(y+dy).clip(0,H-1),(x+dx).clip(0,W-1)] for dy,dx in itertools.product([-1,0,1],repeat=2)])
        good=np.isfinite(neighborhood).all(0)&(neighborhood>0).all(0)&inside
        span=np.full(len(z),np.inf);span[good]=np.ptp(neighborhood[:,good],axis=0)
        smooth.append(good&(span<=.05))
        e=np.array(frame['dataset_extrinsics']);camera_points=rays*np.where(np.isfinite(z),z,0)[:,None]
        worlds.append((camera_points-e[:,3])@np.linalg.inv(e[:,:3]).T);depths.append(z)
    gt=np.concatenate(depths);return gt,np.vstack(worlds),np.isfinite(gt)&(gt>0),np.concatenate(smooth),records


def evaluate(dataset):
    from evaluate_gt import camera_z,depth_metrics,point_metrics,fit_sim3,GT_STATUS
    from raw_baseline import proper_rotation,pose_alignment
    from blur_evaluate import focal,epipolar
    source=latest('I12',dataset);st=Stage('I26',dataset,[source,latest('I14',dataset),latest('I15',dataset)],dict(protocol='outdoor raw-common comparison',GT_access='evaluation only'))
    try:
        shutil.copy2(PLAN,st.path/'artifacts/source/outdoor_plan.md')
        amendment=ROOT/'docs/vggt_omega_outdoor_lidar_amendment_A1.md'
        if amendment.exists():shutil.copy2(amendment,st.path/'artifacts/source/amendment_A1.md')
        assert not json.loads((source/'manifest.json').read_text())['gt_accuracy_evaluated']
        d=load(dataset);n,h,w=d['depth'].shape;N=len(d['ids']);split=split_load(dataset)
        st.log('open_GT_after_optimizer',optimizer_run=source.parents[1].name)
        gt,world,valid,smooth,inputs=gt_arrays(d);fit=split['fit']&valid;test=split['validation']&valid
        assert not (fit&test).any() and min(fit.sum(),test.sum())>=500
        arrays=st.path/'artifacts/laser_GT';arrays.mkdir()
        np.savez_compressed(arrays/'evaluation_arrays.npz',gt=gt,world_gt=world,valid=valid,fit_mask=fit,test_mask=test,smooth_mask=smooth)
        raw=st.path/'artifacts/omega_raw';raw.mkdir()
        np.savez_compressed(raw/'pointmap.npz',xyz=d['raw_xyz'],depth=d['depth'],intrinsics=d['k'],extrinsics=d['e'],
            rgb=d['raw_rgb'],frame_id=d['fid'],pixel_uv=d['uv'],observation_id=d['ids'],confidence=d['conf'])
        ply_write(raw/'pixel_rgb.ply',d,d['raw_xyz'],np.full(N,-1,np.int32),d['raw_rgb'])
        states={'omega_raw':dict(xyz=d['raw_xyz'],intrinsics=d['k'])};paths={'omega_raw':c.record(raw/'pointmap.npz')}
        for arm in ARMS[1:]:
            name='initial' if arm=='fov' else arm;path=source/'artifacts/photometric'/name/'pointmap.npz'
            with np.load(path) as z:states[arm]={key:z[key] for key in z.files}
            paths[arm]=c.record(path)
            for key,val in [('rgb',d['raw_rgb']),('frame_id',d['fid']),('pixel_uv',d['uv']),('observation_id',d['ids']),('extrinsics',d['e'])]:assert np.array_equal(states[arm][key],val),(arm,key)
        with np.load(latest('I2',dataset)/'artifacts/fov/pointmap.npz') as z:assert np.array_equal(z['xyz_raw'],d['raw_xyz'])
        pred={arm:camera_z(state['xyz'],d['e'],d['fid']) for arm,state in states.items()}
        assert np.max(abs(pred['omega_raw']-pred['fov']))<1e-8
        scale=float(np.median(gt[fit]/pred['omega_raw'][fit]));ix=np.flatnonzero(fit);ix=ix[np.linspace(0,len(ix)-1,min(len(ix),30000),dtype=int)]
        ss,r,t=fit_sim3(d['raw_xyz'][ix],world[ix]);surface=dict(sim3_scale=ss,sim3_rotation=r.tolist(),sim3_translation=t.tolist())
        gt_e=np.array([frame['dataset_extrinsics'] for frame in d['frames']]);gt_k=np.array([processed_camera(frame,h,w) for frame in d['frames']])
        gc=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in gt_e]);gq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in gt_e])
        pq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in d['e']])
        try:pose=pose_alignment(d['centers'],pq,gc,gq);pose_failure=None
        except AssertionError as error:pose=None;pose_failure=str(error)
        alignment=dict(depth_scale=scale,depth_shift=0,pose=pose,pose_failure=pose_failure,raw_surface=surface,
            fit_count=int(fit.sum()),test_count=int(test.sum()),fit_hash=ahash(fit),test_hash=ahash(test))
        label=states['plane_fixed']['plane_id']
        with np.load(source/'artifacts/photometric/support.npz') as z:optimized=z['optimized_mask']
        groups=dict(all=np.ones(N,bool),projected=label>=0,optimized=optimized,unknown_untouched=label<0)
        metrics={}
        for arm,state in states.items():
            result={}
            for group,mask in groups.items():
                take=test&mask;result[group]=dict(depth=depth_metrics(scale*pred[arm],gt,take),depth_smooth=depth_metrics(scale*pred[arm],gt,take&smooth))
                for name,transform in [('pose',pose),('raw_surface',surface)]:
                    if transform is None:result[group]['world_'+name]=None;continue
                    xyz=transform['sim3_scale']*state['xyz']@np.array(transform['sim3_rotation']).T+np.array(transform['sim3_translation'])
                    result[group]['world_'+name]=point_metrics(xyz,world,take)
            result['focal']=focal(state['intrinsics'],gt_k)
            result['per_frame']=[depth_metrics(scale*pred[arm],gt,test&(d['fid']==f)) for f in range(n)]
            metrics[arm]=result
        assert all(np.array_equal(states[arm]['xyz'][label<0],states['fov']['xyz'][label<0]) for arm in ['plane_fixed','plane_distance','plane_distance_normal'])
        opt=json.loads((source/'evaluation/metrics.json').read_text());count=int((test&optimized).sum())
        primary=metrics['plane_distance_normal']['all']['depth'];deltas={}
        for arm in ['omega_raw','plane_fixed']:
            base=metrics[arm]['all']['depth'];deltas[arm]=dict(MAE_relative_gain=1-primary['mae_m']/base['mae_m'],RMSE_change_m=primary['rmse_m']-base['rmse_m'])
        success=all(value['MAE_relative_gain']>=.01 and value['RMSE_change_m']<=0 for value in deltas.values()) and opt['primary_passes_rgb_visibility']
        decision='INSUFFICIENT_SUPPORT' if count<500 else 'GT_IMPROVED' if success else 'NO_CONFIRMED_GAIN'
        result=dict(decision=decision,dataset=dataset,metrics=metrics,alignment=alignment,comparisons=deltas,
            raw_point_count=N,raw_bitwise_matches_beta1=True,raw_vs_fov_Z_max=float(abs(pred['omega_raw']-pred['fov']).max()),
            unknown_unchanged_bitwise=True,GT_valid_fraction=float(valid.mean()),optimized_test_GT_count=count,
            optimized_plane_count=opt['optimized_plane_count'],validation_RGB_gain=opt['validation_relative_gain'] if opt['optimized_plane_count'] else None,
            empty_photo_gain_policy='undefined when no supported plane; legacy I12 aggregate can report 1.0 for zero/zero and is not an improvement',
            primary_passes_RGB_visibility=opt['primary_passes_rgb_visibility'],paths=paths,inputs=inputs,
            epipolar=epipolar(m.load(split_path(dataset)/'matches.npz'),gt_k,gt_e),
            GT_sensor='Velodyne HDL-64E annotated LiDAR depth; OXTS pose' if dataset.startswith('kitti-') else 'FARO Focus X330 rendered depth; ETH3D registered camera pose',
            no_GT_optimizer=True,plan=c.record(PLAN))
        c.json_write(st.path/'evaluation/alignment.json',alignment)
        error_figure(st,d,gt,valid,pred,scale)
        rows=['| arm | depth MAE (m) | RMSE (m) | focal error (%) |','|---|---:|---:|---:|']
        for arm in ARMS:
            item=metrics[arm];rows.append(f"| {arm} | {item['all']['depth']['mae_m']:.6f} | {item['all']['depth']['rmse_m']:.6f} | {item['focal']['mean_abs_relative_percent']:.4f} |")
        st.finish(result,f'# I26 — {dataset} 야외 LiDAR 평가\n\n판정 **{decision}**, 최적화 평면 {opt["optimized_plane_count"]}, 최적화 영역 보류 GT {count}개.\n\n'+'\n'.join(rows)+'\n\nRaw FIT scale 하나와 고정 보류 mask를 모든 군에 공통 적용했다. raw/FoV는 Z가 같다. pose 및 raw FIT 표면 공통 3D 정렬은 JSON에 각각 기록했다. 동적 물체 제거 없이 기존 전체 화면 알고리즘을 전이했으며 forest는 흑백이다.\n\n![GT 오차](figures/GT_comparison.png)',gt_status=GT_STATUS)
    except Exception as error:st.fail(error);raise


def error_figure(st,d,gt,valid,pred,scale):
    n,h,w=d['depth'].shape;canvas=Image.new('RGB',(w*4,(h+30)*n),'white');draw=ImageDraw.Draw(canvas)
    bound=2. if d['dataset'].startswith('kitti-') else .2
    for f in range(n):
        sl=slice(f*h*w,(f+1)*h*w);top=f*(h+30)
        canvas.paste(Image.fromarray(d['rgb'][f]),(0,top+30));draw.text((5,top+5),'RGB',fill='black')
        for j,arm in enumerate(['omega_raw','fov','plane_distance_normal'],1):
            error=np.zeros(h*w);error[valid[sl]]=(scale*pred[arm][sl][valid[sl]]-gt[sl][valid[sl]])/bound
            v=np.clip(error.reshape(h,w),-1,1);col=np.full((h,w,3),255.)
            col[:,:,0]-=255*np.maximum(-v,0);col[:,:,2]-=255*np.maximum(v,0);col[:,:,1]-=255*abs(v)
            col[~valid[sl].reshape(h,w)]=[70,70,70]
            canvas.paste(Image.fromarray(col.astype('uint8')),(j*w,top+30));draw.text((j*w+5,top+5),arm+f' +/-{bound}m',fill='black')
    canvas.save(st.path/'artifacts/figures/GT_comparison.png')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','infer','freeze','segment','pipeline','no_named','evaluate']);parser.add_argument('--dataset',choices=DATASETS+['all'],default='all');args=parser.parse_args()
    datasets=DATASETS if args.dataset=='all' else [args.dataset]
    if args.mode=='infer':infer(datasets)
    elif args.mode=='segment':
        import segment;segment.run(datasets)
    else:
        for dataset in datasets:{'prepare':prepare,'freeze':freeze,'pipeline':pipeline,'no_named':no_named,'evaluate':evaluate}[args.mode](dataset)
