"""Regenerate the run registry from saved manifests, preserving every attempt."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
DESCRIPTIONS={
    'C0':'역투영·solver·합성 복구 검증',
    'C0a':'최근접 검색 실패 진단·정확한 BF 방식 검증',
    'C0b':'관측 퇴화·순수 회전·평면 합성 제어',
    'C1':'실내 raw 기준선·고정 대응·split·식별 가능성',
    'C2':'공통 β 1개 보정',
    'C3':'프레임별 수평·수직 FoV 6개 보정',
    'C4':'HKairport01·AMtown01 비교',
    'C5':'색+깊이 융합·점 수 축소·표면 보존',
}


def main():
    docs=ROOT/'docs/experiments/camera_fov_alignment'
    manifests=[]
    for p in sorted(docs.glob('*/*/manifest.json')):
        m=json.loads(p.read_text());manifests.append((p,m))
    text='''# Camera FoV Alignment 실험 현황

[실험 계획서](../../vggt_omega_fov_pointmap_alignment_experiment_plan.md)를 따른다. 카메라 중심·회전·원본 Depth를 고정하고 FoV 보정 후 재역투영한 프레임 간 점 차이를 최소화한다.

C5에서는 고정된 보정값에서 원본 RGB 유사도·깊이 근접 조건으로 점 수를 줄인다. 실제 연속 SLAM 검증과 구분한다. [기존 Pointmap Refinement 이력](../pointmap_refinement/index.md)은 보존한다.

실행 완료와 과학적 효과는 각각 기록한다. 최신 상태는 아래 실제 manifest를 기준으로 한다.

| 코드 | 목적 | 실행 상태 |
| --- | --- | --- |
'''
    for code,description in DESCRIPTIONS.items():
        rows=[m for p,m in manifests if m['experiment_code']==code]
        completed=sum(m['status']=='completed' for m in rows)
        failed=sum(m['status']=='failed' for m in rows)
        status=f'완료 {completed}회 / 실패 기록 {failed}회' if rows else '미실행'
        text+=f'| {code} | {description} | {status} |\n'
    text+='\n| 실행 | 상태 | 판정·보고서 |\n| --- | --- | --- |\n'
    for p,m in manifests:
        report=(p.parent/'report.md').relative_to(docs)
        decision=m.get('decision','FAILED' if m['status']=='failed' else m['status'])
        text+=f'| `{m["run_id"]}` | {m["status"]} | [{decision}]({report}) |\n'
    text+='\n대형 NPZ/PLY와 source snapshot은 `results/camera_fov_alignment/`의 각 Run ID/Stage에 보관한다. 이 목록은 새 실행이 끝날 때 갱신한다.\n'
    (docs/'index.md').write_text(text)


if __name__=='__main__':main()
