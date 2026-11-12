"""Original VGGT-1B, one joint three-image forward, raw PLY export on host GPU."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/camera_fov_alignment'))
import common as io
sys.path.insert(0,str(ROOT/'thirdparty/vggt'))


def main():
    code='V0';dataset='tum-freiburg1_desk'
    date=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d');seq=1
    base=ROOT/'results/vggt_baseline'
    while (base/f'{dataset}-{code}-{date}-{seq:03}').exists():seq+=1
    run_id=f'{dataset}-{code}-{date}-{seq:03}'
    stage=base/run_id/'stages'/code;stage.mkdir(parents=True,exist_ok=False)
    docs=ROOT/'docs/experiments/vggt_baseline'/code/run_id;docs.mkdir(parents=True,exist_ok=False)
    for name in ['artifacts/source','artifacts/inputs','artifacts/inference','artifacts/maps',
                 'artifacts/projections','artifacts/figures','evaluation','logs']:
        (stage/name).mkdir(parents=True)
    started=time.perf_counter()
    manifest={'status':'running','experiment_code':code,'run_id':run_id,'started_at':io.stamp(),
        'project_commit_at_start':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'execution_context':'host GPU outside sandbox','model':'original facebook/VGGT-1B'}
    io.json_write(stage/'manifest.json',manifest)
    def log(event,**data):
        message=json.dumps({'time':io.stamp(),'event':event}|data,ensure_ascii=False)
        print(message,flush=True)
        with (stage/'logs/run.log').open('a') as stream:stream.write(message+'\n')
    try:
        import torch
        import torchvision
        from PIL import Image
        from vggt.models.vggt import VGGT
        from vggt.utils.load_fn import load_and_preprocess_images
        from vggt.utils.pose_enc import pose_encoding_to_extri_intri
        from vggt.utils.geometry import unproject_depth_map_to_point_map
        assert torch.cuda.is_available(),'Host CUDA unavailable'
        torch.manual_seed(0);np.random.seed(0)
        source=ROOT/'thirdparty/vggt'
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
        assert source_commit=='a288dd0f14786c93483e45524328726ab7b1b4ce'
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=source,text=True).strip()
        checkpoint_info=json.loads((ROOT/'checkpoints/vggt_1b/provenance.json').read_text())
        assert checkpoint_info['repository']=='facebook/VGGT-1B'
        assert checkpoint_info['revision']=='860abec7937da0a4c03c41d3c269c366e82abdf9'
        assert checkpoint_info['sha256']=='d15bf50a8615c8225ed48b51ea5cac673d82442ec0309036df555a053253afe0'
        checkpoint=ROOT/checkpoint_info['path']
        assert io.record(checkpoint)['sha256']==checkpoint_info['sha256']
        e0=ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E0-20261112-001/stages/E0'
        frames=json.loads((e0/'artifacts/baseline/frames.json').read_text())
        assert [r['index'] for r in frames]==[30,40,50]
        for row in frames:
            src=ROOT/row['path'];assert io.record(src)['sha256']==row['sha256']
            target=stage/'artifacts/inputs'/src.name;shutil.copy2(src,target)
            assert io.record(target)['sha256']==row['sha256']
            row['baseline_source_path']=row['path'];row['run_input_path']=str(target.relative_to(ROOT))
        io.json_write(stage/'artifacts/inputs/frames.json',frames)
        for path in (ROOT/'experiments/vggt_baseline/V0').iterdir():
            if path.is_file():shutil.copy2(path,stage/'artifacts/source'/path.name)
        shutil.copy2(ROOT/'experiments/camera_fov_alignment/common.py',stage/'artifacts/source/io_helpers.py')
        for relative in ['vggt/models/vggt.py','vggt/models/aggregator.py','vggt/utils/load_fn.py',
                         'vggt/utils/pose_enc.py','vggt/utils/geometry.py','README.md','LICENSE.txt']:
            target=stage/'artifacts/source/upstream'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/relative,target)
        dtype=torch.bfloat16 if torch.cuda.get_device_capability()[0]>=8 else torch.float16
        config={'experiment_code':code,'run_id':run_id,'dataset':dataset,'frame_order':[30,40,50],
            'frame_count':3,'joint_forward_calls':1,'checkpoint':checkpoint_info,
            'official_source_commit':source_commit,'preprocessing':'official load_and_preprocess_images(mode=crop)',
            'model_parameters_dtype':'float32','outer_autocast':str(dtype),'seed':0,
            'fusion':False,'camera_refinement':False,'vertex_refinement':False,
            'confidence_filter':False,'primary_geometry':'official depth unprojection using predicted cameras',
            'additional_geometry':'raw direct point-head output','execution_context':'host GPU outside sandbox'}
        io.json_write(stage/'config_resolved.json',config)
        env={'python':sys.version,'platform':platform.platform(),'torch':torch.__version__,
            'torchvision':torchvision.__version__,'numpy':np.__version__,
            'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
            'capability':list(torch.cuda.get_device_capability(0)),
            'execution_context':'host GPU outside sandbox',
            'nvidia_smi':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used','--format=csv,noheader'],text=True).strip()}
        io.json_write(stage/'environment.json',env)
        images=load_and_preprocess_images([str(ROOT/r['run_input_path']) for r in frames],mode='crop')
        assert tuple(images.shape)==(3,3,392,518)
        np.savez_compressed(stage/'artifacts/inputs/preprocessed_rgb.npz',images=images.numpy())
        log('input_ready',shape=list(images.shape),frame_indices=[30,40,50],source_commit=source_commit)
        model=VGGT().eval()
        loaded=torch.load(checkpoint,map_location='cpu',weights_only=True)
        result=model.load_state_dict(loaded,strict=True)
        assert not result.missing_keys and not result.unexpected_keys
        del loaded
        model=model.to('cuda');images=images.to('cuda')
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize()
        begin=time.perf_counter()
        with torch.inference_mode(),torch.autocast(device_type='cuda',dtype=dtype):
            predictions=model(images)
            extrinsic,intrinsic=pose_encoding_to_extri_intri(predictions['pose_enc'],images.shape[-2:])
        torch.cuda.synchronize();forward_seconds=time.perf_counter()-begin
        log('joint_forward_finished',seconds=forward_seconds,
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved())
        arrays={k:v.detach().float().cpu().numpy() for k,v in predictions.items() if isinstance(v,torch.Tensor)}
        arrays|={'extrinsics':extrinsic.detach().float().cpu().numpy(),
            'intrinsics':intrinsic.detach().float().cpu().numpy()}
        assert arrays['images'].shape==(1,3,3,392,518)
        assert {'depth','depth_conf','world_points','world_points_conf','pose_enc'}<=arrays.keys()
        for key,array in arrays.items():assert np.isfinite(array).all(),key
        assert (arrays['depth']>0).all()
        gpu_metrics={'forward_seconds':forward_seconds,'joint_forward_calls':1,'batch_size':1,'frames_in_batch':3,
            'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()}
        del predictions,extrinsic,intrinsic,images,model
        torch.cuda.empty_cache()
        np.savez_compressed(stage/'artifacts/inference/vggt_raw.npz',**arrays)
        with np.load(stage/'artifacts/inference/vggt_raw.npz') as saved:
            for key,value in arrays.items():assert np.array_equal(saved[key],value)
        depth=arrays['depth'][0,...,0];ks=arrays['intrinsics'][0];es=arrays['extrinsics'][0]
        official_xyz=unproject_depth_map_to_point_map(arrays['depth'][0],es,ks)
        xyz=official_xyz.reshape(-1,3)
        n,h,w=depth.shape;size=h*w;fid=np.repeat(np.arange(n,dtype=np.int16),size)
        uv=np.tile(np.indices((h,w))[::-1].reshape(2,-1).T,(n,1))
        rgb=np.rint(arrays['images'][0].transpose(0,2,3,1)*255).clip(0,255).astype(np.uint8)
        models={'depth':xyz,'pointhead':arrays['world_points'][0].reshape(-1,3)}
        for label,positions in models.items():
            assert len(positions)==3*392*518 and np.isfinite(positions).all()
            io.ply_write(stage/f'artifacts/maps/vggt_{label}_rgb.ply',positions,rgb.reshape(-1,3),fid)
            io.ply_write(stage/f'artifacts/maps/vggt_{label}_frames.ply',positions,io.PALETTE[fid],fid)
        for i in range(3):
            mask=fid==i
            io.ply_write(stage/f'artifacts/maps/frame_{i}_depth_rgb.ply',xyz[mask],rgb[i].reshape(-1,3),fid[mask])
        np.savez_compressed(stage/'artifacts/maps/observations.npz',depth_world_xyz=xyz,
            pointhead_world_xyz=models['pointhead'],frame_id=fid,pixel_uv=uv,rgb=rgb.reshape(-1,3),
            depth=depth,depth_conf=arrays['depth_conf'][0],intrinsics=ks,extrinsics=es)
        checks=[];rgb_rows=[];source_rows=[]
        for camera in range(3):
            own=xyz[camera*size:(camera+1)*size]
            projected,z,valid=io.project(own,ks[camera],es[camera],h,w)
            pixel_error=float(np.max(np.abs(projected-uv[camera*size:(camera+1)*size])))
            depth_relative=float(np.max(np.abs(z-depth[camera].ravel())/depth[camera].ravel()))
            assert valid.all() and pixel_error<1e-3 and depth_relative<1e-5
            checks.append({'camera':camera,'self_projection_max_px':pixel_error,'self_relative_z_error_max':depth_relative})
            zz,win,_=io.front(xyz,ks[camera],es[camera],h,w);hit=win>=0
            photo=np.zeros((h,w,3),np.uint8);color=photo.copy()
            photo[hit]=rgb.reshape(-1,3)[win[hit]];color[hit]=io.PALETTE[fid[win[hit]]]
            io.image_write(stage/f'artifacts/projections/camera_{camera}_rgb.png',photo)
            io.image_write(stage/f'artifacts/projections/camera_{camera}_frames.png',color)
            np.savez_compressed(stage/f'artifacts/projections/camera_{camera}_front.npz',depth=zz,winner=win,empty=~hit)
            rgb_rows.append([rgb[camera],photo,color])
            source_rows.append([color])
        io.panel(stage/'artifacts/figures/vggt_camera_views.png',rgb_rows,
            ['Input RGB 518x392','VGGT depth RGB','Frame 0/1/2 colors'])
        io.json_write(stage/'artifacts/cameras.json',[{'camera':i,'frame':frames[i],
            'intrinsics':ks[i].tolist(),'camera_from_world':es[i].tolist(),
            'center_world':(-np.linalg.solve(es[i,:,:3],es[i,:,3])).tolist()} for i in range(3)])
        metrics={'decision':'PLY_CREATED_VERIFIED','point_count_per_geometry':len(xyz),
            'frame_point_counts':[size]*3,'input_original_wh':[640,480],
            'processed_wh':[w,h],'omega_processed_wh':[512,384],
            'same_original_input_files_and_order':True,'joint_inference':gpu_metrics,
            'strict_state_dict_load':'passed','all_arrays_finite':True,'positive_depth':True,
            'ply_reload_xyz_rgb_owner_count':'passed','npz_reload':'passed',
            'self_projection_checks':checks,'fusion_performed':False,'confidence_filter_performed':False,
            'icp_or_scale_alignment_performed':False,'geometry_accuracy_evaluated':False,
            'method_comparison':'qualitative only; native grids and model coordinate systems differ',
            'elapsed_seconds':time.perf_counter()-started}
        io.json_write(stage/'evaluation/metrics.json',metrics)
        manifest|={'status':'completed','ended_at':io.stamp(),'decision':metrics['decision'],
            'checkpoint':checkpoint_info,'official_source_commit':source_commit,
            'input_frames':frames,'parent_manifest':io.record(e0/'manifest.json')}
        log('completed',point_count=len(xyz),primary_ply=str(stage/'artifacts/maps/vggt_depth_rgb.ply'))
        manifest['artifacts']=[io.record(p) for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='manifest.json']
        io.json_write(stage/'manifest.json',manifest)
        report=f'''# V0 — 일반 VGGT 실내 3장 공동 추론·PLY

실행 `{run_id}`. **PLY_CREATED_VERIFIED**. C 계열 FoV/융합 방법은 사용자 요청으로 종료했으며 이 파일은 별도 육안 비교다.

- 모델: 원본 공식 [facebook/VGGT-1B](https://huggingface.co/facebook/VGGT-1B), revision `{checkpoint_info['revision']}`.
- 체크포인트 SHA-256: `{checkpoint_info['sha256']}`. HF LFS 해시·크기 대조 통과.
- [공식 소스](https://github.com/facebookresearch/vggt/tree/{source_commit}) commit `{source_commit}`. strict state-dict load 통과.
- 기존과 동일한 원본 이미지 index 30/40/50을 같은 순서로 **동시에 3장, 배치 1개, forward 1회** 입력했다. 원본 파일 해시도 일치한다.
- 공식 crop 전처리: 원본 640×480 → **518×392**. Omega E0의 512×384와 격자가 다르며 해상도를 맞춘 모델 우열 실험은 아니다.
- 각 geometry는 프레임별 {size:,}점, 총 **{len(xyz):,}점**이다. confidence 필터·융합·FoV/정점 보정·ICP·GT 정렬은 적용하지 않았다.
- 호스트 GPU `{env['gpu']}`, autocast `{dtype}`. 공동 forward {forward_seconds:.3f}초, peak allocated {gpu_metrics['peak_allocated_bytes']/2**30:.3f} GiB.

## PLY 선택

| 파일 | 의미 |
| --- | --- |
| `vggt_depth_rgb.ply` | **주 비교 파일**. 공식 Depth+카메라 역투영, 원본 RGB |
| `vggt_depth_frames.ply` | 같은 XYZ, 프레임 0 빨강·1 초록·2 파랑 |
| `vggt_pointhead_rgb.ply` | 같은 forward에서 직접 예측한 point-head 좌표, 원본 RGB |
| `vggt_pointhead_frames.ply` | 직접 point-head 좌표, 프레임별 색 |
| `frame_0/1/2_depth_rgb.ply` | 주 점군을 프레임별로 분리한 파일 |

실제 파일 디렉터리: `{(stage/'artifacts/maps').relative_to(ROOT)}`. 큰 PLY/NPZ는 로컬 results에, 코드·보고서·그림·수치·해시는 GitHub에 보관한다.

![카메라별 원본·VGGT 역투영·프레임 색](figures/vggt_camera_views.png)

## 검증과 비교 제한

공식 모델의 카메라/Depth/point-head 배열이 finite임을 확인했다. PLY를 다시 읽어 XYZ·RGB·프레임 ID·점 수를 대조했고, NPZ 재로딩과 자기 카메라 재투영/Z-depth를 확인했다. 세 원본 영상은 `frames.json`과 입력 해시로 추적된다.

비교 기준은 기존 Omega 원본 E0의 `results/pointmap_refinement/tum-freiburg1_desk-E0-20261112-001/stages/E0/artifacts/geometry/all_observations.ply`다. 서로 다른 모델의 원점·회전·scale이 동일하다고 가정하지 않는다. 원본 좌표를 보존했으므로 뷰어에서 각각 같은 형태의 시점/배율로 살펴본다. 실제 기하 정확도나 어느 모델이 더 우수한지는 판정하지 않았다.
'''
        (docs/'report.md').write_text(report)
        for name in ['manifest.json','config_resolved.json','environment.json']:
            shutil.copy2(stage/name,docs/name)
        shutil.copytree(stage/'evaluation',docs/'evaluation')
        shutil.copytree(stage/'artifacts/figures',docs/'figures')
        shutil.copy2(stage/'logs/run.log',docs/'run.log')
        artifact_index=[io.record(p)|{'relative_path':str(p.relative_to(ROOT))}
            for p in sorted((stage/'artifacts/maps').glob('*.ply'))]
        io.json_write(docs/'ply_files.json',artifact_index)
        index_text=f'''# 일반 VGGT 육안 비교

사용자 요청으로 FoV 보정·융합 방법을 종료하고 별도 원본 VGGT 비교 파일을 생성했다. 기존 [C 계열 결과](../camera_fov_alignment/index.md)를 보존한다.

| 코드 | 입력 | 상태·보고서 |
| --- | --- | --- |
'''
        for record_path in sorted(docs.parent.glob('*/manifest.json')):
            saved=json.loads(record_path.read_text());label='PLY 생성·검증 완료' if saved['status']=='completed' else '실패·이력 보존'
            index_text+=f'| V0 `{saved["run_id"]}` | TUM freiburg1_desk 원본 index 30/40/50, 3장 공동 추론 | [{label}](V0/{saved["run_id"]}/report.md) |\n'
        index_text+=f'\n주 비교 파일은 `vggt_depth_rgb.ply`, 층 분리 관찰용은 `vggt_depth_frames.ply`다. [전체 PLY 경로·크기·해시](V0/{run_id}/ply_files.json)를 보존했다. GT 정확도·모델 우열은 판정하지 않았다.\n'
        (docs.parent.parent/'index.md').write_text(index_text)
    except Exception as error:
        manifest|={'status':'failed','ended_at':io.stamp(),'error':str(error),'traceback':traceback.format_exc()}
        io.json_write(stage/'manifest.json',manifest);shutil.copy2(stage/'manifest.json',docs/'manifest.json')
        (docs/'report.md').write_text(f'# V0 실행 실패\n\n```text\n{traceback.format_exc()}\n```\n')
        log('failed',error=str(error));raise


if __name__=='__main__':main()
