"""Stop only this task's obsolete processes, selected by exact stdout log paths."""
from core import *
import signal
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
    for path in FAMILY.glob(f'{dataset}-{code}-*-{seq:03d}/stages/{code}/manifest.json'):
        value=json.loads(path.read_text())
        if value['status']=='running':
            value|=dict(status='superseded',ended_at=c.stamp(),completion_criteria_met=False,reason='Add frozen minimum-fit/rank feasibility to effective assigned supports after reassignment; original candidate fit alone is insufficient. Partial checkpoints/logs retained.')
            c.json_write(path,value);doc=DOC/code/value['run_id'];shutil.copy2(path,doc/'manifest.json')
            (doc/'report.md').write_text(f'# {code} superseded\n\nI3 보류 depth의 영역 분할 유입을 발견하여 중단했다. 새 fit-only run으로 대체한다. 부분 checkpoint와 원래 로그는 보존한다.\n\n`{path.parent.relative_to(ROOT)}`\n')
c.json_write(FAMILY/f'superseded_process_audit_{time.time_ns()}.json',dict(time=c.stamp(),targets=targets,reason='correct effective fit-support feasibility; no source/input data removed'))
print(json.dumps(targets,indent=2))
