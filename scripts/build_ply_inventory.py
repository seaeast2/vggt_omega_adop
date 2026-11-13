"""Read existing PLYs/reports; write a catalog without modifying experiments."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PURPOSE={
    'P1':'Omega 원본 Depth·카메라의 좌표계/역투영·자기 재투영이 올바른지 검증',
    'E0':'Omega 보정 전 원본 3프레임 점군을 변경 없는 비교 기준선으로 보존',
    'E0a':'E0와 같은 좌표를 프레임별 색으로 표시해 중복 층·출처별 어긋남 관찰',
    'E0b':'다음 카메라의 같은 픽셀에 투영된 점의 Z를 평균하고 이전 대표점을 치환하는 단순 융합',
    'E0c':'E0b 방식에 원본 RGB 그룹 채널 범위 30 이하 조건을 추가해 다른 색의 융합 억제',
    'E0d':'드론 원본 3장 공동 Omega 추론 및 E0c 색 조건 융합을 실내와 비교',
    'E1':'E0 단순 연결 F0의 프레임 간 깊이 불일치·층 퍼짐·잠재 중복 진단',
    'E2':'공간 거리·양방향 깊이/재투영·법선 조건의 보수적 공유점 융합 F1 검증',
    'E3':'E2 점군의 owner 시선 방향 위치를 고정 RGB 손실로 200회 최적화',
    'E3b':'E0b 단순 융합 점군을 초기값으로 고정 RGB 미분 정점 이동 200회 적용',
    'P2c':'4개 렌더러의 가림/색 합성·실제 미분 및 같은 초기점에서 10회 짧은 이동 비교',
    'E3c':'같은 compact_soft 렌더러에서 E0b 대조군과 E0c 색 조건 처치군의 RGB 위치 최적화 비교',
    'E3d':'E0c 초기값에 최소 ADOP 방식 1픽셀·깊이 제한·근사 위치 기울기 적용',
    'E3e':'드론 E0d 융합 점군에서 E3d와 같은 최소 ADOP 방식 위치 이동 시험',
    'C1':'실내 융합 전 원본 기준선·고정 영상 대응·split·FoV 식별 가능성 측정',
    'C2':'모든 카메라/양축의 공통 FoV 배율 1개 보정; 원래 지원 조건 미달 시 초기값 유지',
    'C2a':'원래 실내 sparse 대응으로 실제 공통 FoV 수치 보정; 저지원 탐색 진단',
    'C3':'카메라별 수평/수직 FoV 총 6개 보정; 원래 지원 조건 미달 시 초기값 유지',
    'C3a':'실내 저지원 6변수 FoV 제안과 coverage 거절·초기값 선택 진단',
    'C4':'드론에서 원래 SIFT 대응 및 공통 1변수/프레임별 6변수 FoV 보정 비교',
    'C4a':'원래 coverage 기준을 유지하며 초기값→6변수 제안의 고정 선분 17개 후보 비교',
    'C5':'원래 C3/C4 선택값 기준, 보정 전/후 × 원본 RGB+깊이 범위 융합 유무 비교',
    'C5b':'탐색적 C4a FoV 선택값에 같은 색·깊이 융합을 적용한 보조 비교',
    'V0':'원본 일반 VGGT에 같은 실내 3장 공동 입력; Depth 역투영과 직접 point-head PLY 육안 비교',
}
SCOPES={
    'P1':'좌표 변환 검증; 실제 깊이 정확도 개선 판정 아님',
    'E0':'원본 보존·출처 검증',
    'E0a':'색/출처 진단; XYZ 변경 없음',
    'E0b':'융합 동작·점 수 감소 검증; 최초 GT 정확도 미평가',
    'E0c':'E0b 대비 coverage 증가, 공통 GT 깊이 RMSE 증가; 전체 3D 외관 악화 판정 아님',
    'E0d':'드론 raw/융합·출처 검증; GT 기하 정확도 미평가',
    'E1':'예측 간 불일치 진단; 원본 복사',
    'E2':'융합 구현 통과, 재투영 RGB PSNR 소폭 감소; GT 기하 미평가',
    'E3':'RGB 손실/PSNR/coverage 기준; selected=initial, last 별도',
    'E3b':'RGB 손실/PSNR/coverage 기준; selected=initial, last 별도',
    'P2c':'compact_soft 미분/10회 RGB 감소 통과; 장기/실제 GT 기하 미평가',
    'E3c':'RGB 손실 감소, 고정 scale·공통 입력 시점 GT 깊이 오차/coverage 악화',
    'E3d':'현재 최소 ADOP 설정의 RGB/같은 시점 GT 깊이 기준 미달; 전체 ADOP 판정 아님',
    'E3e':'RGB/coverage 기준 미달; 드론 GT 기하 정확도 미평가',
    'C1':'영상 대응 지원 부족',
    'C2':'지원 부족으로 보정 미적용; selected=initial',
    'C2a':'저지원 진단만; 실제 FoV 변동이 있으나 정확성 확인 아님',
    'C3':'지원 부족으로 보정 미적용; selected=initial',
    'C3a':'solver 제안 수렴, coverage 거절; selected=initial',
    'C4':'공통 1변수는 장면별 상이; 6변수 selected=initial, 제안은 별도',
    'C4a':'고정 validation 내부 3D 개선, 깊이축 목표 미달; 탐색 보완',
    'C5':'점 수 감소·공통 영역 Z 변화 통과, 이전 카메라 coverage 손실로 압축 기준 미달',
    'C5b':'C4a 뒤 점 수 감소, 이전 카메라 coverage 손실로 압축 기준 미달',
    'V0':'생성·저장·재투영 검증; 모델 간 GT 정확도 우열 미평가',
}
TYPES={'float':'<f4','float32':'<f4','double':'<f8','float64':'<f8','uchar':'u1',
    'uint8':'u1','char':'i1','int8':'i1','short':'<i2','int16':'<i2','ushort':'<u2',
    'uint16':'<u2','int':'<i4','int32':'<i4','uint':'<u4','uint32':'<u4'}


def read(path):
    props=[];count=None;in_vertex=False
    with path.open('rb') as stream:
        assert stream.readline()==b'ply\n'
        assert stream.readline().strip()==b'format binary_little_endian 1.0'
        while True:
            words=stream.readline().decode().split();assert words
            if words[0]=='end_header':break
            if words[0]=='element':
                in_vertex=words[1]=='vertex'
                if in_vertex:count=int(words[2])
            if words[0]=='property' and in_vertex:
                assert words[1]!='list';props.append((words[2],TYPES[words[1]]))
        vertices=np.fromfile(stream,np.dtype(props),count=count)
        assert len(vertices)==count and not stream.read(1)
        xyz=np.column_stack([vertices[a] for a in ['x','y','z']]).astype('<f8',copy=False)
        assert np.isfinite(xyz).all()
        rgb=np.column_stack([vertices[a] for a in ['red','green','blue']]).astype(np.uint8)
        geometry=hashlib.sha256(xyz.tobytes()).hexdigest()
        color=hashlib.sha256(rgb.tobytes()).hexdigest()
        stream.seek(0);file_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    return count,geometry,color,file_hash


def classify(path,code):
    name=path.name;parts=path.parts
    if 'pointhead' in name:kind='직접 point-head 예측 좌표'
    elif code in ['E0b','E0c','E0d','E2','C5','C5b']:kind='원본 또는 융합 대표점; arm/state 참조'
    elif code in ['C2','C2a','C3','C3a','C4','C4a']:kind='Depth 재역투영; FoV 설정은 state 참조'
    else:kind='Depth 역투영 또는 그 점군의 위치 이동'
    if 'source_mix' in name:color='원본 프레임 출처의 팔레트 혼합색; 실제 RGB 아님'
    elif 'owner' in name:color='최신 owner 프레임 팔레트색; 실제 RGB 아님'
    elif '_source' in name or '_frames' in name or 'colored' in name:
        color='프레임 출처/owner 팔레트색; 실제 RGB 아님'
    elif code in ['E2','E3']:color='그룹 원본 RGB 중앙값; 학습 중 고정'
    else:color='원본/owner 관측 RGB'
    state='기준선/단일 결과'
    if 'proposed_not_selected' in parts:state='solver 제안; 최종 선택에서 제외'
    elif 'selected' in parts or 'selected' in name:state='선택한 상태; 초기값일 수도 있음'
    elif 'last' in name:state='마지막 실제 이동 상태; 선택 결과와 별개'
    elif 'initial' in parts or 'initial' in name:state='초기 상태'
    elif 'after_frame_' in name:state='순차 융합 중간 단계'
    elif '_short_' in name:state='10회 짧은 최적화 결과'
    arm=''
    if 'arms' in parts:arm=parts[parts.index('arms')+1]
    if code in ['C5','C5b']:
        state={'A':'A 원본·미융합','B':'B 원본·색+깊이 융합',
            'C':'C FoV 선택값·미융합','D':'D FoV 선택값·색+깊이 융합'}[arm]
    if code in ['E0a','E1','P1','E0']:kind='융합 전 원본 Depth 역투영; E0a는 색만 변경, E1은 복사'
    subset='전체 점군'
    if name.startswith('frame_') and name not in ['frame_colored_all.ply']:
        subset='단일 프레임/출처 부분집합'
    return kind,color,state,arm,subset


def main():
    rows=[]
    for path in sorted((ROOT/'results').rglob('*.ply')):
        relative=path.relative_to(ROOT);parts=relative.parts;i=parts.index('stages')
        series,code,run=parts[1],parts[i+1],parts[i-1]
        assert code in PURPOSE,code
        count,geometry,color,file_hash=read(path)
        kind,color_kind,state,arm,subset=classify(relative,code)
        report=Path('docs/experiments')/series/code/run/'report.md'
        assert (ROOT/report).is_file(),report
        rows.append({'series':series,'experiment_code':code,'run_id':run,
            'dataset':run.split(f'-{code}-',1)[0],'purpose':PURPOSE[code],
            'historical_verdict_scope':SCOPES[code],'arm':arm,'state':state,
            'geometry_kind':kind,'color_kind':color_kind,'subset':subset,
            'vertex_count':count,'bytes':path.stat().st_size,
            'relative_path':str(relative),'absolute_path':str(path),
            'report':str(report),'file_sha256':file_hash,'ordered_xyz_f64_sha256':geometry,
            'rgb_sha256':color})
    groups={key:f'G{i:03}' for i,key in enumerate(sorted({r['ordered_xyz_f64_sha256'] for r in rows}),1)}
    first={}
    for row in rows:
        key=row['ordered_xyz_f64_sha256'];row['same_xyz_group']=groups[key]
        row['same_xyz_as']=first.setdefault(key,row['relative_path'])
    summary={'files':len(rows),'run_stage_folders':len({(r['series'],r['run_id'],r['experiment_code']) for r in rows}),
        'experiment_codes':len({r['experiment_code'] for r in rows}),
        'ordered_xyz_exact_groups':len(groups),'counts_by_series':dict(Counter(r['series'] for r in rows)),
        'exact_group_note':'f64 정점 좌표와 순서가 완전히 같은 경우만 같은 그룹. 재정렬/부동소수점 반올림/scale 차이는 별도 그룹이며 품질 판정이 아니다.',
        'scope':'현재 저장소 results 아래 실제 존재하는 PLY. 삭제된 이력/다른 저장소/NPZ만 있는 단계는 제외.',
        'experiments_modified':False}
    output=ROOT/'docs/ply_inventory';output.mkdir(parents=True,exist_ok=True)
    with (output/'files.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (output/'files.json').write_text(json.dumps({'summary':summary,'files':rows},indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
