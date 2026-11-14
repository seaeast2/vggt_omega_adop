"""Acquire two ground-based outdoor LiDAR references without running a model.

Public KITTI ZIPs are read with HTTP ranges, preserving only required members.
ETH3D archives are cached in full. Run with network access; no GPU is used.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/outdoor_lidar_samples'
sys.path.insert(0, str(ROOT / 'experiments/global_planar_pointmap'))
from eth3d_laser import extract_archive, calibration


def record(path):
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest())


def curl(*args):
    return subprocess.check_output(['curl', '-sS', '--fail', '--location',
        '--retry', '2', '--connect-timeout', '15', '--max-time', '1200', *args])


class RemoteZip(io.RawIOBase):
    """Seekable HTTP-range file; cache exact responses for provenance/restart."""
    def __init__(self, url, cache):
        self.url, self.cache, self.pos = url, cache, 0
        cache.mkdir(parents=True, exist_ok=True)
        header = curl('--head', url).decode()
        (cache / 'head.txt').write_text(header)
        self.size = int(re.findall(r'content-length:\s*(\d+)', header, re.I)[-1])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, offset, whence=0):
        self.pos = offset + (0 if whence == 0 else self.pos if whence == 1 else self.size)
        return self.pos

    def read(self, n=-1):
        stop = self.size if n < 0 else min(self.size, self.pos + n)
        if stop <= self.pos: return b''
        start = self.pos
        path = self.cache / f'{start}-{stop-1}.bin'
        if not path.exists():
            temporary = path.with_suffix('.partial')
            headers = path.with_suffix('.headers')
            curl('--range', f'{start}-{stop-1}', '--dump-header', str(headers),
                 '--output', str(temporary), self.url)
            h = headers.read_text()
            assert re.search(rf'content-range:\s*bytes {start}-{stop-1}/{self.size}', h, re.I), h
            assert temporary.stat().st_size == stop-start
            temporary.rename(path)
        result = path.read_bytes()
        assert len(result) == stop-start
        self.pos = stop
        return result


def select_zip(url, key, accept):
    with zipfile.ZipFile(RemoteZip(url, DATA/'http_ranges'/key)) as archive:
        names = archive.namelist()
        (DATA/'http_ranges'/key/'members.json').write_text(json.dumps(names, indent=2))
        selected = [name for name in names if accept(name)]
        assert selected, key
        records = []
        for name in selected:
            target = DATA/'kitti_city'/name
            assert target.resolve().is_relative_to((DATA/'kitti_city').resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            # zipfile verifies the member CRC when read.
            value = archive.read(name)
            if not target.exists() or target.read_bytes() != value: target.write_bytes(value)
            records.append(dict(member=name, crc32=f'{archive.getinfo(name).CRC:08x}', **record(target)))
    return dict(url=url, archive_bytes=archive_size(key), members=records)


def archive_size(key):
    h = (DATA/'http_ranges'/key/'head.txt').read_text()
    return int(re.findall(r'content-length:\s*(\d+)', h, re.I)[-1])


def kitti():
    base = 'https://s3.eu-central-1.amazonaws.com/avg-kitti/'
    frames = ['0000000030', '0000000040', '0000000050']
    drive = '2011_09_26_drive_0005_sync'
    def raw_member(name):
        return (any(name.endswith('/'+frame+ext) for frame in frames for ext in ['.png','.bin','.txt'])
                and any('/'+kind+'/' in name for kind in ['image_02','velodyne_points','oxts'])) or name.endswith('timestamps.txt')
    raw = select_zip(base+'raw_data/2011_09_26_drive_0005/'+drive+'.zip', 'kitti_raw_0005', raw_member)
    calib = select_zip(base+'raw_data/2011_09_26_calib.zip', 'kitti_calib_0926', lambda name:name.endswith('.txt'))
    gt = select_zip(base+'data_depth_annotated.zip', 'kitti_annotated',
        lambda name:drive+'/' in name and '/image_02/' in name and any(name.endswith('/'+frame+'.png') for frame in frames))
    result = dict(dataset='kitti-city-0005', frames=frames, sequence=drive,
        sources=[raw,calib,gt], gt='Official KITTI accumulated/filtered LiDAR annotated depth; uint16 / 256 meters, zero invalid',
        raw_lidar='Synchronized Velodyne points are retained separately, not substituted for annotated GT',
        status='downloaded; no Omega inference or accuracy experiment')
    target=DATA/'kitti_city/acquisition.json';target.write_text(json.dumps(result,indent=2))
    print(json.dumps(dict(dataset=result['dataset'],members=sum(len(x['members']) for x in result['sources']))),flush=True)


def forest():
    archives=DATA/'eth3d_forest/archives';archives.mkdir(parents=True,exist_ok=True)
    records=[]
    for kind in ['rig_undistorted','rig','rig_depth']:
        name=f'forest_{kind}.7z';url='https://eth3d.ethz.ch/data/'+name;path=archives/name
        if not path.exists():
            partial=path.with_suffix('.partial')
            curl('--continue-at','-','--output',str(partial),url);partial.rename(path)
        records.append(dict(url=url,**record(path)))
        print(json.dumps(dict(downloaded=name,bytes=path.stat().st_size)),flush=True)
    # Full calibration + undistorted images. Original images/depth are selected later.
    out=DATA/'eth3d_forest/extracted'
    extract_archive(archives/'forest_rig_undistorted.7z',out)
    extract_archive(archives/'forest_rig.7z',out,lambda name:name.endswith('.txt'))
    (DATA/'eth3d_forest/acquisition.json').write_text(json.dumps(dict(dataset='eth3d-forest-rig',sources=records,
        gt='FARO Focus X330 laser-rendered original distorted camera-Z depth; float32 meters; infinity invalid',
        status='downloaded; frame selection and sample validation pending'),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('dataset',choices=['kitti','forest']);args=parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    {'kitti':kitti,'forest':forest}[args.dataset]()
