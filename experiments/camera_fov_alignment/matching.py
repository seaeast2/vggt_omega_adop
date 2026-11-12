"""Image-only fixed correspondences, conflict-free tracks, frozen spatial split."""
import hashlib
import itertools
import cv2
import numpy as np
import common as c


def depth_samples(data,camera,uv):
    d,conf=data['depth'][camera],data['conf'][camera]
    h,w=d.shape
    xy=np.floor(uv).astype(int)
    inside=(xy[:,0]>=0)&(xy[:,0]<w-1)&(xy[:,1]>=0)&(xy[:,1]<h-1)
    xy[:,0]=xy[:,0].clip(0,w-2);xy[:,1]=xy[:,1].clip(0,h-2)
    x,y=xy.T
    support=np.column_stack([d[y,x],d[y,x+1],d[y+1,x],d[y+1,x+1]])
    confidence=np.column_stack([conf[y,x],conf[y,x+1],conf[y+1,x],conf[y+1,x+1]])
    threshold=float(np.percentile(conf[np.isfinite(conf)],10))
    good=inside&np.isfinite(support).all(1)&(support>0).all(1)&\
        np.isfinite(confidence).all(1)&(confidence>=threshold).all(1)
    good&=(support.max(1)-support.min(1))/np.median(support,axis=1)<=.03
    dx,dy=(uv-xy).T
    weights=np.column_stack([(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy])
    result=(weights*support).sum(1)
    return result,good,threshold


def pair_support(matches,h,w):
    rows=[]
    for i,j in itertools.combinations(range(3),2):
        mask=(matches['pair'][:,0]==i)&(matches['pair'][:,1]==j)
        total=int(mask.sum());validation=int((mask&matches['validation']).sum());fit=total-validation
        cells=[]
        for field in ['uv_i','uv_j']:
            uv=matches[field][mask]
            cells.append(int(len(np.unique(np.minimum(3,(uv[:,0]*4/w).astype(int))+
                4*np.minimum(3,(uv[:,1]*4/h).astype(int))))))
        passed=total>=100 and fit>=50 and validation>=20 and min(cells)>=6
        rows.append({'pair':[i,j],'total':total,'fit':fit,'validation':validation,
            'occupied_4x4_cells':cells,'passed':passed})
    return {'pairs':rows,'passed':all(r['passed'] for r in rows)}


def extract(data,output,stage):
    output.mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(2);cv2.setRNGSeed(0)
    sift=cv2.SIFT_create(nfeatures=8192)
    keys=[];descriptors=[]
    for i,rgb in enumerate(data['rgb']):
        kp,desc=sift.detectAndCompute(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),None)
        keys.append(np.array([p.pt for p in kp],float).reshape(-1,2));descriptors.append(desc)
        np.savez_compressed(output/f'features_{i}.npz',uv=keys[-1],descriptor=desc)
    offsets=np.r_[0,np.cumsum([len(x) for x in keys])]
    parent=np.arange(offsets[-1])
    def find(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]];a=parent[a]
        return a
    def union(a,b):
        aa,bb=find(a),find(b)
        if aa!=bb:parent[max(aa,bb)]=min(aa,bb)
    edges=[];reports=[]
    bf=cv2.BFMatcher(cv2.NORM_L2)
    for i,j in itertools.combinations(range(3),2):
        def ratio_pairs(a,b):
            if descriptors[a] is None or descriptors[b] is None or len(descriptors[b])<2:return set()
            return {(m[0].queryIdx,m[0].trainIdx) for m in bf.knnMatch(descriptors[a],descriptors[b],k=2)
                if len(m)==2 and m[0].distance<.75*m[1].distance}
        forward=ratio_pairs(i,j);backward={(b,a) for a,b in ratio_pairs(j,i)}
        mutual=np.array(sorted(forward&backward),np.int64).reshape(-1,2)
        inlier=np.zeros(len(mutual),bool);fundamental=np.empty((0,3))
        if len(mutual)>=8:
            cv2.setRNGSeed(0)
            fundamental,mask=cv2.findFundamentalMat(keys[i][mutual[:,0]],keys[j][mutual[:,1]],
                cv2.FM_RANSAC,1.5,.999,10000)
            if fundamental is not None and mask is not None and fundamental.shape==(3,3):
                inlier=mask.ravel().astype(bool)
            else:fundamental=np.empty((0,3))
        accepted=mutual[inlier]
        for a,b in accepted:
            union(offsets[i]+a,offsets[j]+b);edges.append((i,int(a),j,int(b)))
        np.savez_compressed(output/f'pair_{i}_{j}_ransac.npz',mutual_feature_ids=mutual,
            ransac_inliers=inlier,fundamental=fundamental)
        reports.append({'pair':[i,j],'features':[len(keys[i]),len(keys[j])],
            'forward_ratio':len(forward),'mutual_ratio':len(mutual),'ransac_inliers':len(accepted)})
        stage.log('image_correspondences',**reports[-1])
    groups={}
    for i,a,j,b in edges:
        for camera,index in [(i,a),(j,b)]:
            root=find(offsets[camera]+index)
            groups.setdefault(root,set()).add((camera,index))
    conflict=0;tracks=[]
    h,w=data['depth'].shape[1:]
    rows=[]
    for root,members in sorted(groups.items()):
        members=sorted(members)
        if len({camera for camera,index in members})!=len(members):
            conflict+=1;continue
        observations=[]
        for camera,index in members:
            uv=keys[camera][index:index+1]
            depth,good,threshold=depth_samples(data,camera,uv)
            if good[0]:observations.append((camera,index,uv[0],float(depth[0])))
        if len(observations)<2:continue
        # Anchor remains the minimum original camera, even when depth invalidates an observation.
        anchor_camera,anchor_index=members[0]
        anchor_uv=keys[anchor_camera][anchor_index]
        tx=min(15,int(anchor_uv[0]*16/w));ty=min(11,int(anchor_uv[1]*12/h))
        digest=hashlib.sha256(f'0:{anchor_camera}:{tx}:{ty}'.encode()).digest()
        validation=int.from_bytes(digest[:8],'little')%5==0
        track_id=len(tracks)
        tracks.append({'track':track_id,'feature_members':members,
            'valid_depth_cameras':[o[0] for o in observations],
            'anchor':[anchor_camera,tx,ty],'validation':validation})
        for left,right in itertools.combinations(observations,2):
            i,a,uv_i,di=left;j,b,uv_j,dj=right
            rows.append((i,j,uv_i,uv_j,di,dj,track_id,validation))
    matches={'pair':np.array([[x[0],x[1]] for x in rows],np.int16).reshape(-1,2),
        'uv_i':np.array([x[2] for x in rows],float).reshape(-1,2),
        'uv_j':np.array([x[3] for x in rows],float).reshape(-1,2),
        'di':np.array([x[4] for x in rows]),'dj':np.array([x[5] for x in rows]),
        'track_id':np.array([x[6] for x in rows],np.int64),
        'validation':np.array([x[7] for x in rows],bool)}
    np.savez_compressed(output/'matches.npz',**matches)
    c.json_write(output/'tracks.json',tracks)
    support=pair_support(matches,h,w)
    report={'image_pair_matching':reports,'conflicting_tracks_discarded':conflict,
        'retained_tracks':len(tracks),'pair_observations':len(rows),'support':support,
        'confidence_thresholds':[float(np.percentile(x[np.isfinite(x)],10)) for x in data['conf']],
        'fundamental_matrix_is_not_correspondence_GT':True,
        'split':'SHA256 seed0/min-original-camera/16x12 anchor tile; whole tracks grouped'}
    c.json_write(output/'matching.json',report)
    assert not (set(matches['track_id'][matches['validation']]) &
                set(matches['track_id'][~matches['validation']]))
    return matches,report


def subset(matches,mask):
    return {k:v[mask] for k,v in matches.items()}


def load(path):
    with np.load(path) as z:return {k:z[k] for k in z.files}
