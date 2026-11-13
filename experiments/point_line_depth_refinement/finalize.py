"""Publish stage index and track source provenance without changing frozen results."""
import run as g
from pathlib import Path
import json,shutil
root=g.ROOT/'docs/experiments/point_line_depth_refinement';summary=root/'summary.md'
rows=json.loads((g.latest('G5a')/'evaluation/metrics.json').read_text());base=rows['arms'][0]['geometry_before']['validation']
text='\n## G5a 추가 실내 구간 결과\n\n기준은 새 구간에 C3a 방법으로 보정한 미융합 점군이다. 기존 30/40/50의 C3a와 직접 거리 비교하지 않는다.\n\n| 군 | 3D median 변화 | Z median 변화 |\n| --- | --- | --- |\n'
for r in rows['arms']:
 v=r['geometry_proposed']['validation'];g3=(base['relative_3d']['median']-v['relative_3d']['median'])/base['relative_3d']['median'];gz=(base['relative_z']['median']-v['relative_z']['median'])/base['relative_z']['median'];text+=f"| {r['name']} | {g3:+.2%} | {gz:+.2%} |\n"
text+='\n양수는 오차 감소다. 이 구간에서는 선·깊이 배율 결합의 수치 개선이 관찰됐다. 그러나 선 구조 2개뿐이고 보류 선·쌍별 지원과 coverage 조건을 별도로 확인해야 하므로, 기하 정확도나 일반적인 개선을 확정하지 않는다. 벽이 보이지 않는 책상 장면이다.\n'
summary.write_text(summary.read_text()+text)
index='# 점·선·깊이 제약 실험 실행 현황\n\n2026-11-13. **G0~G6 및 G0a/G5a 실행 완료. 효과 판정은 탐색적/미확인.**\n\n[실험 계획](../../vggt_omega_point_line_depth_refinement_experiment_plan.md) · [종합 보고서](summary.md)\n\n| 코드 | 실행 | 판정·보고서 |\n| --- | --- | --- |\n'
for code in ['G0','G0a','G1','G2','G3','G4','G5','G5a','G6']:
 p=g.latest(code);manifest=json.loads((p/'manifest.json').read_text());run=p.parents[1].name;index+=f"| {code} | `{run}` | [{manifest['decision']}]({code}/{run}/report.md) |\n"
index+='\n주 입력 30/40/50과 추가 실내 100/110/120에서 총 18개 주 최적화 비교군, 20개 초기값·민감도 비교를 실행했다. 주 비교군은 RGB/출처색 PLY와 initial/proposed/selected/last를 보존했다. G4는 실제 공식 MoGe-2 추론 결과를 사용했다.\n\nPLY 빠른 비교 경로: `results/point_line_depth_refinement/ply_review/`\n\nG0a는 numerical Jacobian 검증 보조 실행이다. G5a는 사전 지정한 추가 실내 구간이다. GT·pose 공동 최적화·융합·연속 SLAM은 미평가다.\n'
(root/'index.md').write_text(index)
amend='''# G 계열 구현·검증 기록

원래 계획의 기준을 소급 변경하지 않고 실행 시 선택과 한계를 기록한다.

- G0a: production solver는 SciPy `least_squares(jac="3-point")`다. autodiff 구현으로 부르지 않는다. affine P 미분, pinhole quotient의 analytic 미분, 중앙/전방 차분 비교 및 합성 8변수 복구를 별도 확인했다.
- solver 한도: SciPy `max_nfev=200`은 residual 기준이며 내부 Jacobian 차분 호출은 별도다. `callback`의 수용 iterate와 종료값을 후보로 저장했다. 거절 trial/finite-difference query는 selected 후보가 아니다. 별도 200 iteration 중단 callback은 구현하지 않았으며 실제 nfev/njev를 기록했다.
- 선 대응: 원본 RGB를 보고 LSD 선분의 구조 대응을 annotation했다. 원본 구간 3개/추가 구간 2개 구조로 사전 지원 기준 미달이다. 자동 matcher 교체나 지원 기준 완화는 하지 않았다. 모든 선 관련 효과는 low-support 진단이다.
- G4: fit 타일의 모든 유효 픽셀로 공통 scale을 동결한 뒤, 계산용 prior residual은 고정 4pixel stride로 읽었다. validation 타일은 제외했다. MoGe-2는 metric GT가 아니다.
- G5a: 고정 100/110/120 구간의 실제 존재·rgb.txt index·RGB를 확인해 joint inference했다. 이 구간의 기준 β는 해당 구간의 점 대응으로 C3a 방법을 적용해 구했다. 이전 구간의 β를 복사하지 않았다. 벽이 보이지 않아 벽 평가는 미실시다.
- G6: 실제 wall-camera0 ROI의 B1 평면과 관측 ID를 고정했다. ROI projection은 가림·다른 표면을 포함할 수 있어 벽 전체의 GT 정합으로 해석하지 않는다.
- 이전 실험 종료 이력은 유지한다. 이번 실험은 사용자가 새로 승인한 G 계열이다. 자유 정점/RGB 최적화나 색·깊이 융합을 추가하지 않았다.
'''
(root/'amendments.md').write_text(amend)
prov=root/'provenance';prov.mkdir(exist_ok=True)
for dirname in ['external_moge2','extra_indoor_100_110_120']:
 p=g.ROOT/'results/point_line_depth_refinement'/dirname
 shutil.copy2(p/'provenance.json',prov/(dirname+'.json'))
shutil.copy2(g.latest('G4')/'artifacts/external_provenance.json',prov/'external_prior_alignment.json')
# Snapshots make upstream depth definition independently reviewable.
out=g.latest('G6')/'artifacts/external_source';out.mkdir(exist_ok=True)
for relative in ['moge/model/v2.py','moge/utils/geometry_torch.py','README.md','LICENSE']:
 p=g.ROOT/'thirdparty/MoGe'/relative
 if p.exists():target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
# Attach late metadata to a separate amendment manifest; preserve original completed manifest.
g.c.json_write(prov/'external_source_snapshot.json',{'artifacts':[g.c.record(f) for f in out.rglob('*') if f.is_file()]})
plan=g.ROOT/'docs/vggt_omega_point_line_depth_refinement_experiment_plan.md';t=plan.read_text().replace('상태: **계획 작성 완료, 실험 미착수**','상태: **G0~G6 및 G0a/G5a 실행 완료 · 효과 판정은 탐색적**',1);needle='## 1. 배경과 범위';t=t.replace(needle,'실행 결과는 [종합 보고서](experiments/point_line_depth_refinement/summary.md)와 [구현·검증 기록](experiments/point_line_depth_refinement/amendments.md)을 따른다. 아래 내용은 사전 계획이며 실제 지원 부족·기술 검증·수치 변화는 실행 보고서와 구분한다.\n\n'+needle,1);plan.write_text(t)
print('indices and provenance finalized')
