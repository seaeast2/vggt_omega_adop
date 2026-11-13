"""Exact mask coverage visualization; no inference, semantic relabeling or geometry change."""
from core import *

RED=np.array([255,0,0],np.uint8)
GREEN=np.array([0,255,0],np.uint8)
BLUE=np.array([0,0,255],np.uint8)

def contact(path,rows,titles,captions):
    h,w=rows[0][0].shape[:2];head=42;label=32
    canvas=np.full((head+len(rows)*(h+label),w*len(titles),3),245,np.uint8)
    for j,title in enumerate(titles):c.cv2.putText(canvas,title,(j*w+8,27),c.cv2.FONT_HERSHEY_SIMPLEX,.6,(20,20,20),1,c.cv2.LINE_AA)
    for i,row in enumerate(rows):
        y=head+i*(h+label)
        for j,cell in enumerate(row):
            c.cv2.putText(canvas,captions[i],(j*w+8,y+23),c.cv2.FONT_HERSHEY_SIMPLEX,.52,(20,20,20),1,c.cv2.LINE_AA)
            canvas[y+label:y+label+h,j*w:(j+1)*w]=cell
    c.image_write(path,canvas)

def run(dataset):
    parent=latest('I1',dataset)
    st=Stage('I1u',dataset,[parent],dict(visualization_only=True,unknown_policy='official AMG union minus all grounded semantic masks; semantic overlap has display priority',
        colors={'unknown_only':[255,0,0],'grounded_semantic':[0,255,0],'uncovered':[0,0,255]},geometry_optimization=False))
    try:
        data=load(dataset);tags=parent/'artifacts/tags';registry=json.loads((tags/'mask_registry.json').read_text());byid={r['mask_id']:r for r in registry}
        out=st.path/'artifacts/coverage';out.mkdir();fig=st.path/'artifacts/figures';counts=[];rows=[];partition_rows=[];raw_rows=[];captions=[];source=[]
        for frame in range(3):
            file=tags/f'frame_{frame}_masks.npz';source.append(c.record(file))
            with np.load(file) as z:masks=z['masks'];maskids=z['mask_ids']
            records=[byid[int(mid)] for mid in maskids];h,w=masks.shape[1:]
            def union(predicate):
                indices=[i for i,r in enumerate(records) if predicate(r)]
                return np.any(masks[indices],axis=0) if indices else np.zeros((h,w),bool)
            known=union(lambda r:r['source']=='grounded' and r['semantic_tag']!='unknown')
            automatic=union(lambda r:r['source']=='automatic' and r.get('official_nms_retained',False))
            raw_automatic=union(lambda r:r['source']=='automatic')
            targets=union(lambda r:r['source']=='grounded' and r['semantic_tag'] in ['table','screen','wall'])
            with np.load(tags/f'frame_{frame}_automatic_post_nms.npz') as z:
                official=z['masks'].any(0)
            check=c.cv2.resize(official.astype(np.uint8),(w,h),interpolation=c.cv2.INTER_NEAREST)>0
            assert np.array_equal(check,automatic),'Official post-NMS mask union mismatch'
            unknown=automatic&~known;overlap=automatic&known;uncovered=~(known|automatic)
            assert not (unknown&known).any() and not (unknown&uncovered).any()
            assert int(known.sum()+unknown.sum()+uncovered.sum())==h*w
            rgb=data['rgb'][frame];red=rgb.copy();red[unknown]=RED
            allred=rgb.copy();allred[automatic]=RED
            partition=np.empty_like(rgb);partition[known]=GREEN;partition[unknown]=RED;partition[uncovered]=BLUE
            # Exact solid colors on processing-grid pixels; no blur/alpha/AI image generation.
            c.image_write(fig/f'frame_{frame}_original.png',rgb)
            c.image_write(fig/f'frame_{frame}_unknown_only_red.png',red)
            c.image_write(fig/f'frame_{frame}_automatic_union_red.png',allred)
            c.image_write(fig/f'frame_{frame}_semantic_partition.png',partition)
            np.savez_compressed(out/f'frame_{frame}_coverage.npz',grounded_semantic=known,unknown_only=unknown,automatic_post_nms=automatic,automatic_pre_nms=raw_automatic,
                semantic_automatic_overlap=overlap,uncovered=uncovered,exact_table_screen_wall=targets)
            for name,mask in [('unknown_only',unknown),('grounded_semantic',known),('uncovered',uncovered)]:
                c.image_write(out/f'frame_{frame}_{name}_mask.png',np.repeat(mask[...,None],3,axis=2).astype('uint8')*255)
            values={'grounded_semantic':known,'unknown_only':unknown,'uncovered':uncovered,'automatic_post_nms_union':automatic,
                'automatic_pre_nms_union':raw_automatic,'semantic_automatic_overlap':overlap,'exact_table_screen_wall_union':targets}
            row=dict(frame=frame,source_index=data['frames'][frame]['index'],pixels=h*w,
                pixels_by_category={key:int(mask.sum()) for key,mask in values.items()},fractions={key:float(mask.mean()) for key,mask in values.items()},
                semantic_labels=sorted(set(r['semantic_tag'] for r in records if r['source']=='grounded')))
            counts.append(row);captions.append(f"index {row['source_index']} | unknown-only {unknown.mean():.2%}")
            rows.append([rgb,red]);partition_rows.append([rgb,partition]);raw_rows.append([rgb,allred]);st.log('frame_coverage',**row)
            del masks
        contact(fig/'unknown_only_comparison.png',rows,['Original RGB','Unknown-only: solid RED'],captions)
        contact(fig/'semantic_partition_comparison.png',partition_rows,['Original RGB','GREEN named | RED unknown | BLUE no mask'],captions)
        contact(fig/'automatic_union_comparison.png',raw_rows,['Original RGB','All automatic unknown masks: RED'],captions)
        aggregate={k:sum(r['pixels_by_category'][k] for r in counts)/sum(r['pixels'] for r in counts) for k in counts[0]['pixels_by_category']}
        c.json_write(st.path/'evaluation/coverage.json',dict(frames=counts,aggregate_fractions=aggregate,inputs=source+[c.record(tags/'mask_registry.json')],
            definitions={'grounded_semantic':'union of all GroundingDINO+SAM named masks, including mixed labels; predicted categories, not GT',
                'unknown_only':'official post-NMS automatic-mask union minus grounded-semantic union',
                'uncovered':'neither grounded nor official post-NMS automatic mask',
                'automatic_union':'all automatic masks have unknown semantic tags; overlaps with named masks retained'},
            geometry_changed=False,models_rerun=False))
        table='\n'.join(f"| {r['source_index']} | {r['fractions']['grounded_semantic']:.2%} | {r['fractions']['unknown_only']:.2%} | {r['fractions']['uncovered']:.2%} | {r['fractions']['automatic_post_nms_union']:.2%} |" for r in counts)
        st.finish(dict(decision='UNKNOWN_COVERAGE_VISUALIZED',aggregate_fractions=aggregate,geometry_changed=False,models_rerun=False),
            '# I1u unknown 영역 시각화\n\n기존 I1 마스크를 재사용했다. 재추론·의미 재분류·평면 보정은 수행하지 않았다. '
            '512×384 처리 격자에서 원색으로 표시했으며 원본 RGB를 나란히 배치했다.\n\n'
            '- 빨강: official automatic NMS 이후 unknown 마스크에 속하지만 이름 있는 GroundedSAM 마스크에는 속하지 않는 픽셀.\n'
            '- 초록: 이름 있는 GroundedSAM 마스크의 합집합. `wall ceiling` 같은 혼합 태그와 다른 이름도 포함하며 정확한 대상 분류를 보장하지 않는다.\n'
            '- 파랑: 두 경로 어디에도 포함되지 않는 미포함 픽셀.\n\n'
            '| 원본 index | 이름 있는 영역 | unknown-only | 미포함 | automatic unknown 전체 |\n| --- | --- | --- | --- | --- |\n'+table+
            '\n\n![원본과 unknown-only](figures/unknown_only_comparison.png)\n\n![이름 있는 영역과 unknown·미포함](figures/semantic_partition_comparison.png)\n\n'
            '![중첩 포함 automatic unknown 전체](figures/automatic_union_comparison.png)\n\n'
            '**unknown-only는 미지 물체의 정답 분류가 아니다.** 책·컵이 넓은 table 마스크에 포함되면 초록으로 표시될 수 있다. '
            '반대로 automatic unknown 마스크는 이미 이름이 있는 벽·화면·책상과도 겹친다. 따라서 모든 unknown 마스크의 합집합을 무조건 보존 mask로 사용하면 '
            '의도한 보정 대상도 대부분 제외될 수 있다. exact `table/screen/wall` 합집합은 NPZ에 별도 저장했지만 보정 정책으로 적용하지 않았다.')
        return st.doc,aggregate
    except Exception as error:st.fail(error);raise

if __name__=='__main__':
    for dataset in ['tum-freiburg1_desk','tum-freiburg1_desk-extra']:print(run(dataset),flush=True)
