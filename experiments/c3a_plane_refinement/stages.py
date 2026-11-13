from base import *
from geometry import fit,associate
from evaluate import arm

def candidates(data):
 parent=observation_stage();values=json.loads((parent/'artifacts/masks/candidates.json').read_text());result={}
 for method,rows in values.items():
  result[method]=[]
  for row in rows:
   ids=dict(np.load(parent/f"artifacts/masks/candidate_{row['candidate_id']:03}.npz"));entry=row|ids;fitids=entry['fit_ids'];ft=fit(data['xyz'][fitids],data['d0'][fitids],data['fid'][fitids]);entry['fit']=ft
   hid=entry['holdout_ids']
   if 'plane' in ft and len(hid):p=np.array(ft['plane']);entry['holdout_before_move']=c.stats(abs(data['xyz'][hid]@p[:3]+p[3])/data['d0'][hid])
   result[method].append(entry)
 return result

def clean(entry):return {k:v for k,v in entry.items() if k not in ['ids','fit_ids','holdout_ids']}

def run(code):
 suffix=code[-1] if code[-1].isalpha() else '';main=code[:-1] if suffix else code
 if suffix:os.environ['H_OBSERVATION_STAGE']='H2'+suffix
 parents=[observation_stage()]
 if main in ['H4','H5']:parents.append(latest('H3'+suffix))
 if main=='H5':parents.append(latest('H4'+suffix))
 st=Stage(code,parents=parents)
 try:
  data=load();t=time.perf_counter();sets=candidates(data) if main!='H5' else {};fit_time=time.perf_counter()-t;rows=[];records={}
  if main=='H3':
   for method,name in [('raw','A1_FRAME_RAWMASK'),('refined','A2_FRAME_REFINED')]:
    groups=[{'ids':e['ids'],'candidate_ids':[e['candidate_id']],'fit':e['fit']} for e in sets[method] if e['fit']['valid']];records[method]=[clean(e) for e in sets[method]];rows.append(arm(st,data,name,groups))
  if main=='H4':
   for method,name in [('raw','A3_SHARED_RAWMASK'),('refined','A4_SHARED_REFINED'),('geometry','A6_GEOMETRY_ONLY')]:
    t=time.perf_counter();groups,assoc=associate(data,sets[method]);assoc['association_seconds']=time.perf_counter()-t;records[method]={'candidates':[clean(e) for e in sets[method]],'association':assoc};dest=st.path/f'artifacts/associations/{method}';dest.mkdir(parents=True)
    c.json_write(dest/'groups.json',[{k:v for k,v in g.items() if k!='ids'} for g in groups]);np.savez_compressed(dest/'group_observations.npz',**{f'group_{i}':g['ids'] for i,g in enumerate(groups)});rows.append(arm(st,data,name,groups))
  if main=='H5':
   parent=latest('H4'+suffix)/'artifacts/associations/refined';grows=json.loads((parent/'groups.json').read_text());obs=np.load(parent/'group_observations.npz');groups=[r|{'ids':obs[f'group_{i}']} for i,r in enumerate(grows)];records={'frozen_H4_A4_groups':c.record(parent/'groups.json'),'frozen_H4_A4_observations':c.record(parent/'group_observations.npz')};row=arm(st,data,'A5_SHARED_SOFT',groups,soft=True)
   with np.load(latest('H4'+suffix)/'artifacts/arms/A4_SHARED_REFINED/proposed/pointmap.npz') as hard, np.load(st.path/'artifacts/arms/A5_SHARED_SOFT/proposed/pointmap.npz') as soft:
    assert np.array_equal(hard['accepted'],soft['accepted']) and np.array_equal(hard['shared_plane_id'],soft['shared_plane_id']);assert np.array_equal(hard['target_depth'],soft['target_depth'])
   row['hard_gate_and_planes_identical_to_A4']=True;rows.append(row)
  c.json_write(st.path/'evaluation/plane_fits_associations.json',records)
  report=f'# {code} 평면 재투영 결과\n\nC3a K/pose/RGB/ID/점 수를 고정하고 자기 픽셀 광선의 Z-depth만 이동했다. H3/H4 적합기는 동일하며, 모든 support·gate는 A0에서 판단했다.\n\n'
  report+='| 군 | 유효 평면 | 공유 평면 | 수용점 | 보존 조건 | retained |\n| --- | --- | --- | --- | --- | --- |\n'
  for r in rows:report+=f"| {r['name']} | {r['valid_planes']} | {r['shared_planes']} | {r['accepted_points']} | {r['preservation_passed']} | {r['retained_state']} |\n"
  report+='\n자동 마스크의 중복은 모호한 관측으로 제외했으며, 보정에 쓰일 지지가 줄 수 있다. 부족한 군도 A0와 같은 NPZ/PLY·투영을 실제로 저장했다. 실패를 보정 성공으로 세지 않는다. 원시 SAM에 책상 일부가 포함된 사례도 원본 그대로 보존했다. 평면 적합 후 잔차 감소는 기하 정확도 증명이 아니다. 최종 평면·프레임별 지지·양방향 연결 근거·거절 사유·holdout의 보정 전 잔차는 JSON에 있다.\n\n'
  if main=='H5':report+='H5는 A4의 실제 공유 평면·관측·hard 목표·gate를 그대로 재사용했고 배열 일치 검증을 통과했다. 새 관측을 soft에서 다시 수용하지 않았다.\n'
  st.finish({'decision':'COMPLETED_DIAGNOSTIC_ONLY','arms':rows,'fitting_seconds':fit_time,'plane_records':records,'all_immutable_checks_passed':all(r['invariants']['all_invariants_passed'] for r in rows)},report)
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run(sys.argv[1])
