"""CUDA depth and UV rasterizer for the Blackwood ortho projector."""

import argparse
import json

import numpy as np
import torch
from scipy.ndimage import distance_transform_edt, find_objects
from torch.nn.functional import grid_sample, max_pool2d, pad

from model_pixels import fit_frame, fit_projection, png_bytes
from probe_torch_gpu import cuda_4090


def fragments(triangles, width, height):
    bounds = triangles.new_tensor([width, height])
    lo = torch.minimum(triangles.amin(1).floor().clamp_min(0), bounds).long()
    hi = torch.minimum(triangles.amax(1).ceil().clamp_min(0), bounds).long()
    extents = hi - lo
    counts = extents.prod(1)
    ends = counts.cumsum(0)
    starts = ends - counts
    total = int(ends[-1]) if len(ends) else 0
    for first in range(0, total, 262144):
        pixels = torch.arange(first, min(first + 262144, total), device=triangles.device)
        face = torch.searchsorted(ends, pixels, right=True)
        local = pixels - starts[face]
        step = extents[face, 0]
        x = local.remainder(step) + lo[face, 0]
        y = torch.div(local, step, rounding_mode="floor") + lo[face, 1]
        a, b, c = triangles[face].unbind(1)
        u, v = b - a, c - a
        dx, dy = x + 0.5 - a[:, 0], y + 0.5 - a[:, 1]
        area = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
        valid = area.abs() >= 1e-9
        denominator = torch.where(valid, area, 1)
        p = (dx * v[:, 1] - dy * v[:, 0]) / denominator
        q = (u[:, 0] * dy - u[:, 1] * dx) / denominator
        valid &= (p >= -1e-7) & (q >= -1e-7) & (p + q <= 1.0000001)
        yield (y * width + x)[valid], face[valid], torch.stack((1 - p - q, p, q), 1)[valid]


def erode(mask):
    return max_pool2d(pad((~mask)[None, None].float(), (1, 1, 1, 1), value=1), 3, stride=1)[0, 0] == 0


def cuda_mask(screen, faces, width, height):
    result = torch.zeros(width * height, dtype=torch.bool, device=screen.device)
    for pixels, _, _ in fragments(screen[faces], width, height):
        result[pixels] = True
    return result.reshape(height, width)


def cuda_contours(first, second):
    def edges(mask):
        return (mask & ~erode(mask)).nonzero().float()

    a, b = edges(first), edges(second)
    distances = torch.cat([torch.cdist(part, target).amin(1) for source, target in ((a, b), (b, a))
                           for part in source.split(256)])
    return float(torch.quantile(distances, 0.95)), float(distances.max())


def cuda_choose(reference, target, candidates, device):
    ref = torch.as_tensor(reference, device=device, dtype=torch.float32)
    goal = torch.as_tensor(target, device=device, dtype=torch.bool)
    target_area = goal.sum()
    params = torch.as_tensor(candidates, device=device, dtype=torch.float32)
    dims = params.new_tensor([ref.shape[1], ref.shape[0]])
    scores = []
    for options in params.split(12):
        zoom, center = options[:, :1], options[:, 1:]
        corner = center - zoom * dims / 2
        stop = corner + zoom * dims
        x0, y0 = corner.amin(0).floor().int().tolist()
        x1, y1 = stop.amax(0).ceil().int().tolist()
        y, x = torch.meshgrid(torch.arange(y0, y1, device=device), torch.arange(x0, x1, device=device), indexing="ij")
        coordinates = torch.stack((x + 0.5, y + 0.5), -1)
        grid = 2 * (coordinates[None] - corner[:, None, None]) / (zoom * dims)[:, None, None] - 1
        raster = grid_sample(ref[None, None].expand(len(options), -1, -1, -1), grid, mode="nearest",
                             padding_mode="zeros", align_corners=False)[:, 0].bool()
        valid = (y >= 0) & (x >= 0) & (y < goal.shape[0]) & (x < goal.shape[1])
        intersection = (raster[:, valid] & goal[y[valid], x[valid]]).sum(1)
        scores.append(intersection / (target_area + raster.sum((1, 2)) - intersection))
    return candidates[int(torch.cat(scores).argmax())]


def linear(rgb):
    return torch.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055).pow(2.4))


def srgb(rgb):
    rgb = rgb.clamp(0, 1)
    return torch.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb.pow(1 / 2.4) - 0.055)


