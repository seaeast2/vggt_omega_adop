"""ETH3D laser transfer: official archives, RGB-only triple choice, host inference.

Laser depth archives are not opened here. GT mapping/evaluation is separate.
"""
from core import *
import ctypes as ct
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

DATA=ROOT/'data/eth3d_laser'
PLAN=ROOT/'docs/vggt_omega_eth3d_laser_experiment_plan.md'
DATASETS=['eth3d-office','eth3d-pipes']

def extract_archive(path,destination,accept=lambda name:True):
    """Use existing system libarchive; no environment installation required."""
    lib=ct.CDLL('libarchive.so.13');ptr=ct.c_void_p
    specs={'archive_read_new':([],ptr),'archive_read_support_filter_all':([ptr],ct.c_int),
        'archive_read_support_format_7zip':([ptr],ct.c_int),'archive_read_open_filename':([ptr,ct.c_char_p,ct.c_size_t],ct.c_int),
        'archive_read_next_header':([ptr,ct.POINTER(ptr)],ct.c_int),'archive_entry_pathname':([ptr],ct.c_char_p),
        'archive_entry_size':([ptr],ct.c_longlong),'archive_read_data':([ptr,ptr,ct.c_size_t],ct.c_longlong),
        'archive_read_data_skip':([ptr],ct.c_int),'archive_read_free':([ptr],ct.c_int),'archive_error_string':([ptr],ct.c_char_p)}
    for name,(args,result) in specs.items():getattr(lib,name).argtypes=args;getattr(lib,name).restype=result
    ar=lib.archive_read_new();lib.archive_read_support_filter_all(ar);lib.archive_read_support_format_7zip(ar)
    assert lib.archive_read_open_filename(ar,str(path).encode(),1024*1024)==0
    entry=ptr();buffer=ct.create_string_buffer(1024*1024);written=[]
    try:
        while True:
            status=lib.archive_read_next_header(ar,ct.byref(entry))
            if status==1:break
            if status<0:raise RuntimeError(lib.archive_error_string(ar))
            name=lib.archive_entry_pathname(entry).decode();size=lib.archive_entry_size(entry)
            target=(destination/name).resolve();assert target.is_relative_to(destination.resolve())
            if not accept(name) or name.endswith('/') or size==0:
                lib.archive_read_data_skip(ar);continue
            if target.exists() and target.stat().st_size==size:
                written.append(target);lib.archive_read_data_skip(ar);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('wb') as output:
                while True:
                    count=lib.archive_read_data(ar,buffer,len(buffer))
                    if count==0:break
                    if count<0:raise RuntimeError(lib.archive_error_string(ar))
                    output.write(buffer.raw[:count])
            assert target.stat().st_size==size;written.append(target)
    finally:lib.archive_read_free(ar)
    return written

def calibration(directory):
    cameras={}
    for line in (directory/'cameras.txt').read_text().splitlines():
        if not line or line.startswith('#'):continue
        row=line.split();cameras[int(row[0])]=dict(model=row[1],width=int(row[2]),height=int(row[3]),params=list(map(float,row[4:])))
    lines=(directory/'images.txt').read_text().splitlines();images={};i=0
    while i<len(lines):
        if not lines[i].strip() or lines[i].startswith('#'):i+=1;continue
        row=lines[i].split();assert len(row)==10
        quat=np.array(list(map(float,row[1:5])));rot=Rotation.from_quat(quat[[1,2,3,0]]).as_matrix();trans=np.array(list(map(float,row[5:8])))
        points=lines[i+1].split() if i+1<len(lines) else []
        ids={int(v) for v in points[2::3] if int(v)>=0}
        images[Path(row[9]).name]=dict(image_id=int(row[0]),name=row[9],camera_id=int(row[8]),
            e=np.c_[rot,trans].tolist(),track_ids=ids)
        i+=2
    return cameras,images

