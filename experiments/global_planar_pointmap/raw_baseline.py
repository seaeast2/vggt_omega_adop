"""I21: append uncorrected Omega depth/K/pose backprojection to frozen outputs.

Depth scale is fitted once on RAW FIT pixels; primary 3D gauge uses cameras only.
Raw/FoV surface-anchor alignments remain as separate sensitivity checks.
No model inference, reconstruction change, per-arm alignment, or GT retuning.
"""
from core import *
from evaluate_gt import camera_z, depth_metrics, point_metrics, fit_sim3, GT_STATUS
from PIL import Image, ImageDraw

DATASETS=list(ACTIVE_DATASETS)
ARMS=['omega_raw','fov','plane_fixed','plane_distance','plane_distance_normal','retained']
PROTOCOL=dict(version='I21.2',raw_definition='Unmodified cached Omega depth + decoded predicted intrinsics/extrinsics; backproject with beta=1. No world_points head exists in these caches.',
    primary_alignment='Depth: one RAW FIT median GT/Z scale. 3D: common camera-pose-only Sim(3), no surface fitting; same transform across all arms',
    sensitivity_alignment='RAW FIT and previously frozen FoV FIT Sim(3), each shared across all arms; replay old results',
    evaluation='Frozen previous valid GT and I0 validation, identical IDs for every arm; no shift in depth',
    sample_cap=30000,inference=False,optimizer_rerun=False,point_filtering=False,
    gt_status=GT_STATUS,evaluation_annotation='Post-hoc baseline extension; existing Kinect/FARO GT reused; no GT reconstruction optimization')

def proper_rotation(matrix):
    u,_,vt=np.linalg.svd(matrix);sign=np.ones(3);sign[-1]=np.linalg.det(u@vt)
    return (u*sign)@vt

def pose_alignment(centers,orientations,gt_centers,gt_orientations):
    # Orientations are camera-to-world. Fit global rotation from attitudes only,
    # then scalar and translation from camera centers. No surface enters this fit.
    r=proper_rotation(sum(q@p.T for p,q in zip(orientations,gt_orientations)))
    x=centers@r.T;xm=x.mean(0);ym=gt_centers.mean(0);a=x-xm;b=gt_centers-ym
    assert np.sum(a*a)>1e-12,'Camera translation baseline insufficient for scale'
    scale=float(np.sum(a*b)/np.sum(a*a));assert scale>0,scale
    t=ym-scale*xm;errors=np.linalg.norm(scale*x+t-gt_centers,axis=1)
    angles=[np.rad2deg(np.arccos(np.clip((np.trace((r@p).T@q)-1)/2,-1,1))) for p,q in zip(orientations,gt_orientations)]
    return dict(sim3_scale=scale,sim3_rotation=r.tolist(),sim3_translation=t.tolist(),
        camera_center_errors_m=errors.tolist(),camera_orientation_errors_degree=angles,
        method='orientation chordal rotation, positive LS center-baseline scale, mean center translation; no pointmap or surface GT fit')

def pose_controls():
    from scipy.spatial.transform import Rotation
    c0=np.array([[0.,0.,0.],[.3,.1,0.],[.1,.4,.1]])
    q=Rotation.from_rotvec([[.1,0,0],[0,.2,0],[0,0,.3]]).as_matrix();r=Rotation.from_rotvec([.2,-.3,.1]).as_matrix()
    expected=2.1*c0@r.T+np.array([.2,-.1,.5]);got=pose_alignment(c0,q,expected,np.array([r@p for p in q]))
    assert abs(got['sim3_scale']-2.1)<1e-12
    assert np.max(abs(np.array(got['sim3_rotation'])-r))<1e-12
    assert np.max(got['camera_center_errors_m'])<1e-12
    return True

def compare_metric(actual,expected):
    assert actual.keys()==expected.keys()
    for k in actual:assert np.isclose(actual[k],expected[k],rtol=1e-11,atol=1e-12),(k,actual[k],expected[k])

