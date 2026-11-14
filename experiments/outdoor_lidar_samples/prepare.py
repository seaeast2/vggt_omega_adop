"""O0: freeze and validate downloaded outdoor samples, without model inference."""
from acquire import *
import itertools
import shutil
import time
import traceback
import numpy as np
from PIL import Image, ImageDraw
from eth3d_laser_evaluate import distort
from scipy.spatial.transform import Rotation


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


def read_calib(path):
    result={}
    for line in path.read_text().splitlines():
        key,value=line.split(':',1)
        try:result[key]=np.array([float(x) for x in value.split()])
        except ValueError:pass
    return result


def rig_calibration(directory):
    cameras,_=calibration(directory)
    rows=(directory/'images.txt').read_text().splitlines();images={};index=0
    while index<len(rows):
        if not rows[index].strip() or rows[index].startswith('#'):
            index+=1;continue
        row=rows[index].split();assert len(row)==10
        quat=np.array(list(map(float,row[1:5])))
        rotation=Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()
        points=rows[index+1].split()
        # Different rig cameras share timestamps/basenames: retain the camera directory.
        key=row[9].replace('_undistorted/','/')
        assert key not in images
        images[key]=dict(name=row[9],camera_id=int(row[8]),image_id=int(row[0]),
            e=np.c_[rotation,np.array(list(map(float,row[5:8])))].tolist(),
            track_ids={int(v) for v in points[2::3] if int(v)>=0})
        index+=2
    assert len(images)==1028,len(images)
    return cameras,images


def kitti_sample(out):
    acquisition=json.loads((DATA/'kitti_city/acquisition.json').read_text())
    root=DATA/'kitti_city/2011_09_26';seq=root/acquisition['sequence']
    calib=read_calib(root/'calib_cam_to_cam.txt');P=calib['P_rect_02'].reshape(3,4)
    K=P[:,:3];frames=[]
    for index in acquisition['frames']:
        image=seq/'image_02/data'/f'{index}.png'
        candidates=list((DATA/'kitti_city').glob(f'*/{acquisition["sequence"]}/proj_depth/groundtruth/image_02/{index}.png'))
        assert len(candidates)==1,candidates
        gt=candidates[0];im=Image.open(image);encoded=np.array(Image.open(gt))
        assert im.mode=='RGB' and im.size==tuple(map(int,calib['S_rect_02']))
        assert encoded.shape==np.array(im).shape[:2] and encoded.dtype in (np.uint16,np.int32)
        depth=encoded.astype(np.float32)/256.;valid=encoded>0
        assert valid.sum()>1000
        cloud=seq/'velodyne_points/data'/f'{index}.bin';points=np.fromfile(cloud,dtype='<f4').reshape(-1,4)
        assert len(points)>10000 and np.isfinite(points).all()
        target=out/f'kitti-city-0005/{index}.npz';target.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(target,depth_m=depth,valid=valid,intrinsics=K,projection_rect_02=P)
        frames.append(dict(name=index,image=record(image),gt_source=record(gt),raw_lidar=record(cloud),
            prepared=record(target),width=im.width,height=im.height,color_mode=im.mode,
            valid_pixels=int(valid.sum()),valid_fraction=float(valid.mean()),
            depth_range_m=[float(depth[valid].min()),float(depth[valid].max())],lidar_points=len(points)))
    return dict(dataset='kitti-city-0005',category='urban street; vehicle-mounted ground camera',frames=frames,
        acquisition=record(DATA/'kitti_city/acquisition.json'),
        depth_definition='Official annotated accumulated/filtered LiDAR depth, meters; native rectified image_02 coordinates',
        limitations=['GT is semi-dense; only valid pixels can be evaluated.',
            'Cars, cyclists and pedestrians can move; static multiview geometry must mask dynamic objects.',
            'These are acquisition checks, not a calibrated reprojection/pose validation or an Omega accuracy result.'],
        model_inference=False,GT_accuracy_evaluated=False)


