"""I13: evaluate completed I12 outputs with frozen I11 GT alignment/masks."""
from core import *
from evaluate_gt import camera_z, depth_metrics, point_metrics, GT_STATUS
from PIL import Image, ImageDraw

ARMS=['initial','plane_fixed','plane_distance','plane_distance_normal','retained']
PLAN=ROOT/'docs/vggt_omega_plane_photometric_experiment_plan.md'

def error_figure(st,d,gt,valid,pred,scale):
    n,h,w=d['depth'].shape;arms=['initial','plane_fixed','plane_distance_normal']
    canvas=Image.new('RGB',((len(arms)+1)*w,n*(h+30)),'white');draw=ImageDraw.Draw(canvas)
    for f in range(n):
        sl=slice(f*h*w,(f+1)*h*w);y=f*(h+30)
        canvas.paste(Image.fromarray(d['rgb'][f]),(0,y+30));draw.text((5,y+8),f"RGB index {d['frames'][f]['index']}",fill='black')
        for j,arm in enumerate(arms,1):
            error=(scale*pred[arm][sl]-gt[sl]).reshape(h,w);t=np.clip(error/.10,-1,1)
            color=np.full((h,w,3),255.);color[:,:,0]-=255*np.maximum(-t,0);color[:,:,2]-=255*np.maximum(t,0);color[:,:,1]-=255*abs(t)
            color[~valid[sl].reshape(h,w)]=[70,70,70]
            canvas.paste(Image.fromarray(color.astype('uint8')),(j*w,y+30));draw.text((j*w+5,y+8),arm+' | blue -10cm / red +10cm',fill='black')
    canvas.save(st.path/'artifacts/figures/gt_depth_error.png')