def figure(st,d,gt,valid,pred,scale):
    n,h,w=d['depth'].shape;arms=['omega_raw','fov','plane_distance_normal']
    canvas=Image.new('RGB',(w*4,(h+30)*n),'white');draw=ImageDraw.Draw(canvas)
    for f in range(n):
        sl=slice(f*h*w,(f+1)*h*w);y=f*(h+30)
        canvas.paste(Image.fromarray(d['rgb'][f]),(0,y+30));draw.text((5,y+8),f'RGB index {d["frames"][f]["index"]}',fill='black')
        for j,arm in enumerate(arms,1):
            err=(scale*pred[arm][sl]-gt[sl]).reshape(h,w);t=np.clip(err/.10,-1,1)
            color=np.full((h,w,3),255.);color[:,:,0]-=255*np.maximum(-t,0);color[:,:,2]-=255*np.maximum(t,0);color[:,:,1]-=255*abs(t)
            color[~valid[sl].reshape(h,w)]=[70,70,70]
            canvas.paste(Image.fromarray(color.astype('uint8')),(j*w,y+30));draw.text((j*w+5,y+8),arm+' | blue -10cm / red +10cm',fill='black')
    canvas.save(st.path/'artifacts/figures/raw_fov_optimized_GT.png')

def run(dataset):
    laser=dataset.startswith('eth3d-');oldstage=latest('I20' if laser else 'I13',dataset)
    gtstage=oldstage if laser else latest('I11',dataset);source=latest('I12',dataset)
    st=Stage('I21',dataset,[source,gtstage,latest('I2',dataset)],PROTOCOL)
    try:
        st.config.update(PROTOCOL);c.json_write(st.path/'config_resolved.json',st.config)
        c.json_write(st.path/'evaluation/protocol.json',PROTOCOL)
        st.log('protocol_frozen',protocol=c.record(st.path/'evaluation/protocol.json'))
        d=load(dataset);fov=load(dataset,True);N=len(d['ids']);assert np.array_equal(d['xyz'],d['raw_xyz'])
        rawfile=next(Path(r['path']) for r in d['inputs'] if r['path'].endswith('raw.npz'))
        with np.load(rawfile) as z:
            assert 'world_points' not in z.files
            assert np.array_equal(d['depth'],z['depth'][0,...,0])
            assert np.array_equal(d['k'],z['intrinsics'][0]) and np.array_equal(d['e'],z['extrinsics'][0])
        with np.load(latest('I2',dataset)/'artifacts/fov/pointmap.npz') as z:
            assert np.array_equal(d['xyz'],z['xyz_raw']) and np.array_equal(d['k'],z['intrinsics_raw'])
        inputs=[c.record(rawfile),c.record(source/'manifest.json'),c.record(oldstage/'manifest.json'),c.record(gtstage/'manifest.json')]
        states={'omega_raw':dict(xyz=d['xyz'],intrinsics=d['k'],extrinsics=d['e'])}
        for arm in ARMS[1:]:
            original='initial' if arm=='fov' else arm;path=source/'artifacts/photometric'/original/'pointmap.npz';inputs.append(c.record(path))
            with np.load(path) as z:states[arm]={k:z[k] for k in z.files}
            for k,v in [('rgb',d['raw_rgb']),('observation_id',d['ids']),('frame_id',d['fid']),('pixel_uv',d['uv']),('extrinsics',d['e'])]:assert np.array_equal(states[arm][k],v),(arm,k)
        assert np.array_equal(states['fov']['xyz'],fov['xyz']) and np.array_equal(states['fov']['intrinsics'],fov['k'])
        gtfile=gtstage/('artifacts/laser_GT/evaluation_arrays.npz' if laser else 'artifacts/gt/evaluation_arrays.npz')
        inputs.append(c.record(gtfile));inputs.append(c.record(split_path(dataset)/'split.npz'))
        with np.load(gtfile) as z:
            gt=z['gt' if laser else 'depth_gt'];world=z['world_gt'];valid=z['valid'];fit=z['fit_mask'];test=z['test_mask'];stable=z['smooth_mask']
        sp=split_load(dataset);assert np.array_equal(fit,sp['fit']&valid) and np.array_equal(test,sp['validation']&valid)
        assert not np.any(fit&test)
        pred={a:camera_z(z['xyz'],d['e'],d['fid']) for a,z in states.items()}
        assert np.max(abs(pred['omega_raw']-d['d0']))<1e-8
        uvmax=0.
        for f in range(3):
            take=d['fid']==f;uv,zz,inside=c.project(d['xyz'][take],d['k'][f],d['e'][f],*d['depth'].shape[1:]);uvmax=max(uvmax,float(abs(uv-d['uv'][take]).max()))
        assert uvmax<1e-5
        rawout=st.path/'artifacts/omega_raw';rawout.mkdir();label=np.full(N,-1,np.int32)
        np.savez_compressed(rawout/'pointmap.npz',xyz=d['xyz'],depth=d['depth'],confidence=d['conf'],intrinsics=d['k'],extrinsics=d['e'],
            rgb=d['raw_rgb'],observation_id=d['ids'],frame_id=d['fid'],pixel_uv=d['uv'],plane_id=label,state=np.array('omega_raw'))
        ply_write(rawout/'pixel_rgb.ply',d,d['xyz'],label,d['raw_rgb'])
        with np.load(rawout/'pointmap.npz') as z:assert np.array_equal(z['xyz'],d['xyz']) and len(z['xyz'])==N
        previous=json.loads((oldstage/'evaluation/metrics.json').read_text());oldalign=json.loads((gtstage/'evaluation/metrics.json').read_text())['alignment']
        scale=float(np.median(gt[fit]/pred['omega_raw'][fit]));ix=np.flatnonzero(fit);ix=ix[np.linspace(0,len(ix)-1,min(len(ix),PROTOCOL['sample_cap']),dtype=int)]
        ss,rot,trans=fit_sim3(d['xyz'][ix],world[ix])
        assert pose_controls()
        if laser:
            gt_e=np.array([f['dataset_extrinsics'] for f in d['frames']])
            gc=np.array([-np.linalg.solve(e[:,:3],e[:,3]) for e in gt_e]);gq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in gt_e])
        else:
            assoc=json.loads((gtstage/'evaluation/metrics.json').read_text())['associations']
            gc=np.array([a['translation'] for a in assoc]);gq=np.array([a['rotation_camera_to_world'] for a in assoc])
        pq=np.array([proper_rotation(np.linalg.inv(e[:,:3])) for e in d['e']])
        camera_align=pose_alignment(d['centers'],pq,gc,gq)
        camera_align.update(depth_scale=scale,depth_shift=0,depth_fit_mask_hash=ahash(fit),test_mask_hash=ahash(test))
        alignments={'raw_anchor':dict(depth_scale=scale,depth_shift=0,sim3_scale=ss,sim3_rotation=rot.tolist(),sim3_translation=trans.tolist(),
            fit_mask_hash=ahash(fit),test_mask_hash=ahash(test),sim3_fit_indices_hash=ahash(ix),fit_count=int(fit.sum())),
            'legacy_fov_anchor':oldalign,'camera_pose_anchor':camera_align}
        with np.load(source/'artifacts/photometric/support.npz') as z:optimized=z['optimized_mask']
        ids=states['plane_fixed']['plane_id'];subsets={'all':np.ones(N,bool),'projected':ids>=0,'optimized':optimized,'nonprojected':ids<0}
        planes=json.loads((latest('I10',dataset)/'artifacts/named_or/named_OR/planes.json').read_text())['planes']
        for tag in ['wall','table','screen']:subsets[tag]=(ids>=0)&np.isin(ids,[p['plane_id'] for p in planes if p['semantic_tag']==tag])
        metrics={}
        for name,align in alignments.items():
            metrics[name]={};r=np.array(align['sim3_rotation']);t=np.array(align['sim3_translation'])
            for arm in ARMS:
                wx=align['sim3_scale']*states[arm]['xyz']@r.T+t;metrics[name][arm]={}
                for group,mask in subsets.items():
                    take=test&mask;metrics[name][arm][group]=dict(depth=depth_metrics(align['depth_scale']*pred[arm],gt,take),
                        world_point=point_metrics(wx,world,take),depth_smooth=depth_metrics(align['depth_scale']*pred[arm],gt,take&stable))
                metrics[name][arm]['per_frame']=[depth_metrics(align['depth_scale']*pred[arm],gt,test&(d['fid']==i)) for i in range(3)]
        for arm in ARMS[1:]:
            oldarm='initial' if arm=='fov' else arm
            compare_metric(metrics['legacy_fov_anchor'][arm]['all']['depth'],previous['metrics'][oldarm]['all']['depth'])
            compare_metric(metrics['legacy_fov_anchor'][arm]['all']['world_point'],previous['metrics'][oldarm]['all']['world_point'])
        deltas={}
        for arm in ARMS[1:]:
            base=metrics['camera_pose_anchor']['omega_raw']['all'];m=metrics['camera_pose_anchor'][arm]['all']
            deltas[arm]=dict(depth_mae_change_m=m['depth']['mae_m']-base['depth']['mae_m'],depth_rmse_change_m=m['depth']['rmse_m']-base['depth']['rmse_m'],
                world_mean_change_m=m['world_point']['mean_m']-base['world_point']['mean_m'],world_rmse_change_m=m['world_point']['rmse_m']-base['world_point']['rmse_m'])
        result=dict(decision='UNCORRECTED_OMEGA_BASELINE_ADDED',metrics=metrics,alignments=alignments,deltas_vs_raw=deltas,inputs=inputs,
            protocol=PROTOCOL,GT_sensor=previous.get('GT_sensor','TUM Kinect sensor depth; mocap poses for auxiliary 3D'),
            raw_vertex_count=N,raw_xyz_hash=ahash(d['xyz']),raw_intrinsics_hash=ahash(d['k']),raw_extrinsics_hash=ahash(d['e']),
            raw_vs_fov_Z_max_abs_model_unit=float(abs(pred['omega_raw']-pred['fov']).max()),raw_self_projection_max_px=uvmax,
            checks=dict(raw_matches_I2_beta1_cache_bitwise=True,raw_head_arrays_preserved=True,no_point_filter=True,
                shared_metadata_except_intrinsics=True,no_pose_correction=True,frozen_GT_masks=True,disjoint_alignment_evaluation=True,
                legacy_metrics_replayed=True,all_existing_sources_read_only=True,camera_pose_alignment_synthetic_recovery=True),source_run=source.parents[1].name,
            previous_evaluation=oldstage.parents[1].name,previous_retained=previous['retained'])
        np.savez_compressed(st.path/'artifacts/evaluation_masks.npz',fit_mask=fit,test_mask=test,sim3_fit_indices=ix)
        c.json_write(st.path/'evaluation/alignment.json',alignments)
        figure(st,d,gt,valid,pred,scale)
        report=[f'# I21 — {dataset}: 무보정 Omega raw 기준군 추가',
            '\n기존 모델 출력과 보정 결과를 수정하지 않고 평가 비교군을 추가했다. raw는 저장된 Omega depth·intrinsics·pose를 그대로 역투영한 점군이다. 이 캐시에는 별도 world_points head가 없으며 beta=1, FoV/평면/융합/정규화/점 제거를 적용하지 않았다.',
            f"\nraw 관측 수 {N:,}, XYZ hash `{result['raw_xyz_hash']}`. I2의 원본 beta1 XYZ와 bitwise 동일하다. NPZ/PLY는 artifacts/omega_raw에 원래 모델 좌표로 저장했다.",
            '\n## 후보 점군에 의존하지 않는 공통 정렬의 GT 평가',
            '\n깊이는 raw FIT의 공통 scale, 3D는 카메라 pose만으로 구한 공통 Sim(3)를 사용한다. 회전은 카메라 자세로, scale/translation은 카메라 중심으로 계산하여 raw/FoV 어느 표면에도 맞추지 않았다. 합성 pose 복원 검증을 통과했다. 원래 validation/유효 GT 마스크를 고정했다. 평가용 변환은 저장된 raw 점군을 보정한 것이 아니다. 두 지표는 정렬이 다르므로 혼합하지 않는다.',
            '\n| 출력 | depth MAE(cm) | depth RMSE(cm) | 3D mean(cm) | 3D RMSE(cm) |\n|---|---:|---:|---:|---:|']
        for arm in ARMS:
            m=metrics['camera_pose_anchor'][arm]['all'];a=m['depth'];b=m['world_point'];report.append(f"| {arm} | {a['mae_m']*100:.5f} | {a['rmse_m']*100:.5f} | {b['mean_m']*100:.5f} | {b['rmse_m']*100:.5f} |")
        report+=['\n## raw FIT 점군 정렬의 민감도 확인',
            '\n첫 I21 실행의 raw 표면 FIT 공통 정렬도 보존했다. FoV FIT 정렬과 순위가 바뀌는 경우가 있어 어느 표면에도 맞추지 않는 camera-pose 정렬을 3D 주 표로 추가했다. 모델 출력·mask·optimizer는 변경하지 않았으며 기존 I21 실행은 보존했다.',
            '\n| 출력 | 3D mean(cm) | 3D RMSE(cm) |\n|---|---:|---:|']
        for arm in ARMS:
            m=metrics['raw_anchor'][arm]['all']['world_point'];report.append(f"| {arm} | {m['mean_m']*100:.5f} | {m['rmse_m']*100:.5f} |")
        report+=['\n## 기존 FoV FIT 공통 정렬의 민감도 확인',
            '\n이 정렬도 모든 군에 하나를 공통 적용하며 비교군별 재정렬이 아니다. 기존 평가의 비raw 지표가 재현됨을 확인했다. 기준 정렬이 어느 출력을 잘 맞추는지에 따른 차이를 숨기지 않도록 두 결과를 나눴다.',
            '\n| 출력 | depth MAE(cm) | 3D mean(cm) | 3D RMSE(cm) |\n|---|---:|---:|---:|']
        for arm in ARMS:
            m=metrics['legacy_fov_anchor'][arm]['all'];report.append(f"| {arm} | {m['depth']['mae_m']*100:.5f} | {m['world_point']['mean_m']*100:.5f} | {m['world_point']['rmse_m']*100:.5f} |")
        report+=[f"\nraw/FoV camera-Z 최대 차이는 {result['raw_vs_fov_Z_max_abs_model_unit']:.3g} model units다. FoV는 원래 깊이를 유지하고 광선 방향을 바꾸므로 Z 오차가 같아도 3D 위치 오차는 달라질 수 있다.",
            '\n원래 TUM/ETH3D 센서·왜곡 매핑·희소성·소규모 장면·FoV 지원·semantic 예측의 한계를 그대로 유지한다. GT를 본 뒤 모델·마스크·소속·RGB optimizer·retained를 바꾸지 않았다. 과거 initial이라는 이름은 이 문서에서 fov로 명확히 바꿨고 raw를 별도로 추가했다.',
            '\n![raw/FoV/최적화의 GT Z 오차](figures/raw_fov_optimized_GT.png)']
        st.finish(result,'\n'.join(report),gt_status=GT_STATUS);return st
    except Exception as error:st.fail(error);raise