def forest_sample(out):
    folder=DATA/'eth3d_forest';root=folder/'extracted';archives=folder/'archives'
    camera_paths=list(root.glob('**/*calibration_undistorted/cameras.txt'));assert len(camera_paths)==1,camera_paths
    uc=camera_paths[0].parent
    other=[p.parent for p in root.glob('**/cameras.txt') if p.parent!=uc];assert len(other)==1,other
    cameras,images=rig_calibration(uc);oc,oi=rig_calibration(other[0])
    groups={key:sorted(name for name,im in images.items() if im['camera_id']==key) for key in cameras}
    proposals=[]
    for key,names in groups.items():
        for step in [5,10,20]:
            for start in range(len(names)-2*step):
                triple=[names[start+i*step] for i in range(3)];entries=[images[x] for x in triple]
                support=[len(a['track_ids']&b['track_ids']) for a,b in itertools.combinations(entries,2)]
                centers=[-np.linalg.solve(np.array(e['e'])[:,:3],np.array(e['e'])[:,3]) for e in entries]
                baseline=min(np.linalg.norm(a-b) for a,b in itertools.combinations(centers,2))
                if baseline>.01:proposals.append((min(support),sum(support),triple,support,float(baseline)))
    assert proposals
    score,_,names,support,baseline=sorted(proposals,key=lambda x:(-x[0],-x[1],x[2]))[0]
    assert score>=20,score
    # Freeze selection before opening laser depth; GT coverage never chooses frames.
    write_json(out/'eth3d-forest-rig/selection.json',dict(names=names,pair_shared_RGB_tracks=support,
        minimum_baseline_dataset_units=baseline,rule='Same-camera temporal gaps 5/10/20; maximize minimum then total RGB SfM covisibility',
        laser_GT_used_for_selection=False))
    selected=set(names)
    originals=extract_archive(archives/'forest_rig.7z',root,lambda path:any(path.endswith('/'+key) for key in selected))
    depths=extract_archive(archives/'forest_rig_depth.7z',root,lambda path:any(path.endswith('/'+key) for key in selected))
    frames=[]
    scene=uc.parent
    for name in names:
        entry=images[name];camera=cameras[entry['camera_id']];orig=oi[name];original_camera=oc[orig['camera_id']]
        assert camera['model']=='PINHOLE' and original_camera['model']=='THIN_PRISM_FISHEYE'
        assert np.max(abs(np.array(entry['e'])-np.array(orig['e'])))<1e-4
        image=scene/'images'/entry['name'];im=Image.open(image)
        assert im.size==(camera['width'],camera['height'])
        gt=next(p for p in depths if str(p).endswith('/'+name));W,H=original_camera['width'],original_camera['height']
        assert gt.stat().st_size==W*H*4
        source_depth=np.memmap(gt,dtype='<f4',mode='r',shape=(H,W))
        w,h=im.size;uv=np.indices((h,w))[::-1].reshape(2,-1).T+.5
        fx,fy,cx,cy=camera['params'];rays=(uv-[cx,cy])/[fx,fy]
        distorted=distort(rays,original_camera['params']);ij=np.floor(distorted).astype(int)
        inside=(ij[:,0]>=0)&(ij[:,0]<W)&(ij[:,1]>=0)&(ij[:,1]<H)
        x=ij[:,0].clip(0,W-1);y=ij[:,1].clip(0,H-1)
        z=np.array(source_depth[y,x]);valid=inside&np.isfinite(z)&(z>0)
        z[~valid]=np.inf;assert valid.sum()>1000
        # Verify the distortion map against actual original/undistorted image intensities.
        original_image=next(p for p in originals if str(p).endswith('/'+name))
        import cv2
        source=cv2.imread(str(original_image),cv2.IMREAD_GRAYSCALE)
        mapped=cv2.remap(source,(distorted[:,0]-.5).reshape(h,w).astype('float32'),
            (distorted[:,1]-.5).reshape(h,w).astype('float32'),cv2.INTER_LINEAR)
        expected=np.array(im.convert('L'));mask=inside.reshape(h,w)
        delta=abs(mapped.astype(float)-expected.astype(float))[mask]/255.
        mae=float(delta.mean());assert mae<.05,(name,mae)
        target=out/'eth3d-forest-rig'/f'{Path(name).parent.name}_{Path(name).stem}.npz'
        K=np.array([[fx,0,cx-.5],[0,fy,cy-.5],[0,0,1.]])
        np.savez_compressed(target,depth_m=z.reshape(h,w),valid=valid.reshape(h,w),intrinsics=K,
            dataset_extrinsics=np.array(entry['e']),native_distorted_xy=distorted.reshape(h,w,2))
        frames.append(dict(name=name,image=record(image),original_image=record(original_image),gt_source=record(gt),
            prepared=record(target),width=w,height=h,color_mode=im.mode,
            valid_pixels=int(valid.sum()),valid_fraction=float(valid.mean()),
            depth_range_m=[float(z[valid].min()),float(z[valid].max())],
            distortion_image_MAE_0_to_1=mae,camera=camera,original_camera=original_camera))
    return dict(dataset='eth3d-forest-rig',category='forest; ground-based camera rig',frames=frames,
        acquisition=record(folder/'acquisition.json'),
        selection=record(out/'eth3d-forest-rig/selection.json'),
        depth_definition='FARO laser-rendered camera-Z, nearest valid original pixel mapped to undistorted image; meters',
        limitations=['Grayscale imagery: repeating channels does not supply color information.',
            'Moving leaves, thin branches and missing laser returns require valid-mask and boundary handling.',
            'Image mapping is checked against supplied images; no Omega accuracy experiment has run.'],
        model_inference=False,GT_accuracy_evaluated=False)


