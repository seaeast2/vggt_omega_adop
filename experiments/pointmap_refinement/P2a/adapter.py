"""OpenCV integer-pixel -> PyTorch3D rasterizer NDC adapter; float32 CUDA."""
import torch
from pytorch3d.structures import Pointclouds
from pytorch3d.renderer.points.rasterize_points import rasterize_points
from pytorch3d.renderer.compositing import alpha_composite


def render(xyz,color,k,e,height,width,mode='standard',points_per_pixel=16,radius_pixels=2.,depth_rtol=.03,bin_size=0):
    camera=xyz@e[:,:3].T+e[:,3]
    z=camera[:,2];uv=(camera@k.T)[:,:2]/z.clamp_min(1e-8)[:,None]
    # Pixel (0,0) is the top-left centre; PyTorch3D +X/+Y point left/up.
    size=min(height,width)
    ndc=torch.stack(((width-1-2*uv[:,0])/size,(height-1-2*uv[:,1])/size,z),dim=1)
    radius=radius_pixels*2/size
    ids,zbuf,dists=rasterize_points(Pointclouds(points=[ndc]),image_size=(height,width),radius=radius,points_per_pixel=points_per_pixel,bin_size=bin_size)
    valid=ids>=0
    if mode=='standard':
        weights=(1-dists/(radius*radius)).clamp(0,1)*valid
        features=torch.cat((color,torch.ones_like(z[:,None]),z[:,None]),dim=1).T.contiguous()
        image=alpha_composite(ids.permute(0,3,1,2).long(),weights.permute(0,3,1,2),features)[0].permute(1,2,0)
        alpha=image[...,3];depth=image[...,4]/alpha.clamp_min(1e-12)
        return image[...,:3],depth,alpha
    # P2-like weights/composition; top-K and circular footprint remain different.
    valid=valid&(zbuf<=zbuf[...,:1]*(1+depth_rtol))
    weights=torch.exp(-dists.clamp_min(0)*(size/2)**2/(2*.65**2))*valid
    total=weights.sum(-1)[0];alpha=-torch.expm1(-total)
    rgb=(weights[...,None]*color[ids.clamp_min(0)]).sum(-2)[0]/total.clamp_min(1e-12)[...,None]*alpha[...,None]
    depth=(weights*zbuf).sum(-1)[0]/total.clamp_min(1e-12)
    return rgb,depth,alpha
