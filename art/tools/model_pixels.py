"""CPU orthographic projection and deterministic PNG previews."""

import struct
import zlib

import numpy as np


def png_bytes(pixels):
    height, width, channels = pixels.shape
    if channels not in (3, 4) or pixels.dtype != np.uint8:
        raise ValueError("PNG expects uint8 RGB or RGBA pixels.")

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))

    scanlines = b"".join(b"\0" + row.tobytes() for row in pixels)
    header = struct.pack(">IIBBBBB", width, height, 8, 2 if channels == 3 else 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(scanlines, 6)) + chunk(b"IEND", b"")


def raster(triangle, width, height):
    """Return covered pixels and barycentric weights at their centers."""
    start = np.maximum(np.floor(triangle.min(axis=0)).astype(int), 0)
    end = np.minimum(np.ceil(triangle.max(axis=0)).astype(int), [width, height])
    if np.any(start >= end):
        return None
    a, b, c = triangle
    u, v = b - a, c - a
    area = u[0] * v[1] - u[1] * v[0]
    if abs(area) < 1e-9:
        return None
    x = np.arange(start[0], end[0]) + 0.5 - a[0]
    y = np.arange(start[1], end[1]) + 0.5 - a[1]
    p = (x[None, :] * v[1] - y[:, None] * v[0]) / area
    q = (u[0] * y[:, None] - u[1] * x[None, :]) / area
    row, col = np.nonzero((p >= -1e-7) & (q >= -1e-7) & (p + q <= 1.0000001))
    p, q = p[row, col], q[row, col]
    return row + start[1], col + start[0], np.column_stack((1 - p - q, p, q))


def fit_frame(points, width, height, margin):
    low, high = points.min(axis=0), points.max(axis=0)
    span = high - low
    if min(span) <= 0:
        raise ValueError("Model has no projected silhouette.")
    scale = min(width / span[0], height / span[1]) * margin
    return (points - (low + high) / 2) * [scale, -scale] + [width / 2, height / 2], scale


def silhouette(screen, faces, width, height):
    """Rasterize projected triangles in pixel batches, including dense RAW meshes."""
    mask = np.zeros((height, width), dtype=bool)
    for offset in range(0, len(faces), 8192):
        triangles = screen[faces[offset:offset + 8192]]
        lo = np.clip(np.floor(triangles.min(axis=1)).astype(int), 0, [width, height])
        hi = np.clip(np.ceil(triangles.max(axis=1)).astype(int), 0, [width, height])
        extents = hi - lo
        counts = extents[:, 0] * extents[:, 1]
        for i in np.flatnonzero(counts > 65536):
            covered = raster(triangles[i], width, height)
            if covered is not None:
                mask[covered[0], covered[1]] = True
            counts[i] = 0
        ends = np.cumsum(counts)
        starts = ends - counts
        for first in range(0, int(ends[-1]), 131072):
            pixel = np.arange(first, min(first + 131072, ends[-1]))
            indices = np.searchsorted(ends, pixel, side="right")
            local = pixel - starts[indices]
            y, x = np.divmod(local, extents[indices, 0])
            x, y = x + lo[indices, 0], y + lo[indices, 1]
            a, b, c = triangles[indices].transpose(1, 0, 2)
            u, v = b - a, c - a
            dx, dy = x + 0.5 - a[:, 0], y + 0.5 - a[:, 1]
            area = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
            valid = np.abs(area) >= 1e-9
            denominator = np.where(valid, area, 1)
            p = (dx * v[:, 1] - dy * v[:, 0]) / denominator
            q = (u[:, 0] * dy - u[:, 1] * dx) / denominator
            valid &= (p >= -1e-7) & (q >= -1e-7) & (p + q <= 1.0000001)
            mask[y[valid], x[valid]] = True
    return mask


def overlap(a, b):
    union = np.count_nonzero(a | b)
    return float(np.count_nonzero(a & b) / union) if union else 0.0


