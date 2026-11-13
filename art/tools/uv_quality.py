"""Measure atlas area and UV connectivity on an exported triangle mesh."""

import json

import numpy as np

from send_to_game import PipelineError


def uv_islands(points, triangles, corners):
    if not len(triangles):
        raise PipelineError("UV_QUALITY: mesh has no triangles.")
    if not np.isfinite(corners).all():
        raise PipelineError("UV_QUALITY: atlas contains non-finite UV coordinates.")
    # A UV edge is continuous only if both positions and UVs match at both ends.
    # This welds the copies glTF exports at hard normal edges without welding UV seams.
    points_at_corners = points[triangles]
    keys = np.concatenate((points_at_corners, corners), axis=2).reshape(-1, 5)
    _, indices = np.unique(keys, axis=0, return_inverse=True)
    vertices = indices.reshape(-1, 3)
    parents = list(range(len(triangles)))

    def root(face):
        while parents[face] != face:
            parents[face] = parents[parents[face]]
            face = parents[face]
        return face

    edges = {}
    for face, (a, b, c) in enumerate(vertices.tolist()):
        for start, end in ((a, b), (b, c), (c, a)):
            if start == end:
                continue
            edge = (min(start, end), max(start, end))
            neighbor = edges.setdefault(edge, face)
            parents[root(face)] = root(neighbor)

    return np.asarray([root(face) for face in range(len(triangles))], dtype=np.int32)


def uv_quality(points, triangles, corners):
    islands = uv_islands(points, triangles, corners)
    u, v = np.diff(corners.astype(np.float64), axis=1).transpose(1, 0, 2)
    area = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]) * 0.5
    pixels = area * 2048**2
    return {
        "area_fraction": float(area.sum()),
        "median_triangle_px_at_2048": float(np.median(pixels)),
        "fraction_triangles_below_one_px": float(np.mean(pixels < 1)),
        "islands": len(np.unique(islands)),
    }


def require_uv_quality(evidence):
    if evidence["area_fraction"] <= 0:
        raise PipelineError("UV_QUALITY: atlas has no nonzero UV triangle area. " + json.dumps(evidence))
    warnings = []
    if evidence["area_fraction"] < 0.50:
        warnings.append(f"UV area is {evidence['area_fraction']:.2%} (guide: at least 50%).")
    if evidence["median_triangle_px_at_2048"] < 20:
        warnings.append(f"Median UV triangle area at 2048 is {evidence['median_triangle_px_at_2048']:.2f} px² "
                        "(guide: at least 20 px²).")
    if evidence["fraction_triangles_below_one_px"] > 0.01:
        warnings.append(f"UV triangles below 1 px² at 2048: {evidence['fraction_triangles_below_one_px']:.2%} "
                        "(guide: at most 1%).")
    if evidence["islands"] > 300:
        warnings.append(f"UV islands: {evidence['islands']:,} (guide: at most 300).")
    return warnings
