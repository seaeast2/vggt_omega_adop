"""Official MoGe-2 v2 inference on original frozen Omega processed images."""
from pathlib import Path
import sys,time,json,subprocess
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'thirdparty/MoGe'));sys.path.insert(0,str(ROOT/'experiments/camera_fov_alignment'))
import common as c
from moge.model.v2 import MoGeModel
out=ROOT/'results/point_line_depth_refinement/external_moge2';out.mkdir(parents=True,exist_ok=True)
assert torch.cuda.is_available()
torch.manual_seed(0)
print('Loading official Ruicheng/moge-2-vitl',flush=True)
from huggingface_hub import HfApi,hf_hub_download
info=HfApi().model_info('Ruicheng/moge-2-vitl');checkpoint=hf_hub_download('Ruicheng/moge-2-vitl','model.pt',revision=info.sha)
model=MoGeModel.from_pretrained(checkpoint).eval().to('cuda');data=c.load_data('tum-freiburg1_desk');depth=[];mask=[];intrinsics=[]
for i,rgb in enumerate(data['rgb']):
 image=torch.from_numpy(rgb.copy()).permute(2,0,1).float().cuda()/255
 with torch.inference_mode():output=model.infer(image,resolution_level=9,use_fp16=True)
 depth.append(output['depth'].cpu().numpy());mask.append(output['mask'].cpu().numpy());intrinsics.append(output['intrinsics'].cpu().numpy());print('frame',i,'finished',flush=True)
np.savez_compressed(out/'depth.npz',depth=np.stack(depth),mask=np.stack(mask),intrinsics=np.stack(intrinsics))
c.json_write(out/'provenance.json',{'model_repo':'Ruicheng/moge-2-vitl','revision':info.sha,'checkpoint':c.record(checkpoint),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'thirdparty/MoGe',text=True).strip(),'context':'host GPU outside sandbox','torch':torch.__version__,'gpu':torch.cuda.get_device_name(),'seed':0,'resolution_level':9,'use_fp16':True,'depth_definition':'official output depth = points[...,2] camera Z','input_shapes':list(data['rgb'].shape),'input_provenance':data['inputs'],'peak_allocated_bytes':torch.cuda.max_memory_allocated()})
