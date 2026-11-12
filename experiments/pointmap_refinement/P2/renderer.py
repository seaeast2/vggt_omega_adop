"""Minimal differentiable fixed-radius Gaussian splat in OpenCV screen coordinates.

Pixel stencils, front-layer gating and frustum selection are discrete/detached.
Gradients are local inside a fixed visibility configuration, not through topology.
"""
import torch


def render(xyz, color, k, e, height, width, sigma=.65, radius=2, depth_rtol=.03):
    cam=xyz @ e[:,:3].T+e[:,3]
    z=cam[:,2]
    uv=(cam @ k.T)[:,:2]/z.clamp_min(1e-8)[:,None]
    offsets=torch.cartesian_prod(torch.arange(-radius,radius+1,device=xyz.device),torch.arange(-radius,radius+1,device=xyz.device))
    pix=torch.floor(uv.detach()).long()[:,None,:]+offsets[None,:,:]
    valid=(z[:,None]>1e-6)&(pix[:,:,0]>=0)&(pix[:,:,0]<width)&(pix[:,:,1]>=0)&(pix[:,:,1]<height)
    ids=torch.arange(len(xyz),device=xyz.device)[:,None].expand(-1,len(offsets))[valid]
    xy=pix[valid];flat=xy[:,1]*width+xy[:,0]
    zmin=torch.full((height*width,),float('inf'),dtype=xyz.dtype,device=xyz.device)
    zmin.scatter_reduce_(0,flat,z[ids].detach(),reduce='amin',include_self=True)
    front=(z[ids].detach()<=zmin[flat]*(1+depth_rtol))
    ids=ids[front];xy=xy[front];flat=flat[front]
    weight=torch.exp(-((uv[ids]-xy.to(xyz.dtype))**2).sum(-1)/(2*sigma*sigma))
    total=torch.zeros(height*width,dtype=xyz.dtype,device=xyz.device).scatter_add(0,flat,weight)
    rgb=torch.zeros((height*width,3),dtype=xyz.dtype,device=xyz.device).index_add(0,flat,weight[:,None]*color[ids])
    depth=torch.zeros_like(total).scatter_add(0,flat,weight*z[ids])
    alpha=-torch.expm1(-total)
    rgb=rgb/total.clamp_min(1e-12)[:,None]*alpha[:,None]  # Black background, fixed RGB.
    depth=depth/total.clamp_min(1e-12)
    return rgb.reshape(height,width,3),depth.reshape(height,width),alpha.reshape(height,width)
