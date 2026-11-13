"""Fetch official ETH3D assets; run outside the network sandbox.

Keeps files local under ignored data/. Existing completed files are reused.
"""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/eth3d_laser'
CAMERA_COMMIT='d1bb0163229925f44ce9b52b384ab458f42712ba'
PIPELINE_COMMIT='e09275b39b30c9c59abf535b849fcc539dc03efd'
OFFICIAL_SOURCES={name:f'https://raw.githubusercontent.com/ETH3D/camera-model-implementations/{CAMERA_COMMIT}/cpp/src/{name}' for name in ['camera.h','camera.cc','util.h']}
OFFICIAL_SOURCES.update(ground_truth_creator_cc=f'https://raw.githubusercontent.com/ETH3D/dataset-pipeline/{PIPELINE_COMMIT}/src/exe/ground_truth_creator.cc')
OFFICIAL_SOURCES['ground_truth_creator.cc']=OFFICIAL_SOURCES.pop('ground_truth_creator_cc')
OFFICIAL_SOURCES['colmap_model.cc']=f'https://raw.githubusercontent.com/ETH3D/dataset-pipeline/{PIPELINE_COMMIT}/src/io/colmap_model.cc'

def fetch(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size>0:return
    temporary=path.with_suffix(path.suffix+'.partial')
    subprocess.run(['curl','-sS','--fail','--location','--continue-at','-','--retry','2','--connect-timeout','15','--max-time','1200','--output',str(temporary),url],check=True)
    temporary.rename(path)

def run():
    for scene in ['office','pipes']:
        for kind in ['undistorted','jpg','depth']:
            name=f'{scene}_dslr_{kind}.7z';fetch('https://eth3d.ethz.ch/data/'+name,DATA/'archives'/name)
    for name,url in OFFICIAL_SOURCES.items():fetch(url,DATA/'official_camera'/name)
    print('Official archives and pinned camera/depth source cached. Existing files reused.')

if __name__=='__main__':run()
