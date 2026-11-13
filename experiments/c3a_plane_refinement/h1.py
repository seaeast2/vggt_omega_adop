"""Original RGB -> official GroundingDINO Swin-T + SAM ViT-H; no geometry feedback."""
from base import *
import gc

def run():
 st=Stage('H1',parents=[latest('H0a')],extra={'detector_runtime':'Transformers official IDEA-Research converted checkpoint; custom CUDA kernels disabled; float32','sam_runtime':'facebookresearch/segment-anything original ViT-H float32','mask_mapping':'640x480 -> 512x384 nearest, no crop','library_change':'transformers4.57.1 installed; huggingface_hub 2.4.0 -> 0.36.2 dependency resolution'})
 try:
  import torch,transformers
  from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
  sys.path.insert(0,str(ROOT/'thirdparty/segment-anything'))
  from segment_anything import sam_model_registry,SamPredictor
  assert torch.cuda.is_available();torch.manual_seed(0);np.random.seed(0)
  torch.cuda.reset_peak_memory_stats();data=load();images=[]
  for f in data['frames']:
   p=ROOT/f['path'];assert c.record(p)['sha256']==f['sha256'];im=c.cv2.imread(str(p))[...,::-1].copy();assert im.shape==(480,640,3);images.append(im)
  t=time.perf_counter();processor=AutoProcessor.from_pretrained(ROOT/'checkpoints/grounding-dino-tiny',local_files_only=True);model=AutoModelForZeroShotObjectDetection.from_pretrained(ROOT/'checkpoints/grounding-dino-tiny',local_files_only=True,disable_custom_kernels=True).eval().to('cuda');prepare_det=time.perf_counter()-t
  masksout=st.path/'artifacts/masks';masksout.mkdir(parents=True);dets=[];detsec=[]
  with torch.inference_mode():
   for i,im in enumerate(images):
    t=time.perf_counter();inputs=processor(images=im,text='wall.',return_tensors='pt').to('cuda');outputs=model(**inputs);res=processor.post_process_grounded_object_detection(outputs,inputs.input_ids,threshold=.25,text_threshold=.2,target_sizes=[im.shape[:2]])[0];torch.cuda.synchronize();detsec.append(time.perf_counter()-t)
    row={'camera':i,'boxes':res['boxes'].cpu().tolist(),'scores':res['scores'].cpu().tolist(),'text_labels':res['text_labels']};dets.append(row);st.log('detector',**row)
    np.savez_compressed(masksout/f'camera_{i}_detector_queries.npz',logits=outputs.logits.cpu().numpy(),pred_boxes=outputs.pred_boxes.cpu().numpy(),input_ids=inputs.input_ids.cpu().numpy())
  del model,outputs,inputs;gc.collect();torch.cuda.empty_cache()
  t=time.perf_counter();sam=sam_model_registry['vit_h'](checkpoint=str(ROOT/'checkpoints/sam/sam_vit_h_4b8939.pth')).eval().to('cuda');predictor=SamPredictor(sam);prepare_sam=time.perf_counter()-t;samsec=[];counts=[]
  with torch.inference_mode():
   for i,im in enumerate(images):
    t=time.perf_counter();predictor.set_image(im);ms=[];scores=[];low=[]
    for box in dets[i]['boxes']:
     mm,sc,lo=predictor.predict(box=np.array(box),multimask_output=False);ms.append(mm[0]);scores.append(float(sc[0]));low.append(lo[0])
    raw=np.array(ms,bool) if ms else np.zeros((0,480,640),bool)
    mapped=np.array([c.cv2.resize(m.astype(np.uint8),(512,384),interpolation=c.cv2.INTER_NEAREST)>0 for m in raw]) if len(raw) else np.zeros((0,384,512),bool)
    torch.cuda.synchronize();samsec.append(time.perf_counter()-t);counts.append([int(m.sum()) for m in mapped]);np.savez_compressed(masksout/f'camera_{i}_masks.npz',raw_masks=raw,masks=mapped,boxes=np.array(dets[i]['boxes']),sam_scores=np.array(scores),low_res_logits=np.array(low),embedding=predictor.features.cpu().numpy(),original_size=predictor.original_size,input_size=predictor.input_size)
    show=im.copy();colors=np.random.default_rng(0).integers(30,255,(max(1,len(raw)),3))
    for j,mask in enumerate(raw):show[mask]=np.rint(.55*show[mask]+.45*colors[j]).astype(np.uint8)
    for box in dets[i]['boxes']:x0,y0,x1,y1=map(int,box);c.cv2.rectangle(show,(x0,y0),(x1,y1),(255,80,0),2)
    c.image_write(st.path/f'artifacts/figures/camera_{i}_wall_overlay.png',show);st.log('sam',camera=i,areas=counts[-1],scores=scores,seconds=samsec[-1])
  metadata=[]
  for p in sorted((ROOT/'checkpoints/grounding-dino-tiny').glob('*')):
   if p.is_file():metadata.append(c.record(p))
  metadata.append(c.record(ROOT/'checkpoints/sam/sam_vit_h_4b8939.pth'))
  env={'torch':torch.__version__,'transformers':transformers.__version__,'huggingface_hub':__import__('huggingface_hub').__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'gpu_peak_allocated_mib':torch.cuda.max_memory_allocated()/2**20,'gpu_peak_reserved_mib':torch.cuda.max_memory_reserved()/2**20,'sam_source_commit':subprocess.check_output(['git','-C',str(ROOT/'thirdparty/segment-anything'),'rev-parse','HEAD'],text=True).strip(),'models':metadata}
  c.json_write(st.path/'evaluation/model_provenance.json',env);c.json_write(masksout/'detections.json',dets)
  st.finish({'decision':'AUTOMATIC_MASKS_FROZEN' if any(counts) else 'NO_WALL_DETECTION','detections':dets,'mask_areas_processed':counts,'timing_seconds':{'detector_model_load':prepare_det,'sam_model_load':prepare_sam,'detector_inference':detsec,'sam_embedding_and_masks':samsec},'model_provenance':env,'inputs':data['inputs']},'# H1 원본 영상 벽 분할\n\n원본 640×480 RGB 세 장에서 `wall.` / box 0.25 / text 0.2로 GroundingDINO Swin-T와 SAM ViT-H를 실행했다. 마스크를 nearest-neighbor로 512×384에 옮겼다. 원시 후보·박스·점수·SAM embedding·logit을 동결했으며 보정 점군을 사용하지 않았다.\n\nGroundingDINO는 공식 IDEA-Research HF 변환 가중치를 Transformers 4.57.1의 순수 PyTorch 경로로 실행했다. SAM은 원본 공식 구현과 ViT-H 가중치다. 라이브러리 설치 과정에서 huggingface_hub가 2.4.0에서 0.36.2로 변경되었다. 실제 checkpoint SHA256·버전·시간·GPU peak memory는 model_provenance.json에 있다. 점수는 평면성 확률이 아니다. 자동 누락·과포함은 다음 RGB 검토에 기록한다.')
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