def run(dataset):
    parent=latest('I12',dataset);gtparent=latest('I11',dataset)
    st=Stage('I13',dataset,[parent,gtparent],dict(gt_status=GT_STATUS,evaluation_annotation='Frozen I11 registered sensor depth/mocap; no GT optimization',
        protocol='I13.1; common I11 baseline alignment/masks; >=1% MAE gain and nonincreasing RMSE vs both initial and plane_fixed'))
    try:
        shutil.copy2(PLAN,st.path/'artifacts/source/photometric_plan.md')
        st.config.update(gt_status=GT_STATUS,evaluation_annotation='Frozen I11 registered sensor depth/mocap; no GT optimization')
        c.json_write(st.path/'config_resolved.json',st.config)
        source_metrics=json.loads((parent/'evaluation/metrics.json').read_text());assert source_metrics['GT_read_during_optimization'] is False
        assert json.loads((parent/'manifest.json').read_text())['status']=='completed'
        # No model fitting, retuning, re-alignment or outcome-based masking below this line.
        gtfile=gtparent/'artifacts/gt/evaluation_arrays.npz';old=json.loads((gtparent/'evaluation/metrics.json').read_text());align=old['alignment']
        with np.load(gtfile) as z:gt=z['depth_gt'];world=z['world_gt'];test=z['test_mask'];stable=z['smooth_mask'];valid=z['valid']
        with np.load(parent/'artifacts/photometric/support.npz') as z:optimized=z['optimized_mask']
        d=load(dataset,True);N=len(d['ids']);states={};inputs=[c.record(p) for p in [parent/'manifest.json',gtparent/'manifest.json',gtfile,PLAN]]
        for arm in ARMS:
            path=parent/'artifacts/photometric'/arm/'pointmap.npz';inputs.append(c.record(path))
            with np.load(path) as z:states[arm]={k:z[k] for k in z.files}
            for key,v in [('rgb',d['raw_rgb']),('observation_id',d['ids']),('frame_id',d['fid']),('pixel_uv',d['uv']),('intrinsics',d['k']),('extrinsics',d['e'])]:
                assert np.array_equal(states[arm][key],v),(arm,key)
        assert np.array_equal(states['initial']['xyz'],d['xyz'])
        source_i10=latest('I10',dataset)
        with np.load(source_i10/'artifacts/named_or/named_OR/pointmap.npz') as z:assert np.array_equal(states['plane_fixed']['xyz'],z['xyz'])
        pp=json.loads((source_i10/'artifacts/named_or/named_OR/planes.json').read_text())['planes'];labels=states['plane_fixed']['plane_id']
        subsets={'all':np.ones(N,bool),'projected':labels>=0,'optimized':optimized,'unknown_untouched':labels<0}
        for tag in ['wall','table','screen']:subsets[tag]=np.isin(labels,[p['plane_id'] for p in pp if p['semantic_tag']==tag])&(labels>=0)
        depth={a:camera_z(z['xyz'],d['e'],d['fid']) for a,z in states.items()}
        scale=align['depth_scale'];sr=align['sim3_scale'];rot=np.array(align['sim3_rotation']);tr=np.array(align['sim3_translation']);metrics={}
        for arm,z in states.items():
            metrics[arm]={};wx=sr*z['xyz']@rot.T+tr
            for name,mask in subsets.items():
                take=test&mask;metrics[arm][name]=dict(depth=depth_metrics(scale*depth[arm],gt,take),
                    depth_smooth=depth_metrics(scale*depth[arm],gt,take&stable),world_point=point_metrics(wx,world,take))
            metrics[arm]['per_frame']=[depth_metrics(scale*depth[arm],gt,test&(d['fid']==i)) for i in range(3)]
        for arm in ['initial','plane_fixed']:
            oldarm='initial' if arm=='initial' else 'named_OR'
            assert metrics[arm]['all']['depth']==old['metrics'][oldarm]['all']['depth']
        check=dict(metadata_preserved=True,I11_baseline_metrics_replayed_exactly=True,GT_alignment_masks_frozen=True,
            unknown_untouched=all(np.array_equal(z['xyz'][labels<0],d['xyz'][labels<0]) for z in states.values()),
            unsupported_planes_unchanged=all(np.array_equal(states[a]['xyz'][(labels>=0)&~optimized],states['plane_fixed']['xyz'][(labels>=0)&~optimized]) for a in ['plane_distance','plane_distance_normal']))
        assert all(check.values()),check
        primary='plane_distance_normal';p=metrics[primary]['all']['depth'];comparisons={}
        for arm in ['initial','plane_fixed']:
            b=metrics[arm]['all']['depth'];comparisons[arm]=dict(mae_relative_gain=1-p['mae_m']/b['mae_m'],rmse_change_m=p['rmse_m']-b['rmse_m'])
        support=int((test&optimized).sum());gtpass=all(x['mae_relative_gain']>=.01 and x['rmse_change_m']<=0 for x in comparisons.values())
        decision='INSUFFICIENT_SUPPORT' if support<500 else ('GT_IMPROVED' if gtpass and source_metrics['primary_passes_rgb_visibility'] else 'NO_CONFIRMED_GAIN')
        result=dict(decision=decision,metrics=metrics,comparisons_primary=comparisons,optimized_GT_validation_count=support,
            evaluation_count=int(test.sum()),primary_passes_rgb_visibility=source_metrics['primary_passes_rgb_visibility'],
            validation_photo=source_metrics['validation_photo'],validation_photo_relative_gain=source_metrics['validation_relative_gain'],
            retained=source_metrics['retained'],alignment=align,checks=check,inputs=inputs,source_run=parent.parents[1].name,
            optimized_plane_count=source_metrics['optimized_plane_count'],optimized_observations=source_metrics['optimized_observations'],
            gt_limitations='TUM sensor reference; same six RGB frames previously evaluated; scale-aligned, not independent scene/SLAM validation')
        c.json_write(st.path/'evaluation/alignment.json',align)
        error_figure(st,d,gt,valid,depth,scale)
        report=[f'# I13 — 평면 RGB 최적화의 GT 평가: {dataset}',f'\n**{decision}**. 기존 I11의 GT·정렬·평가 마스크를 그대로 사용했다.',
            f"\nI12 최적화 평면 {result['optimized_plane_count']}개, 소속 관측 {result['optimized_observations']:,}개, 해당 GT validation {support:,}개. 전체 GT validation {test.sum():,}개.",
            f"\n주 처치군의 보류 RGB robust 손실 감소 {result['validation_photo_relative_gain']:.4%}, RGB/가시성 선택 통과={result['primary_passes_rgb_visibility']}, retained=`{result['retained']}`. GT로 retained를 바꾸지 않았다.",
            '\n## 전체 깊이 정확도',
            '\n| 출력 | MAE (cm) ↓ | RMSE (cm) ↓ | AbsRel ↓ | 보류 RGB robust 손실 ↓ |\n|---|---:|---:|---:|---:|']
        for arm in ARMS:
            m=metrics[arm]['all']['depth'];photo=result['validation_photo'].get(arm,{}).get('normalized_robust_mean')
            report.append(f"| {arm} | {m['mae_m']*100:.5f} | {m['rmse_m']*100:.5f} | {m['abs_rel']:.7f} | {photo if photo is not None else '—'} |")
        report+=['\n## 영역별 plane_fixed → 거리만 → 거리·법선',
            '\n태그는 예측이며 semantic GT가 아니다. 모든 비교군에 같은 관측 집합을 사용했다.',
            '\n| 영역 | GT 픽셀 | MAE fixed (cm) | 거리 (cm) | 거리·법선 (cm) |\n|---|---:|---:|---:|---:|']
        for name in subsets:
            ms=[metrics[a][name]['depth'] for a in ['plane_fixed','plane_distance','plane_distance_normal']]
            if ms[0]['count']:report.append(f"| {name} | {ms[0]['count']:,} | {ms[0]['mae_m']*100:.5f} | {ms[1]['mae_m']*100:.5f} | {ms[2]['mae_m']*100:.5f} |")
        report+=['\n## 센서 경계 제외 및 대응 3D 보조 평가',
            '\n| 출력 | 경계 제외 MAE (cm) | 경계 제외 RMSE (cm) | 3D mean (cm) | 3D RMSE (cm) |\n|---|---:|---:|---:|---:|']
        for a in ARMS:
            m=metrics[a]['all'];s=m['depth_smooth'];w=m['world_point'];report.append(f"| {a} | {s['mae_m']*100:.5f} | {s['rmse_m']*100:.5f} | {w['mean_m']*100:.5f} | {w['rmse_m']*100:.5f} |")
        report+=['\n## 판정과 제한',
            '\n성공 기준은 주 처치군의 전체 MAE가 initial 및 plane_fixed 양쪽보다 1% 이상 줄고 RMSE가 늘지 않으며, 보류 RGB 1% 개선 및 기존 frustum 손실 0.5% 기준을 통과하는 것이다. optimized GT validation 500개 미만이면 지지 부족으로 판정한다.',
            '\n초기 두 비교군의 I11 지표를 정확히 재현했다. GT는 I12 출력을 완료한 뒤 별도 프로세스에서 읽었다. 같은 장면의 탐색 실험이므로 새 장면의 일반화·전체 SLAM·통계적 유의성을 주장하지 않는다. 대부분의 평면은 단일 source view 패치이며 타 view의 같은 태그가 같은 물리 표면을 보장하지 않는다. low-texture·가림·반사·노출·카메라 오차가 남는다.',
            '\n![전체 유효 GT 픽셀의 깊이 오차. 표는 별도 validation만 사용.](figures/gt_depth_error.png)']
        st.finish(result,'\n'.join(report),gt_status=GT_STATUS);return st
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['tum-freiburg1_desk','tum-freiburg1_desk-extra','all'],default='all');a=p.parse_args()
    for ds in (['tum-freiburg1_desk','tum-freiburg1_desk-extra'] if a.dataset=='all' else [a.dataset]):run(ds)
