"""I1 official GroundingDINO + SAM AMG. Host CUDA only; sequential model lifetime."""
from core import *
import gc

def run(dataset_names=None):
    stages=[Stage('I1',name,[latest('I0',name) if name.startswith('eth3d-') else latest('I0')],dict(execution_context='host CUDA outside sandbox')) for name in (dataset_names or ['tum-freiburg1_desk','tum-freiburg1_desk-extra'])]
    try:
        import torch,transformers
        from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
        sys.path.insert(0,str(ROOT/'thirdparty/segment-anything'))
        from segment_anything import sam_model_registry,SamPredictor,SamAutomaticMaskGenerator
        from segment_anything.utils.amg import rle_to_mask
        assert os.environ.get('I_HOST_GPU')=='1','Use authorized host execution with I_HOST_GPU=1'
        assert torch.cuda.is_available();torch.manual_seed(0);np.random.seed(0);torch.cuda.reset_peak_memory_stats()
        datasets=[load(st.dataset) for st in stages];images=[[c.cv2.imread(str(p))[...,::-1].copy() for p in d['image_paths']] for d in datasets]
        t=time.perf_counter();processor=AutoProcessor.from_pretrained(ROOT/'checkpoints/grounding-dino-tiny',local_files_only=True)
        detector=AutoModelForZeroShotObjectDetection.from_pretrained(ROOT/'checkpoints/grounding-dino-tiny',local_files_only=True,disable_custom_kernels=True).eval().cuda()
        detload=time.perf_counter()-t;detections=[]
        with torch.inference_mode():
            for st,ims in zip(stages,images):
                out=st.path/'artifacts/tags';out.mkdir();dd=[]
                for f,im in enumerate(ims):
                    t=time.perf_counter();inputs=processor(images=im,text=CFG['prompt'],return_tensors='pt').to('cuda');pred=detector(**inputs)
                    res=processor.post_process_grounded_object_detection(pred,inputs.input_ids,threshold=.25,text_threshold=.2,target_sizes=[im.shape[:2]])[0]
                    torch.cuda.synchronize();dd.append(dict(boxes=res['boxes'].cpu().tolist(),scores=res['scores'].cpu().tolist(),labels=res['text_labels'],seconds=time.perf_counter()-t))
                    np.savez_compressed(out/f'frame_{f}_detector_queries.npz',logits=pred.logits.cpu().numpy(),pred_boxes=pred.pred_boxes.cpu().numpy(),input_ids=inputs.input_ids.cpu().numpy())
                    st.log('detector',frame=f,detections=len(dd[-1]['boxes']))
                detections.append(dd);c.json_write(out/'detections.json',dd)
        del detector,pred,inputs;gc.collect();torch.cuda.empty_cache()
        t=time.perf_counter();sam=sam_model_registry['vit_h'](checkpoint=str(ROOT/'checkpoints/sam/sam_vit_h_4b8939.pth')).eval().cuda();samload=time.perf_counter()-t
        # Capture all quality-filtered masks BEFORE official box NMS, retaining the official output too.
        class TracedAMG(SamAutomaticMaskGenerator):
            def _process_batch(self,*args,**kwargs):
                data=super()._process_batch(*args,**kwargs)
                for i,rle in enumerate(data['rles']):self.trace.append(dict(rle=rle,iou=float(data['iou_preds'][i]),stability=float(data['stability_score'][i]),point=data['points'][i].cpu().tolist()))
                return data
        provenance=dict(torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(),
            context='host CUDA outside sandbox',sam_source_commit=subprocess.check_output(['git','-C',str(ROOT/'thirdparty/segment-anything'),'rev-parse','HEAD'],text=True).strip(),
            models=[c.record(ROOT/'checkpoints/sam/sam_vit_h_4b8939.pth')]+[c.record(p) for p in sorted((ROOT/'checkpoints/grounding-dino-tiny').glob('*')) if p.is_file()],
            det_model_load_seconds=detload,sam_model_load_seconds=samload)
        for st,d,ims,dd in zip(stages,datasets,images,detections):
            out=st.path/'artifacts/tags';allrecords=[];allmasks=[];frame_metrics=[];nextid=0
            with torch.inference_mode():
                for f,(im,det) in enumerate(zip(ims,dd)):
                    t=time.perf_counter();predictor=SamPredictor(sam);predictor.set_image(im);records=[];raw=[]
                    for k,box in enumerate(det['boxes']):
                        mask,sc,lo=predictor.predict(box=np.array(box),multimask_output=False)
                        raw.append(mask[0]);records.append(dict(source='grounded',semantic_tag=det['labels'][k],detector_score=det['scores'][k],sam_predicted_iou=float(sc[0]),box=box))
                    del predictor;torch.cuda.empty_cache();traced=[]
                    for batch in [16,8,4]:
                        try:
                            amg=TracedAMG(sam,points_per_side=32,points_per_batch=batch,crop_n_layers=0,pred_iou_thresh=.88,stability_score_thresh=.95,box_nms_thresh=.7,crop_nms_thresh=.7)
                            amg.trace=[];official=amg.generate(im);traced=amg.trace;break
                        except torch.cuda.OutOfMemoryError:
                            st.log('oom_retry',frame=f,batch=batch);del amg;gc.collect();torch.cuda.empty_cache()
                            if batch==4:raise
                    c.json_write(out/f'frame_{f}_automatic_pre_nms_rle.json',traced)
                    np.savez_compressed(out/f'frame_{f}_automatic_post_nms.npz',masks=np.array([r['segmentation'] for r in official],bool),iou=np.array([r['predicted_iou'] for r in official]))
                    selected_hashes={ahash(r['segmentation']) for r in official}
                    for r in traced:
                        mask=rle_to_mask(r['rle']);raw.append(mask);records.append(dict(source='automatic',semantic_tag='unknown',sam_predicted_iou=r['iou'],stability=r['stability'],point=r['point'],official_nms_retained=ahash(mask) in selected_hashes))
                    hh,ww=d['depth'].shape[1:]
                    raw=np.array(raw,bool);mapped=np.array([c.cv2.resize(a.astype('uint8'),(ww,hh),interpolation=c.cv2.INTER_NEAREST)>0 for a in raw])
                    seen={};unique=[];aliases=[]
                    for k,(a,r) in enumerate(zip(mapped,records)):
                        r|=dict(mask_id=nextid,frame=f,raw_hash=ahash(raw[k]),processed_hash=ahash(a),area=int(a.sum()),mapping='640x480->512x384 nearest, no crop');nextid+=1
                        key=ahash(a)
                        if key in seen:r['alias_of']=seen[key];aliases.append(dict(mask_id=r['mask_id'],alias_of=seen[key],reason='exact processed mask equality'))
                        else:seen[key]=r['mask_id'];unique.append(k)
                    # Many-to-many includes every raw candidate; aliases are preserved.
                    np.savez_compressed(out/f'frame_{f}_masks.npz',raw_masks=raw,masks=mapped,mask_ids=np.array([r['mask_id'] for r in records],np.int32))
                    idx=np.array(unique,dtype=int);um=mapped[idx]
                    packed=np.packbits(um.reshape(len(um),-1),axis=1);pop=np.array([int(i).bit_count() for i in range(256)],np.uint8)
                    dag=[]
                    for a,b in itertools.combinations(range(len(um)),2):
                        area_a,area_b=int(um[a].sum()),int(um[b].sum());both=int(pop[packed[a]&packed[b]].sum())
                        if not both:continue
                        parent,child=(a,b) if area_a>area_b else (b,a)
                        dag.append(dict(a=records[unique[a]]['mask_id'],b=records[unique[b]]['mask_id'],intersection=both,relation='contains' if both==min(area_a,area_b) else 'overlap',
                            parent=records[unique[parent]]['mask_id'] if both==min(area_a,area_b) else None,child=records[unique[child]]['mask_id'] if both==min(area_a,area_b) else None))
                    c.json_write(out/f'frame_{f}_hierarchy.json',dict(edges=dag,aliases=aliases))
                    counts=mapped.sum(0);c.image_write(out/f'frame_{f}_uncovered.png',np.repeat((counts==0)[...,None],3,axis=2).astype('uint8')*255)
                    show=d['rgb'][f].copy();rng=np.random.default_rng(0)
                    for a in um[np.argsort([-int(a.sum()) for a in um])]:show[a]=(.55*show[a]+.45*rng.integers(30,255,3)).astype('uint8')
                    c.image_write(st.path/f'artifacts/figures/frame_{f}_all_masks.png',show)
                    allrecords.extend(records);allmasks.extend([(f,a,r['mask_id']) for a,r in zip(mapped,records)])
                    torch.cuda.synchronize();frame_metrics.append(dict(frame=f,semantic_masks=len(det['boxes']),automatic_pre_nms=len(traced),automatic_post_nms=len(official),
                        raw_candidates=len(records),exact_unique=len(unique),uncovered_fraction=float((counts==0).mean()),batch=batch,seconds=time.perf_counter()-t))
                    st.log('sam_frame',**frame_metrics[-1]);del amg,raw,mapped;gc.collect();torch.cuda.empty_cache()
            obs=[];maskids=[]
            for f,a,mid in allmasks:
                ids=np.flatnonzero(a)+f*int(np.prod(d['depth'].shape[1:]));obs.append(ids);maskids.append(np.full(len(ids),mid,np.int32))
            obs=np.concatenate(obs);maskids=np.concatenate(maskids);order=np.lexsort((maskids,obs));obs=obs[order];maskids=maskids[order]
            indptr=np.r_[0,np.cumsum(np.bincount(obs,minlength=len(d['ids'])))].astype(np.int64)
            np.savez_compressed(out/'observation_mask_links.npz',indptr=indptr,mask_ids=maskids,observation_id=d['ids'])
            c.json_write(out/'mask_registry.json',allrecords)
            provenance['gpu_peak_allocated_mib']=torch.cuda.max_memory_allocated()/2**20;provenance['gpu_peak_reserved_mib']=torch.cuda.max_memory_reserved()/2**20
            c.json_write(st.path/'evaluation/model_provenance.json',provenance)
            st.finish(dict(decision='FULL_IMAGE_CANDIDATES_TAGGED',frames=frame_metrics,many_to_many_links=len(maskids),models=provenance),
                '# I1 전체 영상 SAM 후보\n\n고정 semantic prompt와 공식 SAM automatic grid32를 함께 실행했다. 원본 detector query·모든 semantic mask·quality filter 통과 후 NMS 전 automatic RLE와 NMS 후 출력을 별도 보존했다. '
                'quality filter 이전의 mask logits는 저장하지 않으며 이 제한을 명시한다. 동일 마스크는 alias로 기록하고 원본 ID는 삭제하지 않았다. 포함/겹침 DAG·uncovered map·원본 관측 ID의 CSR 연결을 저장했다. '
                'SAM score는 평면성 확률이 아니다. 수동 camera/ROI/plane 개수 입력은 없다.')
    except Exception as e:
        for st in stages:
            if st.manifest['status']=='running':st.fail(e)
        raise
if __name__=='__main__':run()
