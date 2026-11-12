"""Read-only geometry diagnosis of black-background alpha darkening."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import time

import cv2
import numpy as np


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--run-id',required=True); args=parser.parse_args()
    source=Path('experiments/pointmap_refinement/P2b'); config=json.loads((source/'config.json').read_text())
    stage=Path('results/pointmap_refinement')/args.run_id/'stages/P2b'; stage.mkdir(parents=True,exist_ok=False)
    for folder in ['artifacts/source','artifacts/images','artifacts/buffers','evaluation','logs']:(stage/folder).mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file():shutil.copy2(path,stage/'artifacts/source'/path.name)
    projection=Path('experiments/pointmap_refinement/E0a/run.py');shutil.copy2(projection,stage/'artifacts/source/projection.py')
    renderer=Path('experiments/pointmap_refinement/P2/renderer.py');shutil.copy2(renderer,stage/'artifacts/source/renderer.py')
    spec=importlib.util.spec_from_file_location('projection',stage/'artifacts/source/projection.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
    start=time.perf_counter();parent=Path(config['parent_stage']);pm=json.loads((parent/'manifest.json').read_text());assert pm['status']=='completed'
    inputs=[p.record(parent/'manifest.json'),p.record(renderer),p.record(projection)]
    manifest={'experiment_code':'P2b','run_id':args.run_id,'status':'running','started_at':p.stamp()};p.json_write(stage/'manifest.json',manifest)
    p.json_write(stage/'config_resolved.json',config|{'run_id':args.run_id})
    records=[];cells=[]
    for camera in range(3):
        path=parent/f'artifacts/renders/initial_frame_{camera}.npz'
        assert p.record(path)==next(row for row in pm['artifacts'] if row['path']==str(path));inputs.append(p.record(path))
        with np.load(path) as data:
            rgb=data['rgb'];alpha=data['alpha'];target=data['target'];train=data['train_mask'];e1=data['e1_mask']
        valid=alpha>config['alpha_epsilon'];normalized=np.zeros_like(rgb);normalized[valid]=rgb[valid]/alpha[valid,None]
        assert np.isfinite(normalized).all() and normalized.min()>=0 and normalized.max()<1.00001
        assert np.max(np.abs(normalized[valid]*alpha[valid,None]-rgb[valid]),initial=0)<1e-6
        normalized=np.clip(normalized,0,1)
        bright=target.mean(-1)>config['bright_reference_threshold'];dark=bright&(rgb.mean(-1)<config['dark_render_threshold'])
        corrected_dark=bright&(normalized.mean(-1)<config['dark_render_threshold'])
        row={'camera':camera,'probe_dark_pixels_before':int(dark.sum()),'probe_dark_pixels_after':int(corrected_dark.sum()),
             'median_alpha_probe_dark':float(np.median(alpha[dark])),'probe_dark_in_training_mask':int((dark&train).sum()),
             'alpha_below_epsilon_pixels':int((~valid).sum()),'methods':[]}
        for name,image in [('saved_black_background',rgb),('alpha_removed_diagnostic',normalized)]:
            mse=float(((image-target)**2)[e1].mean());loss=float(np.sqrt((image-target)**2+config['charbonnier_epsilon']**2)[train].mean())
            row['methods'].append({'method':name,'psnr_fixed_e1_mask':float(-10*np.log10(max(mse,1e-20))),'charbonnier_fixed_training_mask':loss})
            png=np.rint(image.clip(0,1)*255).astype(np.uint8);p.image_write(stage/f'artifacts/images/camera_{camera}_{name}.png',png)
        a=np.repeat(alpha[...,None],3,axis=2)
        images=[target,rgb,normalized,a]
        cells.append([cv2.resize(np.rint(image.clip(0,1)*255).astype(np.uint8),(512,384),interpolation=cv2.INTER_NEAREST) for image in images])
        np.savez_compressed(stage/f'artifacts/buffers/camera_{camera}.npz',saved_rgb=rgb,alpha=alpha,target=target,normalized_rgb=normalized,
                            valid_alpha_mask=valid,train_mask=train,e1_mask=e1,dark_probe_mask=dark)
        with np.load(stage/f'artifacts/buffers/camera_{camera}.npz') as saved:
            assert np.array_equal(saved['normalized_rgb'],normalized) and np.array_equal(saved['alpha'],alpha)
        records.append(row)
    frames=json.loads((parent/'artifacts/initial/frames.json').read_text())
    inputs.append(p.record(parent/'artifacts/initial/frames.json'))
    p.panel(stage/'artifacts/images/comparison.png',cells,
            ['Reference RGB','Saved RGB: black background','Alpha removed (diagnostic)','Alpha: black=0 / white=1'],frames,384,512)
    before=sum(row['probe_dark_pixels_before'] for row in records);after=sum(row['probe_dark_pixels_after'] for row in records)
    result={'camera_results':records,'probe_dark_before':before,'probe_dark_after':after,'probe_dark_in_training_mask':sum(row['probe_dark_in_training_mask'] for row in records),
            'probe_dark_reduction_fraction':1-after/before,'geometry_or_cameras_changed':False,'new_optimization':False,'gt_accessed':False,
            'limitations':'Cached-buffer color diagnosis only; alpha removal does not validate visibility or gradients; probes are brightness heuristics, not ground truth.'}
    p.json_write(stage/'evaluation/metrics.json',result)
    for item in inputs:assert p.record(item['path'])==item
    p.json_write(stage/'evaluation/verification.json',{'status':'passed','input_hashes_unchanged':True,'recomposite_matches_cached_rgb_on_valid_alpha':True,
                 'normalized_rgb_finite_and_in_range':True,'same_fixed_masks':True,'png_npz_reload':True,'no_geometry_or_training_change':True})
    p.json_write(stage/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,
                 'execution_context':'host CPU; GPU unused','seconds':time.perf_counter()-start,
                 'source_files':[p.record(path) for path in sorted((stage/'artifacts/source').glob('*')) if path.is_file()]})
    (stage/'logs/run.log').write_text(json.dumps(result,indent=2)+'\n')
    manifest.update(status='completed',ended_at=p.stamp(),completion_criteria_met=True,inputs=inputs)
    manifest['artifacts']=[p.record(path) for path in sorted(stage.rglob('*')) if path.is_file() and path.name!='manifest.json' and '__pycache__' not in path.parts]
    p.json_write(stage/'manifest.json',manifest);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
