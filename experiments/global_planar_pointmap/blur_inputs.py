"""I22/I23: deterministic blur interventions; host-only Omega inference."""
from core import *
from PIL import Image,ImageDraw

PLAN=ROOT/'docs/vggt_omega_blur_causal_experiment_plan.md'
DATASETS=['eth3d-office','eth3d-pipes']
CASES=['clean','g075','g150','g300','motion9','frame1_g300']
PROTOCOL=dict(version='blur-v1',cases=CASES,gaussian_sigma={'g075':.75,'g150':1.5,'g300':3.,'frame1_g300':3.},
    motion_length=9,blur_grid='uint8 512x336 processed RGB; unchanged geometry and GT grid',seed=0,
    image_boundary='OpenCV BORDER_REFLECT_101',GT_used_for_optimization=False)

def stage(code,dataset,parents=(),extra=None):
    st=Stage(code,dataset,parents,PROTOCOL|(extra or {}));st.config.update(PROTOCOL|(extra or {}))
    c.json_write(st.path/'config_resolved.json',st.config);shutil.copy2(PLAN,st.path/'artifacts/source/blur_plan.md')
    st.log('blur_protocol_frozen',plan=c.record(PLAN));return st

def apply_blur(image,case,frame):
    if case=='clean' or (case=='frame1_g300' and frame!=1):return image.copy()
    if case=='motion9':
        kernel=np.zeros((9,9),np.float32);kernel[4]=1/9
        return c.cv2.filter2D(image,-1,kernel,borderType=c.cv2.BORDER_REFLECT_101)
    return c.cv2.GaussianBlur(image,(0,0),PROTOCOL['gaussian_sigma'][case],borderType=c.cv2.BORDER_REFLECT_101)

def quality(rgb):
    gray=c.cv2.cvtColor(rgb,c.cv2.COLOR_RGB2GRAY).astype(float)/255.
    lap=c.cv2.Laplacian(gray,c.cv2.CV_64F);gx=c.cv2.Sobel(gray,c.cv2.CV_64F,1,0);gy=c.cv2.Sobel(gray,c.cv2.CV_64F,0,1)
    return dict(laplacian_variance=float(lap.var()),contrast_std=float(gray.std()),
        normalized_laplacian=float(lap.var()/max(gray.var(),1e-12)),sobel_energy=float(np.mean(gx*gx+gy*gy)))

def prepare(dataset):
    st=stage('I22',dataset,[latest('I15',dataset),latest('I0',dataset)])
    try:
        d=load(dataset);root=st.path/'artifacts/inputs';root.mkdir();rows=[]
        with np.load(latest('I15',dataset)/'artifacts/raw/raw.npz') as z:
            assert np.array_equal(d['rgb'].astype(np.float32)/255.,z['images'][0].transpose(0,2,3,1))
        canvas=Image.new('RGB',(320*len(CASES),3*236),'white');draw=ImageDraw.Draw(canvas)
        for j,case in enumerate(CASES):
            out=root/case;out.mkdir();ims=[];records=[]
            for f,im in enumerate(d['rgb']):
                result=apply_blur(im,case,f);assert result.shape==im.shape and result.dtype==im.dtype
                if case=='clean':assert np.array_equal(result,im)
                path=out/f'frame_{f}.png';Image.fromarray(result).save(path);ims.append(result);records.append(c.record(path))
                show=Image.fromarray(result);show.thumbnail((320,210));canvas.paste(show,(j*320,f*236+25));draw.text((j*320+5,f*236+7),f'{case} / frame{f}',fill='black')
            np.savez_compressed(out/'images.npz',rgb=np.array(ims))
            rows.append(dict(case=case,quality=[quality(im) for im in ims],files=records,arrays_sha256=ahash(np.array(ims))))
        canvas.save(st.path/'artifacts/figures/blur_inputs.png');c.json_write(st.path/'evaluation/input_conditions.json',rows)
        reference={}
        for ds in ['tum-freiburg1_desk','tum-freiburg1_desk-extra']:
            ref=load(ds);reference[ds]=[quality(x) for x in ref['rgb']]
        c.json_write(st.path/'evaluation/TUM_quality_reference.json',reference)
        # Split-aware blur must not see forbidden colors.
        from photometric_planes import fill_split
        test=np.zeros((16,16,3),np.uint8);test[::2]=180;allowed=np.indices((16,16))[1]<8
        modified=test.copy();modified[~allowed]=255
        a,_=fill_split(test,allowed);b,_=fill_split(modified,allowed)
        assert all(np.array_equal(apply_blur(a,case,0),apply_blur(b,case,0)) for case in CASES)
        st.finish(dict(decision='BLUR_INPUTS_AND_PROTOCOL_FROZEN',conditions=rows,TUM_reference=reference,
            checks=dict(clean_input_bitwise_equal=True,shape_dtype_unchanged=True,split_safe_blur_control=True)),
            f'# I22 — {dataset} 블러 개입 입력\n\n같은 3장에 6개 고정 블러 조건을 적용했다. 원본/GT 좌표와 크기는 바꾸지 않았다. 장면 간 sharpness 수치는 texture·contrast에도 의존한다.\n\n![블러 입력](figures/blur_inputs.png)')
    except Exception as error:st.fail(error);raise

