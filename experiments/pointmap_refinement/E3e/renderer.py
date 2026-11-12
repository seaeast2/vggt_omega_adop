"""One-pixel forward with an ADOP-style neighbor-insertion surrogate backward.

Reference: ADOP paper 3.1, original PointRenderer.cu mode 4 (ad880158).
This local fixed-RGB implementation omits the network and ghost dropout. The
surrogate is intentionally NOT the exact derivative of its discrete forward.
"""
import torch


class OnePixel(torch.autograd.Function):
    @staticmethod
    def forward(ctx, uv, z, color, height, width, tolerance, border):
        valid = torch.isfinite(uv).all(1) & torch.isfinite(z) & (z > 1e-6)
        pixels = torch.floor(torch.nan_to_num(uv.detach())+.5).long()
        valid &= (pixels[:, 0] >= 0) & (pixels[:, 0] < width) & (pixels[:, 1] >= 0) & (pixels[:, 1] < height)
        ids = torch.nonzero(valid, as_tuple=True)[0]; flat = pixels[ids, 1]*width+pixels[ids, 0]
        depth = torch.full((height*width,), float('inf'), device=z.device, dtype=z.dtype)
        depth.scatter_reduce_(0, flat, z[ids], reduce='amin', include_self=True)
        accepted = z[ids] <= depth[flat]*(1+tolerance); ids = ids[accepted]; flat = flat[accepted]
        count = torch.zeros_like(depth).scatter_add_(0, flat, torch.ones_like(z[ids]))
        image = torch.zeros((height*width, 3), device=color.device, dtype=color.dtype)
        image.index_add_(0, flat, color[ids]); image /= count.clamp_min(1)[:, None]
        ctx.height = height; ctx.width = width; ctx.tolerance = tolerance; ctx.border = border
        ctx.save_for_backward(uv, z, color, pixels, ids, image, depth, count)
        depth_out = torch.where(count > 0, depth, torch.zeros_like(depth)).reshape(height, width)
        count_out = count.reshape(height, width)
        ctx.mark_non_differentiable(depth_out, count_out)
        return image.reshape(height, width, 3), depth_out, count_out

    @staticmethod
    def backward(ctx, grad_image, grad_depth, grad_count):
        uv, z, color, pixels, ids, image, depth, count = ctx.saved_tensors
        width, height, border = ctx.width, ctx.height, ctx.border
        pos = pixels[ids]
        inside = ((pos[:, 0] > border) & (pos[:, 0] < width-1-border) &
                  (pos[:, 1] > border) & (pos[:, 1] < height-1-border))
        ids = ids[inside]; pos = pixels[ids]; incoming = grad_image.reshape(-1, 3)
        grad_uv = torch.zeros_like(uv)
        # Same signs, fuzzy cases, symmetric factor and channel averaging as
        # official mode 4; center-pixel removal is not modeled by this surrogate.
        for axis in range(2):
            total = torch.zeros(len(ids), device=z.device, dtype=z.dtype)
            for sign in [-1, 1]:
                offset = pos.clone(); offset[:, axis] += sign; flat = offset[:, 1]*width+offset[:, 0]
                w = count[flat]; d = depth[flat]
                override = (w == 0) | (z[ids]*(1+ctx.tolerance) < d)
                behind = (w > 0) & (z[ids] > d*(1+ctx.tolerance))
                change = (color[ids]-image[flat])/(w+1)[:, None]
                change = torch.where(override[:, None], color[ids]-image[flat], change)
                change = torch.where(behind[:, None], torch.zeros_like(change), change)
                total += .5*sign*(change*incoming[flat]).sum(1)/color.shape[1]
            grad_uv[ids, axis] = total
        return grad_uv, None, None, None, None, None, None


def render(xyz, color, k, e, height, width, tolerance=.01, border=2):
    camera = xyz@e[:, :3].T+e[:, 3]; z = camera[:, 2]
    uv = (camera@k.T)[:, :2]/z.clamp_min(1e-8)[:, None]
    return OnePixel.apply(uv, z, color.detach(), height, width, tolerance, border)


def controlled_checks(device='cuda'):
    def t(value, grad=False): return torch.tensor(value, device=device, dtype=torch.float64, requires_grad=grad)
    k = t([[1, 0, 0], [0, 1, 0], [0, 0, 1]]); e = t([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]])
    uv = t([[4.1, 4.2], [4.2, 4.1], [4, 4], [-1, 0]])
    color = t([[1, 0, 0], [0, 0, 1], [0, 1, 0], [1, 1, 1]])
    image, depth, count = OnePixel.apply(uv, t([1, 1.005, 2, 1]), color, 12, 12, .01, 2)
    assert int((count > 0).sum()) == 1 and float(count[4, 4]) == 2
    assert torch.equal(image[4, 4], t([.5, 0, .5])) and float(depth[4, 4]) == 1
    # A ghost insertion into a right neighbor: front overwrites, behind has zero
    # influence, near-depth averages. An independent scalar formula checks sign
    # and magnitude using a one-pixel loss gradient of [1,0,0].
    cases = []
    for neighbor_z, expected in [(2., 1/6), (.5, 0.), (1.005, 1/12)]:
        q = t([[4., 4.], [5., 4.]], True); colors = t([[1, 0, 0], [0, 0, 1]])
        rgb, _, _ = OnePixel.apply(q, t([1, neighbor_z]), colors, 12, 12, .01, 2)
        rgb[4, 5, 0].backward(); actual = float(q.grad[0, 0])
        assert abs(actual-expected) < 1e-12
        cases.append({'neighbor_Z': neighbor_z, 'expected_du': expected, 'actual_du': actual})
    # Chain rule: a front red point at (x,y,z) projects to (x/z,y/z),
    # so the scalar x loss must return (1/6)/z and z loss -x/(6*z^2).
    xyz = t([[8, 8, 2], [15, 12, 3]], True)
    rgb, _, _ = render(xyz, t([[1, 0, 0], [0, 0, 1]]), k, e, 12, 12)
    rgb[4, 5, 0].backward()
    assert abs(float(xyz.grad[0, 0])-1/12) < 1e-12
    assert abs(float(xyz.grad[0, 2])+1/3) < 1e-12
    return {'one_pixel_no_spatial_spread': True, 'fuzzy_1_percent_and_near_mean': True,
            'far_depth_and_outside_rejected': True, 'neighbor_insertion_cases': cases,
            'perspective_chain_rule': True, 'fixed_color_no_gradient': True,
            'infinitesimal_forward_finite_difference_not_a_surrogate_validity_test': True}