def summary():
    data={};depthrows=[];worldrows=[];links=[]
    for dataset in DATASETS:
        st=latest('I21',dataset);m=json.loads((st/'evaluation/metrics.json').read_text());man=json.loads((st/'manifest.json').read_text())
        for record in man['artifacts']+m['inputs']:
            actual=c.record(Path(record['path']));assert actual['sha256']==record['sha256'],record['path']
        assert all(m['checks'].values()) and man['gt_accuracy_evaluated']
        data[dataset]=dict(run_id=st.parents[1].name,**m)
        dep=[];world=[]
        for arm in ARMS:
            x=m['metrics']['camera_pose_anchor'][arm]['all'];dep.append(f"{100*x['depth']['mae_m']:.4f}");world.append(f"{100*x['world_point']['mean_m']:.4f}")
        depthrows.append('| '+dataset+' | '+' | '.join(dep)+' |');worldrows.append('| '+dataset+' | '+' | '.join(world)+' |')
        links.append(f"- [{dataset}]({st.parents[1].name}/report.md) · [GT 오차 이미지]({st.parents[1].name}/figures/raw_fov_optimized_GT.png)")
    out=DOC/'I21';c.json_write(out/'summary.json',data)
    text='''# I21 — 무보정 Omega raw를 포함한 공정 비교

**현재 활성 데이터셋의 무보정 Omega raw 비교다.** 기존 initial은 FoV 보정 후였으므로 이 문서에서는 `fov`로 표시한다. 이후는 평면 고정, 평면 거리만 조정, 평면 거리·법선 조정, 기존 retained다. TUM은 사용자 지시에 따라 신규 실행에서 제외하며 기존 4구간 결과는 과거 기록으로 보존한다.

raw는 Omega가 예측한 depth·K·pose를 그대로 역투영한 점군이며 저장 캐시에 별도 XYZ head는 없다. FoV/평면/융합/점 필터 없이 모든 관측을 유지했다. I2에 저장된 원본 beta1 점군과 bitwise 동일함을 확인했고, 원래 모델 좌표의 raw NPZ/PLY를 새 run에 보존했다. GPU 재추론은 하지 않았다.

## camera-Z 깊이 MAE (cm)

raw FIT의 공통 scale을 모든 군에 적용하고 동일 validation/유효 GT mask로 평가했다. 낮을수록 좋다.

| 데이터 | omega_raw | fov | plane_fixed | 거리 | 거리·법선 | retained |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(depthrows)+'''

