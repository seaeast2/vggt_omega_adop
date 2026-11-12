"""Full E0 observation cloud: all, own-source, cross-source render diagnostics."""
import argparse,importlib.util,json,time
from pathlib import Path
import cv2,numpy as np,torch
spec=importlib.util.spec_from_file_location('p2','experiments/pointmap_refinement/P2/renderer.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();s=a.stage;c=json.loads((s/'config_resolved.json').read_text())
def t(x):return torch.as_tensor(x,device='cuda',dtype=torch.float32)
with np.load(s/'artifacts/f0/observations.npz') as d:obs={key:d[key] for key in d.files}
with np.load(s/'artifacts/f0/vggt_omega_raw.npz') as d:rgb=d['images'][0].transpose(0,2,3,1);ks=d['intrinsics'][0];es=d['extrinsics'][0]
torch.manual_seed(0);torch.cuda.reset_peak_memory_stats();x=t(obs['world_xyz_initial']);color=t(obs['rgb']/255.);fid=obs['frame_id'];h,w=c['render_hw'];sh,sw=rgb.shape[1:3];aff=np.array([[w/sw,0,(w/sw-1)/2],[0,h/sh,(h/sh-1)/2],[0,0,1]],np.float32)
rows=[]
for i in range(3):
    target=cv2.resize(rgb[i],(w,h),interpolation=cv2.INTER_AREA);images={};alphas={};coverage={}
    for name,mask in [('all',np.ones(len(fid),bool)),('own',fid==i),('cross',fid!=i)]:
        select=torch.as_tensor(mask,device='cuda');torch.cuda.synchronize();start=time.perf_counter()
        with torch.no_grad():out,dep,alpha=mod.render(x[select],color[select],t(aff@ks[i]),t(es[i]),h,w)
        torch.cuda.synchronize();seconds=time.perf_counter()-start
        image=out.cpu().numpy();depth=dep.cpu().numpy();al=alpha.cpu().numpy();assert np.isfinite(image).all() and np.isfinite(depth).all()
        images[name]=image;alphas[name]=al;coverage[name]=al>=c['coverage_threshold']
        np.savez_compressed(s/'artifacts/renders'/f'{name}_frame_{i}.npz',rgb=image,depth=depth,alpha=al,coverage=coverage[name],target=target)
        rows.append({'frame':i,'mode':name,'points':int(mask.sum()),'coverage_fraction':float(coverage[name].mean()),'render_seconds':seconds})
        del out,dep,alpha,select
    fixed=coverage['all'];common=fixed&coverage['own']&coverage['cross']
    for row in rows[-3:]:
        image=images[row['mode']]
        def score(mask):return float(-10*np.log10(max(float(((image-target)**2)[mask].mean()),1e-20))) if mask.any() else None
        row.update(psnr_fixed_all_mask=score(fixed),psnr_common_mask=score(common),psnr_all_pixels=score(np.ones((h,w),bool)),fixed_mask_pixels=int(fixed.sum()),common_mask_pixels=int(common.sum()))
    np.savez_compressed(s/'artifacts/renders'/f'evaluation_masks_frame_{i}.npz',fixed_all_mask=fixed,common_mask=common)
    panel=np.full((h+30,w*4,3),255,np.uint8)
    for col,(name,image) in enumerate([('target',target)]+list(images.items())):
        panel[30:,col*w:(col+1)*w]=np.rint(image.clip(0,1)*255).astype('uint8')[...,::-1];cv2.putText(panel,name,(col*w+3,20),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
    assert cv2.imwrite(str(s/'artifacts/renders'/f'comparison_{i}.png'),panel)
result={'frames':rows,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'renderer':'unchanged P2 Gaussian hard front gate .03','torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),'execution_context':'host GPU outside sandbox','optimization_performed':False,'cross_is_heldout':False,'timing_scope':'single forward per condition, includes indexed GPU input selection'}
(s/'evaluation/render.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
