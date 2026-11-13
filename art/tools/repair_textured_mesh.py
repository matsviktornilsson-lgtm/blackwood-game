"""Targeted Blender mesh preparation and measurable GAME diagnostics."""

import numpy as np


def clean_and_triangulate(mesh):
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        # UVs live on loops, so joining coincident vertices retains chart seams.
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1e-7)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.verts.index_update()
        seen = set()
        rejected = []
        for face in bm.faces:
            key = tuple(sorted(vertex.index for vertex in face.verts))
            if face.calc_area() <= 1e-12 or key in seen:
                rejected.append(face)
            else:
                seen.add(key)
        if rejected:
            bmesh.ops.delete(bm, geom=rejected, context="FACES")
        loose = [vertex for vertex in bm.verts if not vertex.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def triangle_data(mesh):
    mesh.calc_loop_triangles()
    points = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", points)
    faces = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", faces)
    return points.reshape(-1, 3), faces.reshape(-1, 3)


def keep_outer_shell(mesh, *, prefer_surface_area=False):
    """Retain the connected component with the largest enclosed volume."""
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        remaining = set(bm.faces)
        best, best_volume = [], -1.0
        count = 0
        while remaining:
            stack = [remaining.pop()]
            component = []
            volume = 0.0
            area = 0.0
            while stack:
                face = stack.pop()
                component.append(face)
                if prefer_surface_area:
                    area += face.calc_area()
                a = face.verts[0].co
                for index in range(1, len(face.verts) - 1):
                    volume += a.dot(face.verts[index].co.cross(face.verts[index + 1].co)) / 6
                for edge in face.edges:
                    for other in edge.link_faces:
                        if other in remaining:
                            remaining.remove(other)
                            stack.append(other)
            score = area if prefer_surface_area else abs(volume)
            if score > best_volume:
                best, best_volume = component, score
            count += 1
        if not best:
            raise ValueError("Remesh produced no outer shell.")
        keep = set(best)
        bmesh.ops.delete(bm, geom=[face for face in bm.faces if face not in keep], context="FACES")
        bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context="VERTS")
        # GPU repair can leave open boundary loops after disconnecting non-manifold edges.
        boundary = [edge for edge in bm.edges if edge.is_boundary]
        if boundary:
            filled = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)["faces"]
            if filled:
                bmesh.ops.triangulate(bm, faces=filled)
        if any(not edge.is_manifold for edge in bm.edges):
            count_invalid = sum(not edge.is_manifold for edge in bm.edges)
            raise ValueError(f"Remesh did not produce a closed outer shell ({count_invalid} non-manifold edges).")
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
        return count - 1
    finally:
        bm.free()


def unique_triangles(points, faces):
    if not len(faces):
        return False
    _, mapping = np.unique(points, axis=0, return_inverse=True)
    welded = np.sort(mapping[faces], axis=1)
    vertices = points[faces]
    area = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    return bool(np.all(np.any(area != 0, axis=1)) and len(np.unique(welded, axis=0)) == len(faces))


def compare_extremities(before, after):
    """Report lateral and vertical extremes for inspection after decimation."""
    floor, ceiling = before[:, 2].min(), before[:, 2].max()
    height = ceiling - floor
    center = (before[:, 0].min() + before[:, 0].max()) / 2
    zones = {
        "left_foot": lambda v: (v[:, 0] <= center) & (v[:, 2] <= floor + 0.16 * height),
        "right_foot": lambda v: (v[:, 0] > center) & (v[:, 2] <= floor + 0.16 * height),
        "left_arm": lambda v: (v[:, 0] <= center) & (v[:, 2] >= floor + 0.35 * height) & (v[:, 2] <= floor + 0.87 * height),
        "right_arm": lambda v: (v[:, 0] > center) & (v[:, 2] >= floor + 0.35 * height) & (v[:, 2] <= floor + 0.87 * height),
        "head": lambda v: v[:, 2] >= floor + 0.87 * height,
    }
    evidence = {}
    for name, select in zones.items():
        source, result = before[select(before)], after[select(after)]
        axis = 2 if name.endswith("foot") or name == "head" else 0
        extreme = np.min if name.endswith("foot") or name == "left_arm" else np.max
        offset = abs(float(extreme(source[:, axis]) - extreme(result[:, axis]))) if len(source) and len(result) else None
        evidence[name] = {"source_vertices": len(source), "game_vertices": len(result), "extent_delta_m": offset}
    observed = all(item["extent_delta_m"] is not None and item["extent_delta_m"] <= 0.02 * height
                   for item in evidence.values())
    return observed, evidence