def prepare(scene):
    dataset='eth3d-'+scene;st=Stage('I14',dataset,extra=dict(source='ETH3D official high-res training; FARO Focus X330',selection='max minimum pair RGB SfM covisibility; no laser GT'))
    try:
        extracted=DATA/'extracted';archives=DATA/'archives'
        st.log('extract_RGB',scene=scene)
        extract_archive(archives/f'{scene}_dslr_undistorted.7z',extracted)
        extract_archive(archives/f'{scene}_dslr_jpg.7z',extracted,lambda name:name.endswith('.txt'))
        root=extracted/scene;uc=root/'dslr_calibration_undistorted';dc=root/'dslr_calibration_jpg'
        cameras,images=calibration(uc);original_cameras,original_images=calibration(dc)
        names=sorted(images);proposals=[]
        for triple in itertools.combinations(names,3):
            ims=[images[name] for name in triple]
            if len({x['camera_id'] for x in ims})!=1:continue
            center=[-np.linalg.solve(np.array(x['e'])[:,:3],np.array(x['e'])[:,3]) for x in ims]
            if min(np.linalg.norm(a-b) for a,b in itertools.combinations(center,2))<1e-4:continue
            counts=[len(a['track_ids']&b['track_ids']) for a,b in itertools.combinations(ims,2)]
            proposals.append((min(counts),sum(counts),triple,counts))
        assert proposals,'No same-camera overlapping triple'
        score,total,triple,counts=sorted(proposals,key=lambda x:(-x[0],-x[1],x[2]))[0]
        assert score>=50,(scene,score)
        frames=[]
        for name in triple:
            entry=images[name];camera=cameras[entry['camera_id']];orig=original_images[name];origcam=original_cameras[orig['camera_id']]
            assert camera['model']=='PINHOLE' and origcam['model']=='THIN_PRISM_FISHEYE'
            assert np.max(abs(np.array(entry['e'])-np.array(orig['e'])))<1e-4
            path=root/'images'/entry['name'];image=Image.open(path)
            assert image.size==(camera['width'],camera['height']),(path,image.size,camera)
            assert image.getexif().get(274,1)==1,'Unexpected EXIF rotation'
            frames.append(dict(index=names.index(name),name=name,path=str(path),sha256=c.record(path)['sha256'],
                source_member=entry['name'],original_wh=list(image.size),camera=camera,original_camera=origcam,
                original_image=orig['name'],dataset_extrinsics=entry['e'],image_id=entry['image_id']))
        c.json_write(st.path/'artifacts/frames.json',frames)
        thumb=Image.new('RGB',(1200,300),'white');draw=ImageDraw.Draw(thumb)
        for i,f in enumerate(frames):
            image=Image.open(f['path']).convert('RGB');image.thumbnail((400,270));thumb.paste(image,(i*400,30));draw.text((i*400+5,8),f['name'],fill='black')
        thumb.save(st.path/'artifacts/figures/selected_RGB.png')
        records=[c.record(archives/f'{scene}_{suffix}.7z') for suffix in ['dslr_undistorted','dslr_jpg','dslr_depth']]
        c.json_write(st.path/'evaluation/downloads.json',[dict(**r,url='https://eth3d.ethz.ch/data/'+Path(r['path']).name) for r in records])
        st.finish(dict(decision='LASER_DATASET_RGB_TRIPLE_FROZEN',pair_shared_tracks=counts,frames=frames,
            camera_files=[c.record(p/name) for p in [uc,dc] for name in ['cameras.txt','images.txt']],archives=records,
            laser_GT_content_used=False),f'# I14 — ETH3D {scene} RGB 사전 선택\n\n공식 undistorted RGB에서 최소 pair 공유 RGB SfM track 수 최대 triple을 고정했다. pair 지원={counts}. 레이저 depth는 캐시만 했고 내용·오차를 선택에 사용하지 않았다.\n\n![선택 RGB](figures/selected_RGB.png)')
    except Exception as error:st.fail(error);raise