raw와 FoV는 원래 camera-Z를 유지하므로 깊이 MAE가 사실상 동일하다. 따라서 FoV 보정의 영향을 보려면 다음 3D 지표를 함께 봐야 한다.

## 대응 3D 점 mean 오차 (cm)

**카메라 pose만으로 구한 하나의 공통 Sim(3)**를 모든 비교군에 적용했다. 회전은 카메라 자세에서, scale/translation은 중심 위치에서 구하여 어떤 후보 점군이나 surface GT에도 맞추지 않았다. 이 변환은 평가용 gauge 정렬이며 raw 저장 좌표를 수정하지 않는다. 각 군의 개별 정렬을 허용하지 않았다. 카메라 baseline이 짧고 pose 오차가 있을 수 있으므로 정렬의 중심/자세 잔차도 JSON에 기록했다. 깊이 지표와 구분한다.

| 데이터 | omega_raw | fov | plane_fixed | 거리 | 거리·법선 | retained |
|---|---:|---:|---:|---:|---:|---:|
'''+ '\n'.join(worldrows)+'''

각 run에는 raw 표면 FIT 및 기존 FoV 표면 FIT 공통 정렬 표도 함께 있다. 기존 FoV 표에서 과거의 비raw 지표가 재현됨을 확인했다. 첫 I21에서 두 표면 정렬 사이에 3D 순위가 뒤집히는 경우를 확인해, 후보 표면에 의존하지 않는 camera-pose 정렬을 3D 주 표에 추가했다. 첫 실행은 보존했다. 이는 정렬 민감도 분석이며 비교군마다 재정렬한 결과가 아니다. 깊이 scale의 FIT/validation은 분리했고, pose 정렬에는 surface GT 평가 픽셀을 쓰지 않았다. 새 GT 마스크·모델 보정·optimizer 실행·GT 기반 retained 선택은 하지 않았다.