def silhouette_iou(raw, raw_faces, game, game_faces, size=768):
    # Blender coordinates, Z up. Use one frame per view so lost extents still count.
    result = {}
    for name, axes in (("front", [0, 2]), ("side", [1, 2])):
        low, high = raw[:, axes].min(axis=0), raw[:, axes].max(axis=0)
        if len(game):
            low, high = np.minimum(low, game[:, axes].min(axis=0)), np.maximum(high, game[:, axes].max(axis=0))
        corners, scale = fit_frame(np.stack((low, high)), size, size, 0.94)
        origin = corners[0] - low * [scale, -scale]
        ref = raw[:, axes] * [scale, -scale] + origin
        test = game[:, axes] * [scale, -scale] + origin
        result[name] = overlap(silhouette(ref, raw_faces, size, size),
                               silhouette(test, game_faces, size, size))
    return result


def erode(mask):
    height, width = mask.shape
    padded = np.pad(mask, 1)
    return np.logical_and.reduce([padded[y:y + height, x:x + width] for y in range(3) for x in range(3)])


def contour_distances(a, b):
    def points(mask):
        return np.column_stack(np.nonzero(mask & ~erode(mask))).astype(np.float32)

    def nearest(source, target):
        return np.concatenate([
            np.min(((chunk[:, None] - target[None, :]) ** 2).sum(axis=2), axis=1)
            for chunk in np.array_split(source, (len(source) + 127) // 128)
        ])

    a, b = points(a), points(b)
    distances = np.sqrt(np.concatenate((nearest(a, b), nearest(b, a))))
    return float(np.percentile(distances, 95)), float(distances.max())


def fit_projection(xyz, faces, alpha, *, rasterize=silhouette, contours=contour_distances, choose=None):
    """Fit a uniform scale and two translations by mask IoU, then measure at native resolution."""
    height, width = alpha.shape
    mask = alpha >= 0.5
    if not mask.any() or mask.all():
        raise ValueError("Projection requires a cutout with foreground and transparent background.")
    work_scale = min(1, 384 / max(height, width))
    rows = np.minimum((np.arange(round(height * work_scale)) / work_scale).astype(int), height - 1)
    cols = np.minimum((np.arange(round(width * work_scale)) / work_scale).astype(int), width - 1)
    target = mask[np.ix_(rows, cols)]
    iy, ix = np.nonzero(target)
    if not len(ix):
        raise ValueError("Projection cutout is empty at fit resolution.")
    low, high = np.array([ix.min(), iy.min()]), np.array([ix.max(), iy.max()]) + 1
    canonical, canonical_scale = fit_frame(xyz[:, :2], 640, 640, 0.94)
    ref = rasterize(canonical, faces, 640, 640)
    sy, sx = np.nonzero(ref)
    if not len(sx):
        raise ValueError("Model has no frontal silhouette.")
    first, last = np.array([sx.min(), sy.min()]), np.array([sx.max(), sy.max()]) + 1
    ref = ref[first[1]:last[1], first[0]:last[0]]
    ref_size = last - first
    expected = min((high - low) / ref_size)
    center = (low + high) / 2
    target_area = np.count_nonzero(target)

    def score(params):
        zoom, x, y = params
        corner = np.array([x, y]) - ref_size * zoom / 2
        grid = [np.arange(int(np.floor(a)), int(np.ceil(a + n * zoom))) for a, n in zip(corner, ref_size)]
        sample = [((p + 0.5 - a) / zoom).astype(int) for p, a in zip(grid, corner)]
        sample = [np.clip(s, 0, n - 1) for s, n in zip(sample, ref_size)]
        pixels = ref[np.ix_(sample[1], sample[0])]
        valid = [(p >= 0) & (p < n) for p, n in zip(grid, target.shape[::-1])]
        intersection = np.count_nonzero(pixels[np.ix_(valid[1], valid[0])] &
                                        target[np.ix_(grid[1][valid[1]], grid[0][valid[0]])])
        return intersection / (target_area + np.count_nonzero(pixels) - intersection)

    candidates = ((expected * z, center[0] + dx * (high[0] - low[0]), center[1] + dy * (high[1] - low[1]))
                  for z in (0.72, 0.84, 0.94, 1, 1.08, 1.2, 1.36)
                  for dx in (-0.12, -0.06, 0, 0.06, 0.12)
                  for dy in (-0.12, -0.06, 0, 0.06, 0.12))
    def best_of(options):
        return choose(ref, target, list(options)) if choose is not None else max(options, key=score)

    best = best_of(candidates)
    for step in (0.04, 0.02, 0.01, 0.005, 0.0025):
        trial = ((best[0] * (1 + z * step), best[1] + dx * step * (high[0] - low[0]),
                  best[2] + dy * step * (high[1] - low[1]))
                 for z in (0, -1, 1) for dx in (0, -1, 1) for dy in (0, -1, 1))
        best = best_of(trial)
    zoom, x, y = best
    origin = np.array([x, y]) - (first + ref_size / 2) * zoom
    projected = (canonical * zoom + origin) / work_scale
    # Include out-of-frame model pixels in the union and contour measurement.
    pad_left, pad_top = np.maximum(-np.floor(projected.min(axis=0)).astype(int), 0)
    pad_right, pad_bottom = np.maximum(np.ceil(projected.max(axis=0)).astype(int) - [width, height], 0)
    reference = np.pad(mask, ((pad_top, pad_bottom), (pad_left, pad_right)))
    fitted = rasterize(projected + [pad_left, pad_top], faces, reference.shape[1], reference.shape[0])
    p95, maximum = contours(reference, fitted)
    translation = projected[0] - xyz[0, :2] * [canonical_scale * zoom / work_scale, -canonical_scale * zoom / work_scale]
    return projected, {"iou": overlap(reference, fitted), "contour_p95_px": p95, "contour_max_px": maximum,
                       "scale_px_per_m": float(canonical_scale * zoom / work_scale),
                       "translation_px": translation.tolist()}


def pad_atlas(texture, covered, seeds, radius):
    """Propagate island edge colors into unused atlas padding only."""
    height, width = covered.shape
    origin = np.full((height, width, 2), -1, dtype=np.int32)
    y, x = np.nonzero(seeds & ~erode(covered))
    origin[y, x] = np.column_stack((y, x))
    padded = np.zeros_like(covered)
    for _ in range(radius):
        if not len(y):
            break
        sources = origin[y, x]
        next_pixels = []
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1)):
            row, col = y + dy, x + dx
            valid = (row >= 0) & (row < height) & (col >= 0) & (col < width)
            row, col, seed = row[valid], col[valid], sources[valid]
            distance = (row - seed[:, 0]) ** 2 + (col - seed[:, 1]) ** 2
            valid = ~covered[row, col] & ~padded[row, col] & (distance <= radius ** 2)
            row, col, seed = row[valid], col[valid], seed[valid]
            origin[row, col] = seed
            texture[row, col, :3] = texture[seed[:, 0], seed[:, 1], :3]
            padded[row, col] = True
            next_pixels.append(np.column_stack((row, col)))
        y, x = np.concatenate(next_pixels).T
    return padded


