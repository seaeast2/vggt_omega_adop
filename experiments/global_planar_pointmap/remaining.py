"""Resume already authorized CPU stages; wait for active runs, never overwrite a run."""
from core import *
from concurrent.futures import ThreadPoolExecutor
def ensure(code,dataset):
    log=ROOT/'results/global_planar_pointmap/runner_logs'/f'{dataset}_{code}.log';log.parent.mkdir(parents=True,exist_ok=True)
    while True:
        paths=sorted(FAMILY.glob(f'{dataset}-{code}-*/stages/{code}/manifest.json'))
        if paths:
            manifest=json.loads(paths[-1].read_text())
            if manifest['status']=='running':time.sleep(5);continue
            if manifest['status']=='failed':raise RuntimeError(f'Preserved failed run: {paths[-1]}')
            fresh=True
            parents={'I7':['I6'],'I8':['I7'],'I3a':['I2'],'I4a':['I3a'],'I5a':['I4a'],'I6a':['I4a','I5a'],'I6b':['I4','I5'],'I6':['I4','I5']}
            for parent in parents.get(code,[]):
                expected=latest(parent,dataset)/'manifest.json'
                fresh&=any(p['sha256']==c.record(expected)['sha256'] for p in manifest['parents'])
            if code=='I3a':fresh&=json.loads((paths[-1].parent/'evaluation/metrics.json').read_text()).get('fit_only_partition',False)
            if manifest.get('completion_criteria_met') and fresh:return paths[-1].parent
        script='export.py' if code in ['I7','I8','I9'] else 'solve.py'
        with log.open('a') as f:
            subprocess.run([sys.executable,str(SOURCE/script),code,'--dataset',dataset],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
def window(dataset):
    ensure('I6',dataset)
    for code in ['I7','I8','I3a','I4a','I5a','I6a','I6b']:ensure(code,dataset)
    print(json.dumps(dict(event='READY_FOR_I9',dataset=dataset)),flush=True)
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(window,['tum-freiburg1_desk','tum-freiburg1_desk-extra']))