def atlas_padding(color, covered, seeds, radius=16):
    height, width = covered.shape
    seed = torch.full((height, width), -1, dtype=torch.long, device=color.device)
    yy, xx = (seeds & ~erode(covered)).nonzero(as_tuple=True)
    seed[yy, xx] = yy * width + xx
    frontier = seed >= 0
    padded = torch.zeros_like(covered)
    for _ in range(radius):
        rows, cols = frontier.nonzero(as_tuple=True)
        if not rows.numel():
            break
        sources = seed[rows, cols]
        frontier.zero_()
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            y, x = rows + dy, cols + dx
            valid = (y >= 0) & (y < height) & (x >= 0) & (x < width)
            y, x, s = y[valid], x[valid], sources[valid]
            origin_y, origin_x = torch.div(s, width, rounding_mode="floor"), s.remainder(width)
            valid = ~covered[y, x] & ~padded[y, x] & ((y - origin_y).square() + (x - origin_x).square() <= radius ** 2)
            y, x, s = y[valid], x[valid], s[valid]
            seed[y, x] = s
            padded[y, x] = frontier[y, x] = True
    y, x = padded.nonzero(as_tuple=True)
    s = seed[y, x]
    color[y, x, :3] = color[torch.div(s, width, rounding_mode="floor"), s.remainder(width), :3]
    return padded


def fill_atlas_holes(image, valid, labels):
    """Copy the nearest valid RGB within each island, leaving other texels alone."""
    filled = np.zeros_like(valid)
    for island, region in enumerate(find_objects(labels), 1):
        if region is None:
            continue
        inside = labels[region] == island
        seeds = inside & valid[region]
        holes = inside & ~valid[region]
        if not seeds.any() or not holes.any():
            continue
        nearest = distance_transform_edt(~seeds, return_distances=False, return_indices=True)
        colors = image[region]
        colors[holes, :3] = colors[tuple(nearest[:, holes])][:, :3]
        filled[region] |= holes
    return filled


def project(xyz, faces, uv, base, cutout, factor, screen, depth_scale, camera, depth_size=768, *,
            bake_valid=None, islands=None, fill_report=None):
    depth = torch.full((depth_size ** 2,), -torch.inf, device=xyz.device)
    for pixels, face, bary in fragments(screen[faces], depth_size, depth_size):
        z = (bary * xyz[faces[face], 2]).sum(1)
        depth.scatter_reduce_(0, pixels, z, "amax")
    inside = cutout[:, :, 3] >= 0.5
    feather = torch.zeros_like(cutout[:, :, 3])
    for _ in range(4):
        feather += inside * 0.25
        inside = erode(inside)
    cutout = cutout.clone()
    cutout[:, :, 3] *= feather.square() * (3 - 2 * feather)
    height, width = base.shape[:2]
    size = height * width
    atlas = (uv * uv.new_tensor([width, height]))[faces]
    if bake_valid is not None:
        labels = torch.zeros(size, dtype=torch.int32, device=xyz.device)
        for pixel, face, _ in fragments(atlas, width, height):
            labels.scatter_reduce_(0, pixel, islands[face], "amax")
        labels = labels.reshape(height, width).cpu().numpy()
    lower = torch.full((size, 3), torch.inf, device=xyz.device)
    upper = torch.full_like(lower, -torch.inf)
    winner = torch.full((size,), -1, dtype=torch.long, device=xyz.device)
    front_texels = torch.zeros(size, dtype=torch.bool, device=xyz.device)
    verts = xyz[faces]
    normals = torch.linalg.cross(verts[:, 1] - verts[:, 0], verts[:, 2] - verts[:, 0])
    facing = (normals[:, 2] / normals.norm(dim=1).clamp_min(1e-12) / 0.7).clamp(0, 1)

    def interpolate(values, face, bary):
        return (values[faces[face]] * bary[:, :, None]).sum(1)

    for pixel, face, bary in fragments(atlas, width, height):
        pos = interpolate(xyz, face, bary)
        index = pixel[:, None].expand(-1, 3)
        lower.scatter_reduce_(0, index, pos, "amin")
        upper.scatter_reduce_(0, index, pos, "amax")
        sx, sy = interpolate(screen, face, bary).long().clamp(0, depth_size - 1).unbind(1)
        image_xy = interpolate(camera, face, bary)
        h, w = cutout.shape[:2]
        front_texels[pixel[facing[face] > 0]] = True
        valid = ((facing[face] > 0) & (pos[:, 2] >= depth[sy * depth_size + sx] - 2 / depth_scale)
                 & (image_xy[:, 0] >= 0) & (image_xy[:, 0] < w) & (image_xy[:, 1] >= 0) & (image_xy[:, 1] < h))
        winner.scatter_reduce_(0, pixel[valid], face[valid], "amax")
    covered = lower[:, 0].isfinite()
    shared = covered & ((upper - lower).norm(dim=1) > 1e-4)
    winner[shared] = -1
    if bake_valid is not None:
        labels[shared.reshape(height, width).cpu().numpy()] = 0
        pixels = base.cpu().numpy().copy()
        filled = fill_atlas_holes(pixels, bake_valid, labels)
        bake_valid = bake_valid | filled
        base = torch.as_tensor(pixels, device=xyz.device)
        fill_report["after_bake_texels"] = int(filled.sum())
    eligible_count = int((winner >= 0).sum())
    color = base.clone().reshape(size, 4)
    color[:, :3] = linear(color[:, :3]) * factor
    changed = torch.zeros(size, dtype=torch.bool, device=xyz.device)
    painted = torch.zeros_like(changed) if bake_valid is not None else None
    cutout_channels = cutout.permute(2, 0, 1)[None]
    for pixel, face, bary in fragments(atlas, width, height):
        use = winner[pixel] == face
        pixel, face, bary = pixel[use], face[use], bary[use]
        if not pixel.numel():
            continue
        image_xy = interpolate(camera, face, bary)
        grid = (2 * image_xy / image_xy.new_tensor([cutout.shape[1], cutout.shape[0]]) - 1).reshape(1, 1, -1, 2)
        projected = grid_sample(cutout_channels, grid, padding_mode="border", align_corners=False)[0, :, 0].T
        weight = facing[face]
        opacity = (projected[:, 3] * weight.square() * (3 - 2 * weight))[:, None]
        original = color[pixel, :3]
        blended = original * (1 - opacity) + linear(projected[:, :3]) * opacity
        color[pixel, :3] = blended
        # Count a texel only when projection actually changes its exported RGB.
        changed[pixel] = (srgb(blended).mul(255).round() != srgb(original).mul(255).round()).any(dim=1)
        if painted is not None:
            painted[pixel] = opacity[:, 0] > 0.01
    image = color.reshape(height, width, 4)
    projected_count = int(changed.sum())
    if painted is not None:
        pixels = image.cpu().numpy().copy()
        filled = fill_atlas_holes(pixels, bake_valid | painted.reshape(height, width).cpu().numpy(), labels)
        image = torch.as_tensor(pixels, device=xyz.device)
        changed |= torch.as_tensor(filled.ravel(), device=xyz.device)
        fill_report["after_projection_texels"] = int(filled.sum())
    padding = atlas_padding(image, covered.reshape(height, width), (covered & ~shared).reshape(height, width))
    image[:, :, :3] = srgb(image[:, :, :3])
    if bool((factor == 1).all()):
        untouched = ~changed.reshape(height, width) & ~padding
        image[untouched] = base[untouched]
    return image.mul(255).round().to(torch.uint8), projected_count, int(front_texels.sum()), eligible_count


