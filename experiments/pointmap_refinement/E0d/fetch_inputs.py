"""Fetch a preregistered UAVScenes subset without downloading the full ZIP."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import traceback
import zlib

from remote_zip import open_zip


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    p=argparse.ArgumentParser();p.add_argument('--scene',required=True);p.add_argument('--run-id',required=True);a=p.parse_args()
    source=Path('experiments/pointmap_refinement/E0d');c=json.loads((source/'config.json').read_text());assert a.scene in c['scenes']
    s=Path('results/pointmap_refinement')/a.run_id/'stages/E0d';s.mkdir(parents=True,exist_ok=False)
    for name in ['artifacts/source','artifacts/data','artifacts/baseline','artifacts/maps','artifacts/initial','artifacts/figures','artifacts/gt','evaluation','logs']:(s/name).mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file():shutil.copy2(path,s/'artifacts/source'/path.name)
    helpers={'projection.py':'experiments/pointmap_refinement/E0a/run.py','fusion_base.py':'experiments/pointmap_refinement/E0b/run.py',
             'fusion_color.py':'experiments/pointmap_refinement/E0c/run.py','shared_preparation.py':'experiments/pointmap_refinement/E3c/prepare.py',
             'geometry.py':'experiments/pointmap_refinement/E1/geometry.py','infer.py':'experiments/pointmap_refinement/P0/scripts/infer.py',
             'export.py':'experiments/pointmap_refinement/E3d/run.py'}
    for name,path in helpers.items():shutil.copy2(path,s/'artifacts/source'/name)
    projection=module('projection',s/'artifacts/source/projection.py')
    m={'experiment_code':'E0d','run_id':a.run_id,'scene':a.scene,'status':'running','phase':'fetching','started_at':projection.stamp()};projection.json_write(s/'manifest.json',m)
    projection.json_write(s/'config_resolved.json',c|{'scene':a.scene,'run_id':a.run_id})
    try:
        cat=json.loads(Path(c['catalog']).read_text());url=cat['url'];reader,archive=open_zip(url,cat['size'])
        prefix=f'interval5_CAM_LIDAR/interval5_{a.scene}/'
        cameras=sorted([x for x in archive.infolist() if x.filename.startswith(prefix+'interval5_CAM/') and x.filename.lower().endswith(('.jpg','.png'))],key=lambda x:float(Path(x.filename).stem))
        selected=[cameras[i] for i in c['selected_sorted_camera_indices']]
        cache=Path('data/UAVScenes')/c['dataset_revision']/a.scene;cache.mkdir(parents=True,exist_ok=True);records=[]
        def get(info,role):
            target=cache/role/Path(info.filename).name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                b=target.read_bytes();assert len(b)==info.file_size and zlib.crc32(b)==info.CRC
            else:
                b=archive.read(info);assert len(b)==info.file_size and zlib.crc32(b)==info.CRC;target.write_bytes(b)
            rec=projection.record(target)|{'archive_member':info.filename,'crc32':info.CRC,'compressed_bytes':info.compress_size,'role':role}
            records.append(rec);return target
        meta=get(archive.getinfo(prefix+'sampleinfos_interpolated.json'),'metadata')
        metadata=json.loads(meta.read_text());lookup={row['OriginalImageName']:row for row in metadata}
        positions=[lookup[Path(x.filename).name]['T4x4'] for x in cameras]
        import math
        first=next(i for i in range(120,len(cameras)-8) if math.sqrt(sum((positions[i+8][j][3]-positions[i][j][3])**2 for j in range(3)))>=5)
        assert c['selected_sorted_camera_indices']==[first,first+4,first+8]
        frames=[]
        for index,info in zip(c['selected_sorted_camera_indices'],selected):
            image=get(info,'images');timestamp=Path(info.filename).stem
            lidars=[x for x in archive.infolist() if x.filename.startswith(prefix+'interval5_LIDAR/image'+timestamp+'_lidar') and x.filename.endswith('.txt')]
            assert len(lidars)==1,(timestamp,len(lidars));lidar=get(lidars[0],'lidar')
            dest=s/'artifacts/data'/image.name;shutil.copy2(image,dest)
            frames.append({'index':index,'timestamp':timestamp,'path':str(dest),'image_sha256':projection.record(dest)['sha256'],'lidar_path':str(lidar),'image_member':info.filename,'lidar_member':lidars[0].filename,'camera_metadata':lookup[info.filename.split('/')[-1]]})
        calibration=Path('data/UAVScenes')/c['dataset_revision']/'calibration_results.py';assert calibration.is_file();shutil.copy2(calibration,s/'artifacts/data/calibration_results.py')
        projection.json_write(s/'artifacts/data/frames.json',{'frames':frames})
        projection.json_write(s/'artifacts/data/download.json',{'repo':c['dataset_repo'],'revision':c['dataset_revision'],'archive_lfs_sha256':c['archive_lfs_sha256'],
            'full_archive_downloaded':False,'full_archive_hash_locally_verified':False,'verification':'pinned revision and ZIP member CRC/size plus extracted SHA256; not a full-archive SHA verification',
            'records':records,'range_transfers':reader.transfers,'network_bytes_this_process':sum(x['bytes'] for x in reader.transfers),'metadata':str(meta),
            'project_commit_before_run':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})
        inputs=[projection.record(Path(c['catalog'])),projection.record(calibration)]+[projection.record(x['path']) for x in records]
        m.update(phase='inputs_ready',inputs=inputs);projection.json_write(s/'manifest.json',m)
        result={'scene':a.scene,'frames':frames,'metadata':str(meta),'network_bytes':sum(x['bytes'] for x in reader.transfers)}
        (s/'logs/fetch.log').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    except Exception:
        m.update(status='failed',error=traceback.format_exc(),ended_at=projection.stamp());projection.json_write(s/'manifest.json',m);raise


if __name__=='__main__':main()
