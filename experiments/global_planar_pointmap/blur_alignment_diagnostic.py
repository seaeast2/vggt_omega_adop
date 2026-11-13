"""I25a: post-hoc TUM scale sensitivity with fixed rotation and camera centroid.

This is an evaluation diagnostic, not a reconstruction correction or a new
primary score. It does not establish why pose/depth scale estimates differ.
"""
from core import *
from blur_inputs import stage
from evaluate_gt import point_metrics,GT_STATUS

def run(dataset):
    parent=latest('I21',dataset);gtparent=latest('I11',dataset)
    st=stage('I25a',dataset,[parent,gtparent],dict(protocol='post-hoc: same XYZ, rotation and camera centroid; change scale only',gt_status=GT_STATUS,
        evaluation_annotation='TUM registered sensor depth and mocap pose; post-hoc evaluation scale diagnostic, no model correction'))
    try:
        source=json.loads((parent/'evaluation/metrics.json').read_text());pose=source['alignments']['camera_pose_anchor'];s_depth=source['alignments']['raw_anchor']['depth_scale']
        d=load(dataset);r=np.array(pose['sim3_rotation']);cp=d['centers'].mean(0)
        gtmeta=json.loads((gtparent/'evaluation/metrics.json').read_text());cg=np.array([x['translation'] for x in gtmeta['associations']]).mean(0)
        gtfile=gtparent/'artifacts/gt/evaluation_arrays.npz'
        with np.load(gtfile) as z:world=z['world_gt'];test=z['test_mask']
        methods={};inputs=[c.record(parent/'manifest.json'),c.record(gtfile)]
        for arm,name in [('omega_raw',None),('fov','initial'),('plane_fixed','plane_fixed')]:
            if name:
                path=latest('I12',dataset)/'artifacts/photometric'/name/'pointmap.npz'
                with np.load(path) as z:xyz=z['xyz']
                inputs.append(c.record(path))
            else:xyz=d['xyz']
            pose_result=point_metrics(pose['sim3_scale']*(xyz-cp)@r.T+cg,world,test)
            depth_result=point_metrics(s_depth*(xyz-cp)@r.T+cg,world,test)
            expected=source['metrics']['camera_pose_anchor'][arm]['all']['world_point']
            assert abs(pose_result['mean_m']-expected['mean_m'])<1e-11
            methods[arm]=dict(camera_baseline_scale=pose_result,depth_FIT_scale=depth_result,XYZ_hash=ahash(xyz))
        result=dict(decision='POSTHOC_SCALE_SENSITIVITY_MEASURED',metrics=methods,pose_scale=pose['sim3_scale'],depth_scale=s_depth,
            ratio=pose['sim3_scale']/s_depth,rotation=r.tolist(),fixed_predicted_camera_centroid=cp.tolist(),fixed_GT_camera_centroid=cg.tolist(),
            inputs=inputs,checks=dict(same_XYZ=True,same_rotation=True,same_camera_centroids=True,old_pose_metric_replayed=True,no_model_correction=True),
            interpretation='Only quantifies error sensitivity to scale choice; does not prove blur caused scale inconsistency or validate depth-scale alignment as a primary score.')
        report=[f'# I25a — {dataset} 정렬 scale 사후 진단',
            '\n이 진단은 블러 결과 확인 후 추가한 보조 분석이다. 모델 XYZ, 평가 mask, 전역 회전, 카메라 중심의 anchor를 고정하고 두 scale만 비교한다. 원래 지표/출력은 바꾸지 않는다.',
            f"\n카메라 baseline scale={pose['sim3_scale']:.10f}, depth FIT scale={s_depth:.10f}, 비율={result['ratio']:.6f}.",
            '\n| 출력 | pose-scale 3D mean(cm) | depth-scale 3D mean(cm) |\n|---|---:|---:|']
        for a,m in methods.items():report.append(f"| {a} | {100*m['camera_baseline_scale']['mean_m']:.5f} | {100*m['depth_FIT_scale']['mean_m']:.5f} |")
        report+=['\nscale은 고정된 카메라 centroid 주위에서만 바꿨고 회전/translation을 표면에 재최적화하지 않았다. 큰 3D 오차 중 정렬 scale 선택에 민감한 부분을 보여준다. pose/depth scale 추정이 왜 달랐는지, 실제 blur가 원인인지는 이 진단만으로 확정할 수 없다. depth FIT scale에는 이미 평가용 surface GT가 쓰이므로 이를 새로운 우수 성능 결과로 선택하지 않는다.']
        st.finish(result,'\n'.join(report),gt_status=GT_STATUS)
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    for ds in ['tum-freiburg1_desk','tum-freiburg1_desk-extra']:run(ds)