def projection_coverage(count, front_count):
    fraction = count / front_count if front_count else 0
    summary = f"PROJECTION_COVERAGE: {count}/{front_count} ({fraction:.2%})"
    if fraction < 0.20:
        raise ValueError(f"{summary}; minimum is 20%")
    warnings = [f"{summary}; below the 50% guideline"] if fraction < 0.50 else []
    return fraction, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs")
    parser.add_argument("output")
    parser.add_argument("report")
    parser.add_argument("--fill-holes", action="store_true")
    args = parser.parse_args()
    device = cuda_4090()
    torch.cuda.reset_peak_memory_stats(device)
    with np.load(args.inputs, allow_pickle=False) as data, torch.inference_mode():
        xyz, faces = data["xyz"], data["faces"]
        def tensor(array):
            return torch.as_tensor(array, device=device, dtype=torch.float32)
        gpu_faces = torch.as_tensor(faces, device=device, dtype=torch.long)
        camera, alignment = fit_projection(
            xyz, faces, data["cutout"][:, :, 3],
            rasterize=lambda points, _, width, height: cuda_mask(tensor(points), gpu_faces, width, height).cpu().numpy(),
            contours=lambda a, b: cuda_contours(tensor(a).bool(), tensor(b).bool()),
            choose=lambda ref, target, candidates: cuda_choose(ref, target, candidates, device),
        )
        screen, scale = fit_frame(xyz[:, :2], 768, 768, 0.95)
        fill_report = {"enabled": args.fill_holes}
        options = {}
        if args.fill_holes:
            options = {"bake_valid": data["bake_valid"], "islands": tensor(data["islands"]).to(torch.int32),
                       "fill_report": fill_report}
        pixels, count, front_count, eligible_count = project(
            tensor(xyz), gpu_faces, tensor(data["uv"]), tensor(data["base"]), tensor(data["cutout"]),
            tensor(data["factor"]), tensor(screen), scale, tensor(camera), **options)
        print(f"Projection IoU {alignment['iou']:.4f}. Coverage: {count:,}/{front_count:,} "
              f"front-facing texels. {eligible_count:,} pass depth, bounds and shared-UV checks.",
              flush=True)
        fraction, warnings = projection_coverage(count, front_count)
        with open(args.output, "xb") as output:
            output.write(png_bytes(pixels.cpu().numpy()))
    with open(args.report, "x", encoding="utf-8") as report:
        json.dump({"device": f"CUDA: {torch.cuda.get_device_name(device)}", "alignment": alignment,
                   "projected_texels": count, "front_facing_texels": front_count, "projected_fraction": fraction,
                   "eligible_texels": eligible_count,
                   "hole_fill": fill_report,
                   "warnings": warnings,
                   "torch_vram_peak_mib": round(torch.cuda.max_memory_allocated(device) / 2 ** 20, 1)}, report)


if __name__ == "__main__":
    main()
