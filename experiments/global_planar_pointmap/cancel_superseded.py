"""Stop only this task's obsolete processes, selected by exact stdout log paths."""
from core import *
import signal
if '--outdoor-no-named' in sys.argv:
    dataset='eth3d-forest-rig'
    tagpath=latest('I1',dataset)/'artifacts/tags/mask_registry.json'
    tags=json.loads(tagpath.read_text())
    assert not any(row['source']=='grounded' and row['semantic_tag'] in {'wall','table','screen'} for row in tags)
    path=FAMILY/'eth3d-forest-rig-I3-20261114-001/stages/I3/manifest.json'
    value=json.loads(path.read_text());assert value['status']=='running',value['status']
    selected=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():continue
        try:
            if proc.stat().st_uid!=os.getuid() or (proc/'cwd').resolve()!=ROOT:continue
            args=(proc/'cmdline').read_bytes().decode().strip('\0').split('\0')
            if len(args)==3 and args[1:] == ['experiments/global_planar_pointmap/outdoor.py','pipeline']:
                selected.append(dict(pid=int(proc.name),argv=args))
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    assert len(selected)==1,selected
    reason='No allowed grounded semantic anchor exists in any view; named-OR output is provably unchanged. Partial unrestricted geometry candidates preserved; replace with explicitly recorded no-support branch.'
    c.json_write(FAMILY/'outdoor_no_named_stop.json',dict(time=c.stamp(),targets=selected,semantic_registry=c.record(tagpath),reason=reason))
    os.kill(selected[0]['pid'],signal.SIGTERM)
    value.update(status='superseded',ended_at=c.stamp(),completion_criteria_met=False,reason=reason)
    c.json_write(path,value);doc=DOC/'I3'/value['run_id'];shutil.copy2(path,doc/'manifest.json')
    (doc/'report.md').write_text('# I3 — no-named 지원 조건으로 중단\n\n'+reason+'\n\n기존 후보 계산·로그는 보존했다. I10의 명시적 NO_NAMED_SUPPORT branch로 이어간다.\n')
    print(json.dumps(selected));sys.exit(0)
logs={'/tmp/global_planar_I6_clean.log','/tmp/global_planar_extra_I6_clean.log','/tmp/global_planar_remaining_clean.log'}
targets=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdecimal():continue
    try:
        if proc.stat().st_uid!=os.getuid():continue
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        if 'experiments/global_planar_pointmap/' not in command or not any(x in command for x in ['solve.py','remaining.py']):continue
        stdout=os.readlink(proc/'fd/1')
        if stdout in logs:targets.append(dict(pid=int(proc.name),stdout=stdout,command=command))
    except (FileNotFoundError,PermissionError,ProcessLookupError):continue
for target in targets:os.kill(target['pid'],signal.SIGTERM)
for dataset,code,seq in [('tum-freiburg1_desk','I6',3),('tum-freiburg1_desk-extra','I6',2)]:
    for path in [FAMILY/f'{dataset}-{code}-20261113-{seq:03d}/stages/{code}/manifest.json']:
        if not path.exists():continue
        value=json.loads(path.read_text())
        if value['status']=='running':
            value|=dict(status='superseded',ended_at=c.stamp(),completion_criteria_met=False,reason='Add frozen minimum-fit/rank feasibility to effective assigned supports after reassignment; original candidate fit alone is insufficient. Partial checkpoints/logs retained.')
            c.json_write(path,value);doc=DOC/code/value['run_id'];shutil.copy2(path,doc/'manifest.json')
            (doc/'report.md').write_text(f'# {code} superseded\n\nI3 보류 depth의 영역 분할 유입을 발견하여 중단했다. 새 fit-only run으로 대체한다. 부분 checkpoint와 원래 로그는 보존한다.\n\n`{path.parent.relative_to(ROOT)}`\n')
c.json_write(FAMILY/f'superseded_process_audit_{time.time_ns()}.json',dict(time=c.stamp(),targets=targets,reason='correct effective fit-support feasibility; no source/input data removed'))
print(json.dumps(targets,indent=2))