def preview(samples,path):
    canvas=Image.new('RGB',(1200,660),'white');draw=ImageDraw.Draw(canvas)
    for row,sample in enumerate(samples):
        for col,frame in enumerate(sample['frames']):
            image=Image.open(ROOT/frame['image']['path']).convert('RGB');image.thumbnail((395,290))
            x,y=col*400,row*330
            draw.text((x+5,y+5),sample['dataset']+' / '+frame['name'],fill='black')
            canvas.paste(image,(x,y+30))
    canvas.save(path)


def run():
    family=ROOT/'results/outdoor_lidar_samples';date=time.strftime('%Y%m%d');sequence=1
    while (family/f'O0-{date}-{sequence:03}').exists():sequence+=1
    run_id=f'O0-{date}-{sequence:03}';out=family/run_id;out.mkdir(parents=True)
    write_json(out/'manifest.json',dict(status='running',run_id=run_id,stage='O0 acquisition and validation only'))
    try:
        samples=[kitti_sample(out),forest_sample(out)]
        preview(samples,out/'selected_samples.png')
        for source in Path(__file__).parent.glob('*.py'):shutil.copy2(source,out/source.name)
        write_json(out/'samples.json',samples)
        write_json(out/'manifest.json',dict(status='completed',run_id=run_id,
            stage='O0 acquisition and validation only',datasets=[s['dataset'] for s in samples],
            model_inference=False,GT_accuracy_evaluated=False,
            samples=record(out/'samples.json'),preview=record(out/'selected_samples.png')))
        doc=ROOT/'docs/experiments/outdoor_lidar_samples'/run_id;doc.mkdir(parents=True,exist_ok=True)
        for name in ['samples.json','manifest.json','selected_samples.png']:shutil.copy2(out/name,doc/name)
        print(json.dumps(dict(run_id=run_id,samples=[dict(dataset=s['dataset'],coverage=[f['valid_fraction'] for f in s['frames']]) for s in samples])),flush=True)
    except Exception as error:
        write_json(out/'manifest.json',dict(status='failed',error=repr(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':run()
