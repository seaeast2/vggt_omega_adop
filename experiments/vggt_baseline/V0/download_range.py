"""Resume a stalled public checkpoint download; verify every range and final LFS SHA."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib
import json
import os
import shutil
import time

REVISION='860abec7937da0a4c03c41d3c269c366e82abdf9'
EXPECTED='d15bf50a8615c8225ed48b51ea5cac673d82442ec0309036df555a053253afe0'
SIZE=5026874952
CHUNK=32*1024*1024


def main():
    root=Path(__file__).resolve().parents[3];target=root/'checkpoints/vggt_1b'
    parts=target/'http_ranges';parts.mkdir(parents=True,exist_ok=True)
    url=f'https://huggingface.co/facebook/VGGT-1B/resolve/{REVISION}/model.pt?download=true'
    partials=list((target/'.cache/huggingface/download').glob(f'*.{EXPECTED}.*.incomplete'))
    prefix=partials[0] if len(partials)==1 else None
    prefix_size=prefix.stat().st_size if prefix is not None else 0
    assert 0<=prefix_size<=SIZE
    work=target/'model.pt.http_range.incomplete'
    if prefix is not None:shutil.copyfile(prefix,work)
    else:work.write_bytes(b'')
    fd=os.open(work,os.O_RDWR)
    records=[];started=time.perf_counter()
    print(json.dumps({'event':'range_resume','preserved_prefix_bytes':prefix_size,
        'total_bytes':SIZE,'workers':8,'chunk_bytes':CHUNK}),flush=True)
    def fetch(span):
        start,end=span;length=end-start+1;path=parts/f'{start}-{end}.part'
        if path.exists() and path.stat().st_size==length:
            return start,path.read_bytes(),True
        last=None
        for attempt in range(4):
            try:
                request=Request(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'})
                with urlopen(request,timeout=60) as response:
                    assert response.status==206
                    assert response.headers.get('Content-Range')==f'bytes {start}-{end}/{SIZE}'
                    payload=response.read(length+1)
                assert len(payload)==length
                temp=path.with_suffix('.tmp');temp.write_bytes(payload);temp.replace(path)
                return start,payload,False
            except Exception as error:
                last=type(error).__name__
                print(json.dumps({'event':'range_retry','start':start,'attempt':attempt+1,'error_type':last}),flush=True)
        raise RuntimeError(f'range {start}-{end} failed: {last}')
    def download(start,end):
        spans=[(i,min(i+CHUNK,end)-1) for i in range(start,end,CHUNK)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=[pool.submit(fetch,span) for span in spans]
            for job in as_completed(jobs):
                offset,payload,cached=job.result()
                written=0
                while written<len(payload):written+=os.pwrite(fd,payload[written:],offset+written)
                row={'start':offset,'bytes':len(payload),'cached':cached}
                records.append(row)
                print(json.dumps({'event':'range_completed',**row}),flush=True)
    try:
        download(prefix_size,SIZE)
        os.fsync(fd)
        with work.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        prefix_replaced=False
        if actual!=EXPECTED:
            # Xet may have left holes; replace prefix too, never accept an unverified file.
            print(json.dumps({'event':'prefix_hash_mismatch_redownload_prefix','bytes':prefix_size}),flush=True)
            download(0,prefix_size);os.fsync(fd);prefix_replaced=True
            with work.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        assert work.stat().st_size==SIZE and actual==EXPECTED
    finally:os.close(fd)
    work.replace(target/'model.pt')
    result={'repository':'facebook/VGGT-1B','revision':REVISION,'filename':'model.pt',
        'path':str((target/'model.pt').relative_to(root)),'bytes':SIZE,'sha256':actual,
        'expected_hf_lfs_sha256':EXPECTED,'hash_verified':True,
        'download_method':'verified parallel HTTP byte ranges after stalled SDK Xet download',
        'sdk_prefix_bytes_preserved':prefix_size,'prefix_redownloaded_after_full_hash_mismatch':prefix_replaced,
        'range_seconds':time.perf_counter()-started}
    (target/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    (target/'download_range_log.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'event':'complete',**result}),flush=True)


if __name__=='__main__':main()
