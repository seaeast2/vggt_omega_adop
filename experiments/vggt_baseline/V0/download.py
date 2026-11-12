"""Fetch the original official VGGT-1B checkpoint at an immutable HF revision."""
from pathlib import Path
import hashlib
import json
from huggingface_hub import HfApi, hf_hub_download


def main():
    root=Path(__file__).resolve().parents[3]
    target=root/'checkpoints/vggt_1b'
    target.mkdir(parents=True,exist_ok=True)
    info=HfApi(token=False).model_info('facebook/VGGT-1B',
        revision='860abec7937da0a4c03c41d3c269c366e82abdf9',files_metadata=True)
    row=next(x for x in info.siblings if x.rfilename=='model.pt')
    expected=row.lfs.sha256
    print(json.dumps({'event':'download_start','repository':'facebook/VGGT-1B',
        'revision':info.sha,'filename':'model.pt','bytes':row.size,'expected_sha256':expected}),flush=True)
    path=Path(hf_hub_download('facebook/VGGT-1B','model.pt',revision=info.sha,
        local_dir=target,token=False))
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    assert actual==expected and path.stat().st_size==row.size
    result={'repository':'facebook/VGGT-1B','revision':info.sha,'filename':'model.pt',
        'path':str(path.relative_to(root)),'bytes':row.size,'sha256':actual,
        'expected_hf_lfs_sha256':expected,'hash_verified':True}
    (target/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
