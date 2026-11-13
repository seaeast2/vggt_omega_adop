"""Perturb ONLY excluded geometry/confidence and prove candidate outputs unchanged."""
from core import *
import solve
dataset='tum-freiburg1_desk';original=solve.load;reference=latest('I3',dataset)/'artifacts/regions'
def altered(name,fov=False):
    d=original(name,fov);sp=split_load(name);ii=sp['excluded'];rng=np.random.default_rng(123)
    d['xyz'][ii]+=rng.normal(0,100,d['xyz'][ii].shape)
    d['d0']=d['d0'].copy();d['d0'][ii]*=100
    d['conf']=d['conf'].copy();d['conf'].ravel()[ii]=1e8
    return d
solve.load=altered
solve.candidates(dataset,code_override='I3v')
probe=latest('I3v',dataset)/'artifacts/regions'
checks={}
for name in ['regions.json','model_selection.json','proposal_events.json','memberships.npz','normals_7.npz','normals_21.npz']:
    if name.endswith('.npz'):
        with np.load(reference/name) as a,np.load(probe/name) as b:equal=a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
    else:equal=(reference/name).read_bytes()==(probe/name).read_bytes()
    checks[name]=equal
    assert equal,name
c.json_write(FAMILY/'holdout_perturbation_audit.json',dict(status='PASSED',dataset=dataset,reference=str(reference),probe=str(probe),checks=checks,
    mutation='excluded XYZ += N(0,100); Z *=100; confidence=1e8; original files untouched',scope='candidate geometry, model selection, membership, normals invariant to heldout geometry/confidence'))
print(json.dumps(checks))