def infer():
    assert os.environ.get('I_HOST_GPU')=='1','Run host GPU outside sandbox'
    import torch
    sys.path.insert(0,str(ROOT/'thirdparty/vggt-omega'))
    from vggt_omega.models import VGGTOmega
    from vggt_omega.utils.pose_enc import encoding_to_camera
    assert torch.cuda.is_available();torch.manual_seed(0);np.random.seed(0)
    checkpoint=ROOT/'checkpoints/vggt_omega_1b_512.pt';model=VGGTOmega().eval()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True),strict=True);model=model.cuda()
    for dataset in DATASETS:
        parent=latest('I22',dataset);st=stage('I23',dataset,[parent,latest('I15',dataset)],dict(execution_context='host CUDA outside sandbox'))
        try:
            out=st.path/'artifacts/inference';out.mkdir();rows=[]
            for case in CASES:
                inputpath=parent/'artifacts/inputs'/case/'images.npz'
                with np.load(inputpath) as z:rgb=z['rgb']
                images=torch.from_numpy(rgb.transpose(0,3,1,2).astype(np.float32)/255.).cuda();torch.cuda.reset_peak_memory_stats();t=time.perf_counter()
                with torch.inference_mode():pred=model(images);extr,intr=encoding_to_camera(pred['pose_enc'],pred['images'].shape[-2:])
                pred.update(extrinsics=extr,intrinsics=intr);arrays={k:v.detach().float().cpu().numpy() for k,v in pred.items() if isinstance(v,torch.Tensor)}
                path=out/case;path.mkdir();np.savez_compressed(path/'raw.npz',**arrays)
                replay={}
                if case=='clean':
                    with np.load(latest('I15',dataset)/'artifacts/raw/raw.npz') as original:
                        for key in ['images','depth','depth_conf','intrinsics','extrinsics']:
                            replay[key]=dict(bitwise=np.array_equal(arrays[key],original[key]),max_absolute_difference=float(abs(arrays[key]-original[key]).max()))
                            assert np.allclose(arrays[key],original[key],rtol=1e-5,atol=1e-6),(dataset,key,replay[key])
                row=dict(case=case,seconds=time.perf_counter()-t,input=c.record(inputpath),raw=c.record(path/'raw.npz'),clean_replay=replay,
                    gpu_peak_mib=torch.cuda.max_memory_allocated()/2**20)
                rows.append(row);st.log('joint_forward_completed',case=case,seconds=row['seconds'],clean_replay=replay)
                del pred,arrays,images;torch.cuda.empty_cache()
            provenance=dict(context='host GPU outside sandbox',gpu=torch.cuda.get_device_name(),torch=torch.__version__,cuda=torch.version.cuda,
                checkpoint=c.record(checkpoint),joint_forward_calls=len(CASES),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'thirdparty/vggt-omega',text=True).strip())
            c.json_write(st.path/'evaluation/model_provenance.json',provenance)
            st.finish(dict(decision='CONTROLLED_BLUR_OMEGA_INFERRED',conditions=rows,provenance=provenance),
                f'# I23 — {dataset} 블러 조건별 Omega\n\n호스트 GPU에서 6조건×3장 joint 추론을 실행했다. clean을 기존 원본 캐시와 비교했고 depth/K/pose/confidence 입력·출력을 저장했다. GT는 사용하지 않았다.')
        except Exception as error:st.fail(error);raise

def data_with_raw(dataset,path,rgb):
    d=load(dataset)
    with np.load(path) as z:d.update(depth=z['depth'][0,...,0].astype(float),conf=z['depth_conf'][0].astype(float),k=z['intrinsics'][0].astype(float),e=z['extrinsics'][0].astype(float))
    d.update(rgb=rgb,raw_rgb=rgb.reshape(-1,3));d['centers']=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in d['e']])
    d['raw_xyz']=c.points(d,np.ones(6));d['xyz']=d['raw_xyz'];d['d0']=d['depth'].ravel();d['k_raw']=d['k'].copy();d['beta']=np.ones(6)
    d['center_points']=d['centers'][d['fid']];n,h,w=d['depth'].shape
    d['q']=np.vstack([np.c_[d['uv'][f*h*w:(f+1)*h*w],np.ones(h*w)]@np.linalg.inv(d['k'][f]).T@np.linalg.inv(d['e'][f,:,:3]).T for f in range(n)])
    assert np.max(abs(d['center_points']+d['d0'][:,None]*d['q']-d['xyz']))<1e-8
    return d

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','infer']);args=p.parse_args()
    if args.mode=='infer':infer()
    else:
        for dataset in DATASETS:prepare(dataset)