카메라 pose 기준 3D 수치는 depth shape뿐 아니라 pose scale 오차도 포함한다. 특히 TUM 주 구간은 camera baseline scale 약 1.838과 depth scale 약 1.318의 차이가 커 3D mean이 약 58–60 cm로 커진다. 표면 정렬 표의 수 cm와 직접 혼합하거나, 정렬에 따른 순위 변화만으로 보정 효과를 확정하지 않는다. 카메라 기준 정렬이 표면을 편들지 않는다는 것과 그 scale이 짧은 baseline에서 정확히 추정됐다는 것은 별개다. scale·중심·자세 잔차를 run별 alignment JSON에 함께 기록했다.

## 보고서와 출처

'''+ '\n'.join(links)+'''

[전체 정확한 수치·입력 hash·정렬·보존 검증](summary.json)

GT는 ETH3D office/pipes의 FARO 레이저-rendered depth 및 TUM 두 구간의 Kinect depth다. 기존 보정·왜곡 좌표 매핑·센서 오차·희소 GT·소규모 표본·FoV 지원 부족 등의 제한은 그대로다. 이번에는 비교군 누락을 수정한 사후 평가이며 통계적 유의성이나 전체 SLAM 일반화를 주장하지 않는다.

재현: `OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 .venvs/p2a/bin/python experiments/global_planar_pointmap/raw_baseline.py`. 기존 I12/I11/I20 캐시가 필요하다. raw 파일은 각 I21 stage의 `artifacts/omega_raw/pointmap.npz`, `pixel_rgb.ply`다. 기존 raw/FoV/평면 결과 파일은 읽기 전용으로 사용했다.
'''
    (out/'index.md').write_text(text)
    print(json.dumps({k:v['run_id'] for k,v in data.items()}))

if __name__=='__main__':
    for dataset in DATASETS:run(dataset)
    summary()