def depth_buffer(screen, xyz, faces, size):
    depth = np.full((size, size), -np.inf, dtype=np.float32)
    for face in faces:
        covered = raster(screen[face], size, size)
        if covered is not None:
            y, x, weights = covered
            depth[y, x] = np.maximum(depth[y, x], weights @ xyz[face, 2])
    return depth


def bilinear(image, xy):
    height, width = image.shape[:2]
    x, y = np.clip(xy - 0.5, 0, [width - 1, height - 1]).T
    u, v = x.astype(int), y.astype(int)
    s, t = (x - u)[:, None], (y - v)[:, None]
    uu, vv = np.minimum(u + 1, width - 1), np.minimum(v + 1, height - 1)
    return (image[v, u] * (1 - s) + image[v, uu] * s) * (1 - t) + (image[vv, u] * (1 - s) + image[vv, uu] * s) * t


def linear(rgb):
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def srgb(rgb):
    rgb = np.clip(rgb, 0, 1)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)


def project_color(xyz, uv, faces, base, cutout, factor, depth_size=768, *, camera_xy=None):
    """Bake visible, +Z-facing color into existing texels. Preserve other texels."""
    if camera_xy is None:
        camera_xy, _ = fit_projection(xyz, faces, cutout[:, :, 3])
    cutout = cutout.copy()
    inside = cutout[:, :, 3] >= 0.5
    feather = np.zeros_like(cutout[:, :, 3])
    for _ in range(4):
        feather += inside * 0.25
        inside = erode(inside)
    cutout[:, :, 3] *= feather * feather * (3 - 2 * feather)
    screen, depth_scale = fit_frame(xyz[:, :2], depth_size, depth_size, 0.95)
    depth = depth_buffer(screen, xyz, faces, depth_size)
    output = np.array(base, copy=True)
    output[:, :, :3] = linear(base[:, :, :3]) * factor
    height, width = base.shape[:2]
    atlas = uv * [width, height]
    coverage = np.zeros((height, width), dtype=np.uint8)
    changed = np.zeros((height, width), dtype=bool)
    shared = np.zeros((height, width), dtype=bool)
    atlas_position = np.zeros((height, width, 3), dtype=np.float32)
    for face in faces:
        pixels = raster(atlas[face], width, height)
        if pixels is None:
            continue
        row, col, weights = pixels
        position = weights @ xyz[face]
        assigned = coverage[row, col] != 0
        if np.any(assigned):
            delta = position[assigned] - atlas_position[row[assigned], col[assigned]]
            shared[row[assigned], col[assigned]] |= np.linalg.norm(delta, axis=1) > 1e-4
        atlas_position[row, col] = position
        # Topologically adjacent triangles may share a one-pixel edge. A second
        # write never compounds the blend, and uncovered rear charts stay intact.
        coverage[row, col] = 1
        normal = np.cross(xyz[face[1]] - xyz[face[0]], xyz[face[2]] - xyz[face[0]])
        norm = np.linalg.norm(normal)
        if norm == 0 or normal[2] <= 0:
            continue
        sx, sy = np.clip((weights @ screen[face]).astype(int), 0, depth_size - 1).T
        visible = position[:, 2] >= depth[sy, sx] - 2.0 / depth_scale
        projected = weights @ camera_xy[face]
        h, w = cutout.shape[:2]
        visible &= (projected[:, 0] >= 0) & (projected[:, 0] < w) & (projected[:, 1] >= 0) & (projected[:, 1] < h)
        if not np.any(visible):
            continue
        color = bilinear(cutout, projected[visible])
        facing = min(normal[2] / norm / 0.7, 1.0)
        strength = facing * facing * (3 - 2 * facing)
        alpha = (color[:, 3] * strength)[:, None]
        y, x = row[visible], col[visible]
        output[y, x, :3] = linear(base[y, x, :3]) * factor * (1 - alpha) + linear(color[:, :3]) * alpha
        changed[y, x] |= alpha[:, 0] > 0.01
    output[shared, :3] = linear(base[shared, :3]) * factor
    changed &= ~shared
    if not changed.any():
        raise ValueError("Projection found no visible foreground texels.")
    covered = coverage != 0
    padding = pad_atlas(output, covered, covered & ~shared, 16)
    output[:, :, :3] = srgb(output[:, :, :3])
    if np.all(factor == 1):
        untouched = ~changed & ~padding
        output[untouched] = base[untouched]
    return np.rint(output * 255).astype(np.uint8), int(np.count_nonzero(changed))


def preview(xyz, faces, uv, base, angle, size=512):
    radians = np.deg2rad(angle)
    c, s = np.cos(radians), np.sin(radians)
    camera = xyz @ np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    screen, _ = fit_frame(camera[:, :2], size, size, 0.87)
    depth = np.full((size, size), -np.inf, dtype=np.float32)
    canvas = np.full((size, size, 3), 43, dtype=np.uint8)
    for face in faces:
        covered = raster(screen[face], size, size)
        if covered is None:
            continue
        y, x, weights = covered
        z = weights @ camera[face, 2]
        front = z > depth[y, x]
        if not np.any(front):
            continue
        y, x = y[front], x[front]
        depth[y, x] = z[front]
        normal = np.cross(camera[face[1]] - camera[face[0]], camera[face[2]] - camera[face[0]])
        light = 0.57 + 0.43 * abs(normal[2]) / max(np.linalg.norm(normal), 1e-12)
        color = np.array([165, 172, 183]) if base is None else bilinear(base, (weights[front] @ uv[face]) * base.shape[1::-1])[:, :3] * 255
        canvas[y, x] = np.rint(color * light).astype(np.uint8)
    return png_bytes(canvas)
