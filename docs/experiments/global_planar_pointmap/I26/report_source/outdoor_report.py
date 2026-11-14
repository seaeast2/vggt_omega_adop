"""Report the completed outdoor transfer with support and alignment caveats."""
from core import *
from outdoor import DATASETS,ARMS,PLAN


def run():
    out=DOC/'I26';out.mkdir(exist_ok=True);payload={};audit={};depth=[];world=[];support=[];links=[];roi=[]
    for dataset in DATASETS:
        stage=latest('I26',dataset);result=json.loads((stage/'evaluation/metrics.json').read_text())
        payload[dataset]=result;verified=0;skipped=[]
        for code in ['I14','I15','I0','I1','I2','I3','I4','I10','I12','I26']:
            try:p=latest(code,dataset)
            except FileNotFoundError:
                assert dataset=='eth3d-forest-rig' and code in ['I3','I4']
                proof=json.loads((latest('I10',dataset)/'artifacts/named_or/no_named_proof.json').read_text())
                assert proof['allowed_grounded_anchors']==0
                skipped.append(dict(code=code,reason='A1: no permitted named anchor; exact unchanged-output branch',proof=proof))
                continue
            manifest=json.loads((p/'manifest.json').read_text())
            for record in manifest['artifacts']+manifest['parents']:
                assert c.record(record['path'])['sha256']==record['sha256'],record['path'];verified+=1
            if code!='I26':assert not manifest['gt_accuracy_evaluated']
        fov=json.loads((latest('I2',dataset)/'evaluation/metrics.json').read_text())
        named=json.loads((latest('I10',dataset)/'evaluation/metrics.json').read_text())
        opt=json.loads((latest('I12',dataset)/'evaluation/metrics.json').read_text())
        detections=json.loads((latest('I1',dataset)/'artifacts/tags/detections.json').read_text())
        planes=json.loads((latest('I12',dataset)/'evaluation/planes.json').read_text())
        support.append(dict(dataset=dataset,decision=result['decision'],fov_decision=fov['decision'],fov_rank=fov['rank'],
            fov_support=fov['support'],fov_beta=fov['beta'],raw_named_fraction=named['raw_named_fraction'],
            eligible_OR_fraction=named['eligible_OR_fraction'],projected=named['arms']['named_OR'],
            optimized_plane_count=opt['optimized_plane_count'],optimized_observations=opt['optimized_observations'],
            validation_relative_gain=opt['validation_relative_gain'] if opt['optimized_plane_count'] else None,validation_photo=opt['validation_photo'],
            plane_support=planes,detected_labels=[d['labels'] for d in detections]))
        for arm in ARMS:
            m=result['metrics'][arm];z=m['all']['depth'];f=m['focal'];pose=m['all']['world_pose'];surface=m['all']['world_raw_surface']
            depth.append(f"| {dataset} | {arm} | {z['mae_m']:.6f} | {z['rmse_m']:.6f} | {f['mean_abs_relative_percent']:.4f} |")
            posemean=f"{pose['mean_m']:.6f}" if pose else 'unavailable'
            world.append(f"| {dataset} | {arm} | {posemean} | {surface['mean_m']:.6f} |")
        projected=result['metrics']['plane_fixed']['projected']['depth'];raw_projected=result['metrics']['omega_raw']['projected']['depth']
        roi.append(f"| {dataset} | {projected['count']} | "+(f"{raw_projected['mae_m']:.6f} | {projected['mae_m']:.6f} |" if projected['count'] else 'N/A | N/A |'))
        audit[dataset]=dict(verified_artifact_records=verified,skipped_geometry_stages=skipped,GT_only_evaluation=True,raw_beta1_bitwise=result['raw_bitwise_matches_beta1'],
            unknown_bitwise=result['unknown_unchanged_bitwise'],fit_test_disjoint=True,source_run=stage.parents[1].name,
            raw_fov_Z_max=result['raw_vs_fov_Z_max'])
        links.append(f"- {dataset}: [GT 오차 그림]({stage.parents[1].name}/figures/GT_comparison.png) · [평면 소속/제외 영역](../I10/{latest('I10',dataset).parents[1].name}/figures/named_OR_mask.png) · [상세 결과]({stage.parents[1].name}/report.md)")
    c.json_write(out/'summary.json',payload);c.json_write(out/'support.json',support);c.json_write(out/'audit.json',audit)
    narrative=[]
    for item in support:
        dataset=item['dataset'];result=payload[dataset];f=result['metrics']['fov']['focal'];raw=result['metrics']['omega_raw']['focal']
        narrative.append(f"- **{dataset}: {result['decision']}**. raw→FoV focal 평균 상대 오차 {raw['mean_abs_relative_percent']:.4f}→{f['mean_abs_relative_percent']:.4f}%. "
            f"named OR 투영 {item['projected']['accepted']:,}개, RGB 최적화 평면 {item['optimized_plane_count']}개/{item['optimized_observations']:,}점, "
            f"그 영역의 보류 GT {result['optimized_test_GT_count']:,}개. FoV 상태 `{item['fov_decision']}`. "
            f"GT 유효 비율 {result['GT_valid_fraction']:.2%}.")
    text='# I26 — 도시 길거리·숲의 Omega/FoV/평면 LiDAR 평가\n\n'
    text+='두 야외 장면에서 원래의 3장을 사용해 기존 알고리즘을 전이했다. 무보정 Omega raw를 포함한 여섯 군의 출력을 생성하고 LiDAR GT로 비교했다. 지원 없는 단계는 아래에 구분했다. TUM·드론은 실행하지 않았다. [사전 규약](../../../vggt_omega_outdoor_lidar_experiment_plan.md).\n\n'
    text+='\n'.join(narrative)+'\n\n'
    text+='**FoV 효과도 장면에 따라 갈렸다.** KITTI의 focal 오차는 커졌고 숲에서는 줄었다. 두 장면 모두 평면 RGB parameter 업데이트는 지원 부족으로 0개였으므로, 거리·법선 최적화의 개선/악화를 검증한 결과로 해석하지 않는다.\n\n'
    text+='## 동일 보류 GT의 깊이·FoV\n\n단위는 미터다. 각 장면 raw FIT에서 구한 depth scale 하나를 모든 군에 공통 적용했다. KITTI와 숲은 깊이 범위와 센서가 달라 장면 간 평균을 만들지 않는다.\n\n'
    text+='| 장면 | 군 | depth MAE (m) | depth RMSE (m) | focal 평균 상대 오차 (%) |\n|---|---|---:|---:|---:|\n'+'\n'.join(depth)
    text+='\n\n**FoV는 camera-Z를 바꾸지 않으므로 raw/FoV depth 지표가 같은 것이 정상이다.** FoV의 보정 여부는 focal/K와 3D 공통 정렬 지표로 판단한다. Focal은 GT K와 직접 비교하므로 전역 scale 선택에 의존하지 않는다.\n\n'
    text+='평면 투영이 실제 적용된 영역만 보면 다음과 같다. KITTI는 243개의 보류 GT에서 국소 오차가 줄었지만, 전체 깊이 MAE 개선은 약 0.07%이며 1% 개선 기준에 미달한다. 이 국소 결과를 전체 장면의 확정 개선으로 확대하지 않는다.\n\n| 장면 | 투영 영역 보류 GT 수 | raw MAE (m) | fixed MAE (m) |\n|---|---:|---:|---:|\n'+'\n'.join(roi)+'\n\n'
    text+='## 공통 정렬에서의 3D 점 오차\n\n각 정렬을 raw/FoV/평면 전체에 공통 적용했다. 주 지표는 camera pose 기반 정렬, 보조는 raw FIT 표면 기반 정렬이다. 별도 군별 정렬은 없다. KITTI의 OXTS pose와 숲의 짧은 camera baseline 때문에 두 규약의 차이를 반드시 함께 읽어야 한다.\n\n'
    text+='| 장면 | 군 | pose 정렬 3D mean (m) | raw 표면 정렬 3D mean (m) |\n|---|---|---:|---:|\n'+'\n'.join(world)
    text+='\n\n## 범위·판정\n\n'
    text+='평면은 기존 `wall/table/screen`만 허용했다. 이름이 없거나 다른 class인 관측, unknown은 같은 표면의 다른 view에서 named 근거를 전파하지 못하면 보정하지 않는다. 나무·잎·도로를 새 평면으로 강제하지 않았다. named mask가 기하 GT인 것은 아니므로 SAM/의미 오분류 가능성은 남는다. 지원이 없어서 출력이 같은 경우는 최적화의 개선이나 실패 효과로 읽지 않는다.\n\n'
    text+='성공은 기존 기준대로 거리·법선 군이 raw와 plane_fixed 모두에 대해 MAE 1% 이상 개선, RMSE 비증가, RGB/가시성 통과를 함께 만족할 때다. 최적화 영역 보류 GT 500개 미만은 지지 부족이다. 전체·투영·최적화·unknown 영역과 프레임별 지표는 summary JSON에 있다.\n\n'
    text+='KITTI는 공식 loader의 중앙 crop(246,0,996,375)→512×256을 GT/K에 동일 적용했다. forest는 원본 camera 모델을 통해 왜곡 GT를 512×288의 각 픽셀에 직접 대응했다. 결측 GT를 보간하지 않았다. forest의 RGB 3채널은 서로 같으며 컬러 효과를 평가하지 못한다. KITTI의 차량·자전거·보행자는 자동으로 제거하지 않았으므로 전체 화면 전이 및 동적 장면 스트레스 시험이다. GT를 보고 ROI나 hyperparameter를 다시 고르지 않았다.\n\n'
    text+='이번 실행은 원본 입력 비교이며 합성 블러 6조건 반복이나 전체 시퀀스 SLAM 검증은 포함하지 않는다.\n\n'
    text+='RGB 지원 평면이 0개면 보류 RGB 개선율은 정의되지 않아 null로 보고한다. 기존 I12의 빈 집계가 수식상 1.0을 반환하더라도 100% 개선으로 해석하지 않는다.\n\n'
    text+='KITTI I26 첫 실행도 보존했다. `-002`는 지원 0개의 RGB 개선율을 null로 명시한 canonical 평가이며, 두 실행의 모든 GT 지표와 공통 정렬이 정확히 같음을 검사했다.\n\n'
    text+='숲은 모든 view에서 허용 named anchor가 0개여서 [A1 동일 출력 조기 종료](../../../vggt_omega_outdoor_lidar_amendment_A1.md)를 적용했다. 진행 중이던 I3의 부분 결과는 superseded로 보존했고, 전체 I3/I4 기하 탐색은 완료하지 않았다. 빈 plane registry의 I10/I12 출력이 FoV와 bitwise 같음을 검사했다. GT 오차를 보고 조기 종료한 것이 아니다.\n\n'
    text+='\n'.join(links)+'\n\n[정확한 지표·공통 정렬·입력](summary.json) · [FoV/평면 지원·의미 검출·RGB 손실](support.json) · [원본 보존·파일 해시 검증](audit.json)\n'
    plot=SOURCE/'outdoor_plot.py';plotpy=ROOT/'.venvs/blur-report/bin/python'
    subprocess.run([str(plotpy),str(plot),str(out/'summary.json'),str(out/'figures')],check=True,
        env=os.environ|{'MPLCONFIGDIR':'/tmp/vggt-outdoor-mpl'})
    text+='\n## 비교 그림\n\n![야외 LiDAR 비교](figures/outdoor_comparison.png)\n'
    c.json_write(out/'figure_provenance.json',dict(source=c.record(plot),data=c.record(out/'summary.json'),
        figures=[c.record(p) for p in sorted((out/'figures').glob('*'))],
        reporting_python=str(plotpy),requirements=subprocess.check_output([str(plotpy),'-m','pip','freeze'],text=True)))
    snapshot=out/'report_source';snapshot.mkdir(exist_ok=True)
    for name in ['outdoor_report.py','outdoor_plot.py']:shutil.copy2(SOURCE/name,snapshot/name)
    c.json_write(snapshot/'manifest.json',dict(files=[c.record(snapshot/name) for name in ['outdoor_report.py','outdoor_plot.py']],
        summary=c.record(out/'summary.json'),audit=c.record(out/'audit.json')))
    (out/'index.md').write_text(text)
    print(json.dumps(dict(report=str(out/'index.md'),audit=audit)))


if __name__=='__main__':run()
