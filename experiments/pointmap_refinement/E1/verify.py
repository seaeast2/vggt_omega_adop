"""Reload frozen diagnostic masks; calibrate two-layer probes; scientific previews."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
from geometry import front_map,rec

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage
geo=json.loads((s/'evaluation/geometry.json').read_text());ren=json.loads((s/'evaluation/render.json').read_text())
k=np.array([[100.,0,1],[0,100.,1],[0,0,1.]])
e=np.c_[np.eye(3),np.zeros(3)]
near,_,_=front_map(np.array([[0,0,2.]]),k,e,3,3);far,_,_=front_map(np.array([[0,0,2.04]]),k,e,3,3)
assert np.isclose((far-near)[1,1],.04) and np.isclose(((far-near)/near)[1,1],.02)
identical,_,_=front_map(np.array([[0,0,2.],[0,0,2.]]),k,e,3,3);assert identical[1,1]==near[1,1]
for row in geo['pairs']:
    with np.load(s/'artifacts/diagnostics'/f"pair_{row['source']}_to_{row['target']}.npz") as data:
        mask=data['evaluation_mask'];rel=np.abs(data['source_front_depth'][mask]-data['target_initial_depth'][mask])/data['target_initial_depth'][mask]
        assert int(mask.sum())==row['fixed_evaluation_pixels']
        assert np.isclose(np.median(rel),row['absolute_relative_depth']['median'])
        assert np.isclose(np.mean(rel>.03),row['disagreement_fraction'])
for row in ren['frames']:
    with np.load(s/'artifacts/renders'/f"{row['mode']}_frame_{row['frame']}.npz") as d:
        assert np.isfinite(d['rgb']).all() and np.isfinite(d['depth']).all()
        assert np.array_equal(d['coverage'],d['alpha']>=.5)
        assert np.isclose(d['coverage'].mean(),row['coverage_fraction'])
        with np.load(s/'artifacts/renders'/f"evaluation_masks_frame_{row['frame']}.npz") as masks:
            mask=masks['fixed_all_mask'];score=-10*np.log10(((d['rgb']-d['target'])**2)[mask].mean())
            assert np.isclose(score,row['psnr_fixed_all_mask'])
with np.load(s/'artifacts/f0/vggt_omega_raw.npz') as d:rgb=d['images'][0].transpose(0,2,3,1)
h,w=rgb.shape[1:3];panel=np.full((3*(h+35),3*w,3),255,np.uint8)
for i in range(3):
    with np.load(s/'artifacts/diagnostics'/f'layers_target_{i}.npz') as data:
        value=data['relative_layer_spread'];valid=data['layer_evaluation_mask'];support=data['support']
        display=np.zeros((h,w),np.uint8);display[valid]=np.rint(np.clip(value[valid]/.1,0,1)*255).astype('uint8')
        heat=cv2.applyColorMap(display,cv2.COLORMAP_TURBO);heat[~valid]=0
        sv=cv2.applyColorMap((support*85).astype('uint8'),cv2.COLORMAP_TURBO)
    start=i*(h+35)
    for j,(im,name) in enumerate([(np.rint(rgb[i]*255).astype('uint8')[...,::-1],'target'),(heat,'relative spread 0-10%'),(sv,'support views 0-3')]):
        panel[start+35:start+35+h,j*w:(j+1)*w]=im;cv2.putText(panel,f'{i} {name}',(j*w+5,start+22),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
assert cv2.imwrite(str(s/'artifacts/diagnostics/layer_spread.png'),panel)
result={'controlled_identical_layer':'zero spread','controlled_two_layer_z_gap':.04,'controlled_relative_gap':.02,'pair_mask_reload':'passed','render_npz_reload_and_psnr':'passed','status':'passed'}
(s/'evaluation/verification.json').write_text(json.dumps(result,indent=2))
handoff={'f0_observations':rec(s/'artifacts/f0/observations.npz'),'f0_ply':rec(s/'artifacts/f0/f0_observations.ply'),'fixed_pair_evaluation_masks':[rec(p) for p in sorted((s/'artifacts/diagnostics').glob('pair_*.npz'))],'fixed_render_masks':[rec(p) for p in sorted((s/'artifacts/renders').glob('evaluation_masks_*.npz'))],'policy':'Reuse initial target-pixel masks for comparison; report missing prediction coverage instead of silently dropping pixels. Do not equate layer spread or voxel co-occupancy with accuracy.'}
(s/'evaluation/handoff.json').write_text(json.dumps(handoff,indent=2));print(json.dumps(result))
