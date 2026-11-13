"""G5a preselected indoor window, one joint Omega host GPU inference."""
import sys,json,tarfile,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/camera_fov_alignment'));import common as c
sys.path.insert(0,str(ROOT/'thirdparty/vggt-omega'))
import torch
from vggt_omega.models import VGGTOmega
from vggt_omega.utils.load_fn import load_and_preprocess_images
from vggt_omega.utils.pose_enc import encoding_to_camera
out=ROOT/'results/point_line_depth_refinement/extra_indoor_100_110_120';out.mkdir(parents=True,exist_ok=False)
archive=ROOT/'data/pointmap_refinement/tum/rgbd_dataset_freiburg1_desk.tgz'
with tarfile.open(archive) as tar:
 members=sorted([m for m in tar.getmembers() if '/rgb/' in m.name and m.name.endswith('.png')],key=lambda m:m.name);rows=[]
 for idx in [100,110,120]:
  member=members[idx];p=out/Path(member.name).name;p.write_bytes(tar.extractfile(member).read());rows.append({'index':idx,'source_member':member.name,'path':str(p),'sha256':c.record(p)['sha256']})
c.json_write(out/'frames.json',rows);torch.manual_seed(0);assert torch.cuda.is_available()
model=VGGTOmega().eval();model.load_state_dict(torch.load(ROOT/'checkpoints/vggt_omega_1b_512.pt',map_location='cpu',weights_only=True),strict=True);model=model.cuda();images=load_and_preprocess_images([r['path'] for r in rows],mode='max_size',image_resolution=512).cuda()
with torch.inference_mode():
 pred=model(images);extr,intr=encoding_to_camera(pred['pose_enc'],pred['images'].shape[-2:])
pred.update(extrinsics=extr,intrinsics=intr);arrays={k:v.detach().float().cpu().numpy() for k,v in pred.items() if isinstance(v,torch.Tensor)}
np.savez_compressed(out/'raw.npz',**arrays)
c.json_write(out/'provenance.json',{'context':'host GPU outside sandbox','frame_indices':[100,110,120],'joint_forward_calls':1,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'thirdparty/vggt-omega',text=True).strip(),'checkpoint':c.record(ROOT/'checkpoints/vggt_omega_1b_512.pt'),'archive':c.record(archive),'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'raw':c.record(out/'raw.npz')})
print('extra indoor inference finished',flush=True)
