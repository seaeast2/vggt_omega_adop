"""Compact C1 support and normalized soft depth weighting for point diagnostics."""
import torch


def render(xyz,color,k,e,height,width,mode='compact_soft',sigma=.65,radius=2.,depth_rtol=.03,tau=.1):
    camera=xyz@e[:,:3].T+e[:,3]; z=camera[:,2]
    uv=(camera@k.T)[:,:2]/z.clamp_min(1e-8)[:,None]
    side=int(radius)
    offsets=torch.cartesian_prod(torch.arange(-side,side+1,device=xyz.device),torch.arange(-side,side+1,device=xyz.device))
    pixel=torch.floor(uv.detach()).long()[:,None,:]+offsets[None,:,:]
    distance2=((uv[:,None,:]-pixel.to(xyz.dtype))**2).sum(-1)
    valid=(z[:,None]>1e-6)&(pixel[:,:,0]>=0)&(pixel[:,:,0]<width)&(pixel[:,:,1]>=0)&(pixel[:,:,1]<height)
    compact=mode.startswith('compact_')
    if compact:valid=valid&(distance2.detach()<radius*radius)
    ids=torch.arange(len(xyz),device=xyz.device)[:,None].expand(-1,len(offsets))[valid]
    xy=pixel[valid]; flat=xy[:,1]*width+xy[:,0]; r2=distance2[valid]
    spatial=torch.exp(-r2/(2*sigma*sigma))
    if compact:spatial=spatial*(1-r2/(radius*radius)).clamp_min(0).square()
    if not len(ids):
        zero=xyz.sum()*0
        return torch.zeros((height,width,3),device=xyz.device,dtype=xyz.dtype)+zero,torch.zeros((height,width),device=xyz.device,dtype=xyz.dtype)+zero,torch.zeros((height,width),device=xyz.device,dtype=xyz.dtype)+zero
    mass=torch.zeros(height*width,device=xyz.device,dtype=xyz.dtype).scatter_add(0,flat,spatial)
    if mode=='compact_soft':
        # Detaching the normalization offset preserves the derivative of the ratio.
        log_weight=torch.log(spatial.clamp_min(torch.finfo(xyz.dtype).tiny))-z[ids]/tau
        offset=torch.full((height*width,),-float('inf'),device=xyz.device,dtype=xyz.dtype)
        offset.scatter_reduce_(0,flat,log_weight.detach(),reduce='amax',include_self=True)
        weight=torch.exp(log_weight-offset[flat])
    else:
        zmin=torch.full((height*width,),float('inf'),device=xyz.device,dtype=xyz.dtype)
        zmin.scatter_reduce_(0,flat,z[ids].detach(),reduce='amin',include_self=True)
        front=z[ids].detach()<=zmin[flat]*(1+depth_rtol)
        ids,flat,spatial=ids[front],flat[front],spatial[front]
        weight=spatial
        if not compact:mass=torch.zeros_like(mass).scatter_add(0,flat,weight)
    total=torch.zeros_like(mass).scatter_add(0,flat,weight)
    rgb=torch.zeros((height*width,3),device=xyz.device,dtype=xyz.dtype).index_add(0,flat,weight[:,None]*color[ids])
    depth=torch.zeros_like(mass).scatter_add(0,flat,weight*z[ids])
    rgb=rgb/total.clamp_min(1e-12)[:,None];depth=depth/total.clamp_min(1e-12)
    alpha=-torch.expm1(-mass)
    if mode=='legacy':rgb=rgb*alpha[:,None]
    return rgb.reshape(height,width,3),depth.reshape(height,width),alpha.reshape(height,width)
