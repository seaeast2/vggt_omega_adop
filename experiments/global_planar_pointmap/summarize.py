"""Build Korean-facing canonical index from verified, completed local results."""
from core import *
def run():
    DOC.mkdir(parents=True,exist_ok=True);datasets=['tum-freiburg1_desk','tum-freiburg1_desk-extra'];summary={};rows=[]
    for dataset in datasets:
        stages={code:latest(code,'tum-freiburg1_desk' if code=='I0' else dataset) for code in [f'I{i}' for i in range(10)]}
        for code,path in stages.items():
            manifest=json.loads((path/'manifest.json').read_text());assert manifest['completion_criteria_met'],path
            metrics=json.loads((path/'evaluation/metrics.json').read_text());report=DOC/code/manifest['run_id']/'report.md'
            rows.append(f"| {dataset.replace('tum-freiburg1_desk','desk')} | {code} | [{manifest['run_id']}]({report.relative_to(DOC)}) | {metrics['elapsed_seconds']:.2f}s | {manifest['decision']} |")
        m7=json.loads((stages['I7']/'evaluation/metrics.json').read_text());m6=json.loads((stages['I6']/'evaluation/metrics.json').read_text())
        arms=json.loads((stages['I9']/'evaluation/arms.json').read_text());a4=next(r for r in arms if r['arm']=='A4');b1=next(r for r in arms if r['arm']=='B1s')
        summary[dataset]=dict(canonical_stages={k:c.record(v/'manifest.json') for k,v in stages.items()},
            accepted=m7['accepted'],accepted_fraction=m7['accepted']/589824,retained=m7['retained'],visibility=m7['visibility'],
            checks=m7['checks'],stability=m6['stability'],heldout_3d_pair_medians=dict(B1s=[r['relative_3d'].get('median') for r in b1['heldout']],A4=[r['relative_3d'].get('median') for r in a4['heldout']]),
            review_directory=str(FAMILY/'ply_review'/stages['I9'].parents[1].name),
            verdicts=dict(automatic_assignment='NOT_ESTABLISHED_NO_SURFACE_LABEL_GT',structure='AUTOMATIC_HYPOTHESES_ONLY',surface_cleanup='TECHNICAL_PLANARITY_AND_SEPARATE_VISUAL_REVIEW',
                visibility='PASSED' if m7['visibility']['passed'] else 'FAILED_RETAIN_INITIAL',gt_accuracy='GT_NOT_EVALUATED'))
    excluded=[]
    canonical={v['path'] for d in summary.values() for v in d['canonical_stages'].values()}
    for dataset in datasets:
        canonical.update(str(latest(code,dataset)/'manifest.json') for code in ['I3a','I4a','I5a','I6a','I6b'])
    for path in sorted(FAMILY.glob('*/stages/*/manifest.json')):
        value=json.loads(path.read_text())
        code=value['experiment_code'];older=str(path) not in canonical and code in [f'I{i}' for i in range(10)]+['I3a','I4a','I5a','I6a','I6b']
        if value['status'] in ['failed','superseded'] or (value['status']=='completed' and (not value.get('completion_criteria_met',False) or older)):
            reason=value.get('reason',value.get('error','earlier run retained as provenance; superseded by canonical result'))
            if code in ['I3','I3a'] and value['status']=='completed':
                metric=json.loads((path.parent/'evaluation/metrics.json').read_text())
                if not metric.get('fit_only_partition'):reason='KNOWN_HOLDOUT_GEOMETRY_LEAK in pre-fix region partition; excluded from canonical result'
            excluded.append(dict(path=str(path),status=value['status'],run_id=value['run_id'],reason=reason))
    c.json_write(DOC/'canonical_results.json',summary);c.json_write(DOC/'excluded_runs.json',excluded)
    audit=FAMILY/'holdout_perturbation_audit.json'
    if audit.exists():shutil.copy2(audit,DOC/'holdout_perturbation_audit.json')
    text='# I0–I9 전역 자동 평면 pointmap 실행 결과\n\n'
    text+='주 구간 30/40/50과 추가 실내 100/110/120에서 I0–I9 및 A0–A6 비교를 실행했다. 각 구간은 589,824개 원본 관측을 유지한다. '
    text+='실험 실행 완료와 알고리즘의 과학적 성공은 구분한다. GT_NOT_EVALUATED이며 실제 소속/구조 정확도·전체 SLAM 정확도의 향상을 주장하지 않는다.\n\n'
    text+='B1은 기존 C3a 실제 proposed이고 B1s는 공통 fit/보류 분리를 적용한 새 I2 proposed다. 자동 군은 B1s에서 시작한다. '
    text+='기존 C3a split 재현은 I0에서 별도 검증했다. historical fit와 새 보류의 겹침 때문에 B1을 새 독립 보류 기준으로 해석하지 않는다.\n\n'
    text+='| 구간 | 단계 | canonical run·보고서 | stage wall time | 판정 |\n| --- | --- | --- | --- | --- |\n'+'\n'.join(rows)+'\n\n'
    for dataset,s in summary.items():
        text+=f"## {dataset}\n\n확정·수용 관측 {s['accepted']:,}/589,824 ({s['accepted_fraction']:.4%}). 최대 frustum loss {s['visibility']['maximum_frustum_loss']:.4%}; retained=`{s['retained']}`.\n\n"
        text+=f"고정 보류 camera pair 01/02/12 상대 3D median: B1s `{s['heldout_3d_pair_medians']['B1s']}`, A4 `{s['heldout_3d_pair_medians']['A4']}`. 이는 동일 joint inference의 내부 정합이며 GT 오차가 아니다.\n\n"
        text+=f"PLY 검토 폴더: `{s['review_directory']}`. pixel RGB/frame/plane 색을 구분한 B0/B1/B1s/A0–A6 파일이 있다.\n\n"
    text+='## 보존·재현성과 제한\n\n'
    text+='- I1 GPU는 호스트에서 실행했고 CPU geometry와 환경 기록을 구분했다. 모델 SHA256와 source revision은 I1 보고서에 있다.\n'
    text+='- I3 보류 XYZ의 분할 유입을 고친 뒤 후보·모델 선택·소속·normal의 보류 perturbation 불변 검증을 통과했다. 초기·중단 실행은 제외 목록에 남겼다.\n'
    text+='- 소속 변경 뒤 effective fit의 최소 50개/퇴화 조건도 검사한다. 이 조건은 동결된 원래 fit 기준을 적용한 정확성 수정이며 이동 크기 gate가 아니다.\n'
    text+='- initial/proposed/retained bundle은 각각 state/hash로 연결하며 RGB/ID/UV/K/pose·비대상 XYZ를 검사한다. PLY 속성 재읽기·경계 round-trip·이전 checkpoint 복원·잘못된 registry export 거부를 검사했다.\n'
    text+='- 경계의 물리 edge/가림 분류는 provisional이다. 미관측 hole을 실제 구멍으로 확정하거나 watertight mesh를 생성하지 않았다.\n'
    text+='- semantic tag는 모델 예측이며 수동 category/plane annotation이 없다. 추가 실내는 과거 사용 구간이고 threshold를 바꾸는 데 사용하지 않았다.\n'
    text+='- 비용은 각 stage의 wall time/peak RSS이며 모델 GPU peak는 shared process 기준이다. 병렬 실행 시간은 단순 합산한 전체 경과시간과 다르다.\n\n'
    text+='[수치 원본](canonical_results.json) · [제외·중단 실행](excluded_runs.json) · [보류 유입 회귀 검증](holdout_perturbation_audit.json)\n'
    (DOC/'index.md').write_text(text)
if __name__=='__main__':run()
