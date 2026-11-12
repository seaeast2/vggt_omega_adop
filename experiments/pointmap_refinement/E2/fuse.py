"""Conservative projective association with unique-frame, all-pairs bounded groups."""
import argparse,importlib.util,json,hashlib,subprocess,platform
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

spec=importlib.util.spec_from_file_location('e1','experiments/pointmap_refinement/E1/geometry.py');e1=importlib.util.module_from_spec(spec);spec.loader.exec_module(e1)
rec=e1.rec


def clusters(frames,edges,distance):
    n=len(frames);parent=np.arange(n);members={};accepted=0;conflict=0;clique=0
    codes=set((np.minimum(edges[:,0],edges[:,1])*n+np.maximum(edges[:,0],edges[:,1])).tolist())
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return int(i)
    for a,b in edges[np.argsort(distance,kind='stable')]:
        ra,rb=find(a),find(b)
        if ra==rb:continue
        aa=members.get(ra,[ra]);bb=members.get(rb,[rb])
        if len(set(frames[aa+bb].tolist()))!=len(aa)+len(bb):conflict+=1;continue
        if any(min(i,j)*n+max(i,j) not in codes for i in aa for j in bb):clique+=1;continue
        root,other=min(ra,rb),max(ra,rb);parent[other]=root;members[root]=sorted(aa+bb);members.pop(other,None);accepted+=1
    roots=np.array([find(i) for i in range(n)]);_,labels=np.unique(roots,return_inverse=True)
    return labels,{'accepted_unions':accepted,'rejected_frame_conflicts':conflict,'rejected_nonclique_unions':clique}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args();c=json.loads(Path('experiments/pointmap_refinement/E2/config.json').read_text())
    s=Path('results/pointmap_refinement')/a.run_id/'stages/E2';s.mkdir(parents=True,exist_ok=False)
    for n in ['logs','evaluation','artifacts/shared','artifacts/diagnostics','artifacts/renders','artifacts/source']:(s/n).mkdir(parents=True)
    (s/'manifest.json').write_text(json.dumps({'status':'running','experiment_code':'E2','run_id':a.run_id,'started_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat()}));(s/'config_resolved.json').write_text(json.dumps(c,indent=2))
    source=Path(c['parent_stage']);parent=json.loads((source/'manifest.json').read_text());assert parent['status']=='completed'
    for row in parent['artifacts']:assert rec(row['path'])==row
    with np.load(source/'artifacts/f0/observations.npz') as d:obs={key:d[key] for key in d.files}
    with np.load(source/'artifacts/f0/vggt_omega_raw.npz') as d:depth=d['depth'][0,...,0].astype('float64');confidence=d['depth_conf'][0];ks=d['intrinsics'][0].astype('float64');es=d['extrinsics'][0].astype('float64')
    x=obs['world_xyz_initial'];fid=obs['frame_id'];uv=obs['pixel_uv'];n,h,w=depth.shape;pixels=h*w;assert np.array_equal(fid,np.repeat(np.arange(n),pixels))
    median=float(np.median(depth));radius=median*c['spatial_radius_fraction_of_median_depth'];absolute=median*c['fusion_depth_absolute_fraction'];safe=np.stack([e1.edge_safe(z,c['normal_edge_relative']) for z in depth])
    maps=x.reshape(n,h,w,3);normal=np.zeros_like(maps);cross=np.cross(maps[:,1:-1,2:]-maps[:,1:-1,:-2],maps[:,2:,1:-1]-maps[:,:-2,1:-1]);length=np.linalg.norm(cross,axis=-1);normal[:,1:-1,1:-1]=cross/np.maximum(length[...,None],1e-12);norm=normal.reshape(-1,3);reliable=safe.ravel()&(np.linalg.norm(norm,axis=1)>.9)
    def project(points,frame):
        cam=points@es[frame,:,:3].T+es[frame,:,3];z=cam[:,2];q=cam@ks[frame].T
        return q[:,:2]/z[:,None],z
    edges=[];distances=[];candidate_stats=[]
    for i in range(n):
        ids=np.arange(i*pixels,(i+1)*pixels)
        for j in range(i+1,n):
            q,z=project(x[ids],j);inside=(z>0)&(q[:,0]>=0)&(q[:,0]<=w-1)&(q[:,1]>=0)&(q[:,1]<=h-1)
            ai=ids[inside];xy=np.rint(q[inside]).astype(int);bi=j*pixels+xy[:,1]*w+xy[:,0]
            back,back_z=project(x[bi],i);d=np.linalg.norm(x[ai]-x[bi],axis=1)
            masks=[reliable[ai]&reliable[bi],d<=radius,np.abs(z[inside]-depth[j,xy[:,1],xy[:,0]])<=absolute+c['fusion_depth_relative']*depth[j,xy[:,1],xy[:,0]],np.linalg.norm(back-uv[ai],axis=1)<=c['mutual_reprojection_pixels'],np.abs(back_z-depth[i].ravel()[ai-i*pixels])<=absolute+c['fusion_depth_relative']*depth[i].ravel()[ai-i*pixels],np.einsum('ij,ij->i',norm[ai],norm[bi])>=np.cos(np.deg2rad(c['normal_angle_degrees']))]
            keep=np.logical_and.reduce(masks);edges.append(np.column_stack((ai[keep],bi[keep])));distances.append(d[keep]);candidate_stats.append({'frames':[i,j],'in_frustum_candidates':len(ai),'accepted_pair_edges':int(keep.sum()),'independent_gate_pass_counts':[int(m.sum()) for m in masks]})
    edges=np.concatenate(edges);distances=np.concatenate(distances);labels,grouping=clusters(fid,edges,distances)
    count=np.bincount(labels);m=len(count);order=np.argsort(labels,kind='stable');offsets=np.r_[0,np.cumsum(count)];first=order[offsets[:-1]]
    weights=np.empty(len(x));ranges=[]
    for i in range(n):
        lo,hi=np.percentile(obs['depth_conf_raw'][fid==i],c['confidence_weight_quantiles']);weights[fid==i]=np.clip(.1+.9*(obs['depth_conf_raw'][fid==i]-lo)/max(hi-lo,1e-12),.1,1);ranges.append([float(lo),float(hi)])
    sums=np.bincount(labels,weights);xyz=np.column_stack([np.bincount(labels,weights*x[:,j])/sums for j in range(3)])
    rgb=obs['rgb'][first].astype('float64')/255
    for group_size in [2,3]:
        selected=np.flatnonzero(count==group_size);members=order[offsets[selected,None]+np.arange(group_size)[None]];rgb[selected]=np.median(obs['rgb'][members],axis=1)/255
    owner_order=np.lexsort((np.arange(len(x)),-weights,labels));owner_obs=owner_order[offsets[:-1]];owner=fid[owner_obs]
    normals=np.column_stack([np.bincount(labels,weights*norm[:,j])/sums for j in range(3)]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
    observed=np.zeros((m,n),bool);observed[labels,fid]=True;assert np.array_equal(observed.sum(1),count)
    centres=np.stack([-e[:,:3].T@e[:,3] for e in es]);angles=np.full((m,3),np.nan);col=0
    for i in range(n):
        for j in range(i+1,n):
            hit=observed[:,i]&observed[:,j];a1=xyz[hit]-centres[i];a2=xyz[hit]-centres[j];cos=(a1*a2).sum(1)/(np.linalg.norm(a1,axis=1)*np.linalg.norm(a2,axis=1));angles[hit,col]=np.rad2deg(np.arccos(np.clip(cos,-1,1)));col+=1
    multi=count>=2;parallax_max=np.zeros(m);parallax_median=np.zeros(m);parallax_max[multi]=np.nanmax(angles[multi],axis=1);parallax_median[multi]=np.nanmedian(angles[multi],axis=1)
    displacement=np.linalg.norm(x-xyz[labels],axis=1);assert displacement.max()<=radius+1e-10
    visibility=[];sweeps=[]
    for j in range(n):
        q,z=project(xyz,j);inside=(z>0)&(q[:,0]>=0)&(q[:,0]<=w-1)&(q[:,1]>=0)&(q[:,1]<=h-1);idx=np.flatnonzero(inside);xy=np.rint(q[idx]).astype(int);flat=xy[:,1]*w+xy[:,0];buf=np.full(pixels,np.inf);np.minimum.at(buf,flat,z[idx]);target=depth[j,xy[:,1],xy[:,0]];front=z[idx]<=buf[flat]*(1+c['visibility_zbuffer_relative']);valid=safe[j,xy[:,1],xy[:,0]]&(confidence[j,xy[:,1],xy[:,0]]>=np.percentile(confidence[j],c['visibility_target_confidence_quantile']))&front
        for tau in c['visibility_relative_sweep']:
            visible=np.zeros(m,bool);visible[idx]=valid&(np.abs(z[idx]-target)<=median*c['visibility_absolute_fraction']+tau*target);sweeps.append({'camera':j,'relative_threshold':tau,'visible_points':int(visible.sum())})
            if tau==c['visibility_depth_relative']:visibility.append(visible)
    visibility=np.stack(visibility,axis=1)
    payload={'xyz0':xyz,'xyz':xyz.copy(),'rgb_fixed':rgb.astype('float32'),'normal0':normals,'obs_offsets':offsets,'obs_indices':order,'obs_camera':fid[order],'obs_pixel':uv[order],'obs_depth_initial':obs['depth_initial'][order],'obs_conf_raw':obs['depth_conf_raw'][order],'original_rgb_sample_uv':obs['original_rgb_sample_uv'][order],'source_to_shared':labels,'owner_camera':owner,'owner_observation_index':owner_obs,'normalized_confidence':np.bincount(labels,weights*weights)/sums,'n_observed':count,'observed_camera_mask':observed,'parallax_max_degrees':parallax_max,'parallax_median_degrees':parallax_median,'active_candidate':multi&(parallax_max>1e-6),'visibility_estimated':visibility}
    np.savez_compressed(s/'artifacts/shared/shared_map_initial.npz',**payload)
    with np.load(s/'artifacts/shared/shared_map_initial.npz') as saved:
        for key in payload:assert np.array_equal(payload[key],saved[key])
    dt=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1'),('n_observed','u1'),('owner','<i2')]);records=np.empty(m,dt)
    for j,key in enumerate(['x','y','z']):records[key]=xyz[:,j]
    color=np.rint(rgb*255).clip(0,255).astype('uint8')
    for j,key in enumerate(['red','green','blue']):records[key]=color[:,j]
    records['n_observed']=count;records['owner']=owner
    header='ply\nformat binary_little_endian 1.0\ncomment E2 inferred shared groups; no RGB optimization; arbitrary scale\nelement vertex '+str(m)+'\nproperty double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar n_observed\nproperty short owner\nend_header\n'
    with (s/'artifacts/shared/shared_map_initial.ply').open('wb') as f:f.write(header.encode());records.tofile(f)
    np.savez_compressed(s/'artifacts/diagnostics/association.npz',edges=edges,distances=distances,source_normal=norm,source_normal_reliable=reliable,source_weights=weights)
    summary={'source_observations':len(x),'shared_points':m,'point_reduction_fraction':1-m/len(x),'groups_by_observation_count':{str(i):int((count==i).sum()) for i in [1,2,3]},'observations_in_multi_groups':int(count[multi].sum()),'spatial_radius_model_units':radius,'depth_absolute_model_units':absolute,'candidate_stats':candidate_stats,'grouping':grouping,'displacement_model_units':e1.stats(displacement),'parallax_multi_max_degrees':e1.stats(parallax_max[multi]),'visibility_sensitivity':sweeps,'visible_in_at_least_two':int((visibility.sum(1)>=2).sum()),'multi_groups_visible_in_all_source_cameras':int((multi&np.all(~observed|visibility,axis=1)).sum()),'confidence_quantile_ranges':ranges,'position_optimization':False,'fusion_performed':True,'gt_accuracy_evaluated':False}
    (s/'evaluation/fusion.json').write_text(json.dumps(summary,indent=2));(s/'environment_cpu.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,'execution_context':'host CPU','project_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()},indent=2));print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