def infer(dataset_names):
    assert os.environ.get('I_HOST_GPU')=='1','GPU must run outside sandbox'
    import torch
    sys.path.insert(0,str(ROOT/'thirdparty/vggt-omega'))
    from vggt_omega.models import VGGTOmega
    from vggt_omega.utils.load_fn import load_and_preprocess_images
    from vggt_omega.utils.pose_enc import encoding_to_camera
    assert torch.cuda.is_available();torch.manual_seed(0)
    checkpoint=ROOT/'checkpoints/vggt_omega_1b_512.pt';model=VGGTOmega().eval()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True),strict=True);model=model.cuda()
    for dataset in dataset_names:
        parent=latest('I14',dataset);st=Stage('I15',dataset,[parent],dict(execution_context='host CUDA outside sandbox; Omega joint forward'))
        try:
            frames=json.loads((parent/'artifacts/frames.json').read_text());torch.cuda.reset_peak_memory_stats()
            images=load_and_preprocess_images([f['path'] for f in frames],mode='max_size',image_resolution=512).cuda()
            with torch.inference_mode():pred=model(images);extr,intr=encoding_to_camera(pred['pose_enc'],pred['images'].shape[-2:])
            pred.update(extrinsics=extr,intrinsics=intr);arrays={k:v.detach().float().cpu().numpy() for k,v in pred.items() if isinstance(v,torch.Tensor)}
            out=st.path/'artifacts/raw';out.mkdir();np.savez_compressed(out/'raw.npz',**arrays)
            rgb=np.rint(arrays['images'][0].transpose(0,2,3,1)*255).clip(0,255).astype('uint8')
            for i,f in enumerate(frames):
                path=out/f'processed_{i}.png';Image.fromarray(rgb[i]).save(path);f['processed_path']=str(path);f['processed_sha256']=c.record(path)['sha256']
            c.json_write(out/'frames.json',frames)
            provenance=dict(context='host GPU outside sandbox',GPU=torch.cuda.get_device_name(),torch=torch.__version__,CUDA=torch.version.cuda,
                gpu_peak_mib=torch.cuda.max_memory_allocated()/2**20,joint_forward_calls=1,image_shape=list(images.shape),
                checkpoint=c.record(checkpoint),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'thirdparty/vggt-omega',text=True).strip())
            c.json_write(st.path/'evaluation/model_provenance.json',provenance)
            st.finish(dict(decision='NEW_SCENE_OMEGA_INFERRED',provenance=provenance,raw=c.record(out/'raw.npz')),
                f'# I15 — {dataset} Omega 공동 추론\n\n호스트 CUDA에서 기존 checkpoint와 512 max_size를 사용해 3장 한 번 공동 추론했다. processed shape={list(rgb.shape)}. 레이저 GT·공식 카메라 pose를 모델 입력으로 사용하지 않았다.')
            del pred,arrays,images;torch.cuda.empty_cache()
        except Exception as error:st.fail(error);raise

def load_raw(dataset):
    stage=latest('I15',dataset);out=stage/'artifacts/raw'
    with np.load(out/'raw.npz') as z:
        d=dict(depth=z['depth'][0,...,0].astype(float),conf=z['depth_conf'][0],k=z['intrinsics'][0].astype(float),e=z['extrinsics'][0].astype(float),
            rgb=np.rint(z['images'][0].transpose(0,2,3,1)*255).clip(0,255).astype('uint8'))
    n,h,w=d['depth'].shape;frames=json.loads((out/'frames.json').read_text())
    for frame in frames:
        frame['original_path']=frame['path'];frame['original_sha256']=frame['sha256']
        frame['path']=frame['processed_path'];frame['sha256']=frame['processed_sha256']
    d.update(fid=np.repeat(np.arange(n,dtype=np.int16),h*w),uv=np.tile(np.indices((h,w))[::-1].reshape(2,-1).T,(n,1)),
        raw_rgb=d['rgb'].reshape(-1,3),dataset=dataset,frames=frames,image_paths=[Path(f['processed_path']) for f in frames],
        inputs=[c.record(out/'raw.npz'),c.record(out/'frames.json'),c.record(stage/'manifest.json')])
    return d

def freeze(dataset):
    from prepare import freeze_split
    parent=latest('I15',dataset);st=Stage('I0',dataset,[parent],dict(transfer_contract='same TUM frozen geometry/optimizer constants; new scene RGB split'))
    try:
        out=st.path/'artifacts/contract';out.mkdir();c.json_write(out/'config_resolved.json',CFG)
        result=freeze_split(load(dataset),out/dataset,st)
        st.finish(dict(decision='NEW_SCENE_RGB_FIT_HOLDOUT_FROZEN',split=result),f'# I0 — {dataset} RGB 분할\n\n기존 I0 공간 hash 및 whole-track closure·halo를 같은 규약으로 적용했다. 원본 레이저 GT는 읽지 않았다.')
    except Exception as error:st.fail(error);raise

def pipeline(dataset):
    import solve,named_or,photometric_planes
    solve.fov(dataset);solve.candidates(dataset);solve.associate(dataset);named_or.run(dataset);photometric_planes.run(dataset)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','infer','freeze','segment','pipeline']);parser.add_argument('--scene',choices=['office','pipes','all'],default='all');args=parser.parse_args()
    ds=DATASETS if args.scene=='all' else ['eth3d-'+args.scene]
    if args.mode=='prepare':
        for dataset in ds:prepare(dataset.removeprefix('eth3d-'))
    elif args.mode=='infer':infer(ds)
    elif args.mode=='segment':
        import segment;segment.run(ds)
    else:
        for dataset in ds:(freeze if args.mode=='freeze' else pipeline)(dataset)
