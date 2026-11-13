"""Build a textured 2.2 m GAME GLB from an immutable RAW in Windows Blender."""

import math
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import numpy as np
from mathutils import Vector

from blender_model import blender_args, configure_cycles, render_mesh_previews, static_mesh
from gpu_runtime import CPU_ONLY, GPU_NAME
from model_glb import read_glb, view_bytes
from model_pixels import silhouette_iou
from repair_textured_mesh import clean_and_triangulate, compare_extremities, keep_outer_shell, triangle_data, unique_triangles
from send_to_game import PipelineError, write_json
from uv_quality import require_uv_quality, uv_quality

TRIANGLE_TARGET = 40_000
HEIGHT_M = 2.2
VOXEL_M = 0.004
VOXEL_ADAPTIVITY = 0.15
MIN_SILHOUETTE_IOU = 0.95
SMOOTH_ANGLE_DEGREES = 80


def select(model, *others):
    bpy.ops.object.select_all(action="DESELECT")
    for item in (model, *others):
        item.select_set(True)
    bpy.context.view_layer.objects.active = model


def copy_model(source):
    model = source.copy()
    model.data = source.data.copy()
    bpy.context.collection.objects.link(model)
    return model


def normalize(points):
    low, high = points.min(axis=0), points.max(axis=0)
    height = high[2] - low[2]
    if not np.isfinite(points).all() or height <= 0:
        raise PipelineError("GAME_BOUNDS: invalid bounds or empty height.")
    center = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]])
    return ((points - center) * (HEIGHT_M / height)).astype(np.float32)


def set_points(model, points):
    model.data.vertices.foreach_set("co", points.ravel())
    model.data.update()


def smooth_by_angle(mesh):
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.normal_update()
        limit = math.radians(SMOOTH_ANGLE_DEGREES)
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = edge.is_manifold and edge.calc_face_angle() < limit
        sharp_edges = sum(not edge.smooth for edge in bm.edges)
        bm.to_mesh(mesh)
        mesh.update()
        return sharp_edges
    finally:
        bm.free()


def decimate(model):
    select(model)
    points, faces = triangle_data(model.data)
    for _ in range(3):
        count = len(faces)
        if count <= TRIANGLE_TARGET:
            break
        modifier = model.modifiers.new("Blackwood GAME triangle target", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = TRIANGLE_TARGET / count
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        clean_and_triangulate(model.data)
        points, faces = triangle_data(model.data)
        print(f"GAME collapse: {count:,} -> {len(faces):,} triangles.", flush=True)
        if len(faces) >= count:
            break
    return points, faces


def inspect(before, raw_faces, points, faces):
    unique = unique_triangles(points, faces)
    extremities, extents = compare_extremities(before, points) if len(points) else (False, {})
    iou = silhouette_iou(before, raw_faces, points, faces)
    return {"unique_triangles": unique, "extremities_present": extremities, "extremity_probes": extents,
            "triangles": len(faces), "silhouette_iou": iou,
            "accepted": (unique and extremities and min(iou.values()) >= MIN_SILHOUETTE_IOU
                         and len(faces) <= 1.1 * TRIANGLE_TARGET)}


def cumesh_transform(model, worker, directory, site_packages, *, simplify=None, unwrap=False, repair_shell=False):
    if not worker:
        return False
    points, faces = triangle_data(model.data)
    with tempfile.TemporaryDirectory(prefix=".blackwood-cumesh-", dir=directory) as temporary:
        source, output = (Path(temporary) / name for name in ("source.npz", "shell.npz"))
        np.savez(source, points=points, faces=faces)
        command = [str(worker), "-B", "-X", "utf8", str(Path(__file__).with_name("remesh_cumesh.py")),
                   str(source), str(output)]
        if site_packages:
            command.extend(("--site-packages", str(site_packages)))
        if simplify:
            command.extend(("--simplify", str(simplify)))
        if unwrap:
            command.append("--unwrap")
        if repair_shell:
            command.append("--repair-shell")
        process = subprocess.run(command, check=False)
        if process.returncode == 3 and not site_packages:
            return False
        if process.returncode:
            raise PipelineError(f"CUMESH_FAILED: worker exited {process.returncode}. See CUDA diagnostics in the log.")
        with np.load(output, allow_pickle=False) as result:
            if unwrap:
                apply_atlas(model.data, faces, result["faces"], result["uv"])
                return True
            mesh = bpy.data.meshes.new("CuMesh result")
            mesh.from_pydata(result["points"].tolist(), [], result["faces"].tolist())
            mesh.update()
        model.data = mesh
        return True


def apply_atlas(mesh, faces, atlas_faces, atlas_uv):
    # Transfer chart UVs back to mesh loops so UV seams don't split smoothing groups.
    def canonical(indices):
        order = np.argsort(indices, axis=1)
        keys = np.take_along_axis(indices, order, axis=1)
        return order, keys, np.lexsort(keys.T)

    mesh_order, mesh_keys, mesh_rows = canonical(faces)
    atlas_order, atlas_keys, atlas_rows = canonical(atlas_faces)
    if not np.array_equal(mesh_keys[mesh_rows], atlas_keys[atlas_rows]):
        raise PipelineError("UV_TOPOLOGY: xatlas changed the source triangles.")
    loops = np.empty(faces.size, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    target = np.take_along_axis(loops.reshape(-1, 3), mesh_order, axis=1)[mesh_rows]
    coordinates = np.empty((len(mesh.loops), 2), dtype=np.float32)
    coordinates[target] = atlas_uv[atlas_rows[:, None], atlas_order[atlas_rows]]
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", coordinates.ravel())


def remesh_shell(model, worker, directory, site_packages, *, voxel=False):
    clean_and_triangulate(model.data)
    if not voxel and cumesh_transform(model, worker, directory, site_packages):
        return "cumesh_remesh", None
    select(model)
    model.data.remesh_voxel_size = VOXEL_M
    model.data.remesh_voxel_adaptivity = VOXEL_ADAPTIVITY
    model.data.use_remesh_preserve_volume = True
    bpy.ops.object.voxel_remesh()
    return "blender_voxel_remesh", "Explicit 4 mm voxel shell" if voxel else "CuMesh unavailable"


def unwrap_atlas(model, points, faces, cu_args, *, use_xatlas=True):
    while model.data.uv_layers:
        model.data.uv_layers.remove(model.data.uv_layers[0])
    if use_xatlas and cumesh_transform(model, *cu_args, unwrap=True):
        method = "xatlas charts and packing (CPU)"
        evidence = measure_atlas(model.data, points, faces)
        if evidence["area_fraction"] > 0:
            return method, evidence
        print("xatlas returned zero UV area; retrying with Blender Smart UV Project.", flush=True)
        model.data.uv_layers.remove(model.data.uv_layers.active)
    select(model)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003, margin_method="FRACTION")
    bpy.ops.uv.pack_islands(margin=0.003, margin_method="FRACTION")
    bpy.ops.object.mode_set(mode="OBJECT")
    return "Blender Smart UV Project (CPU)", measure_atlas(model.data, points, faces)


def measure_atlas(mesh, points, faces):
    coordinates = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    mesh.uv_layers.active.data.foreach_get("uv", coordinates)
    corners = np.empty(len(faces) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", corners)
    return uv_quality(points, faces, coordinates.reshape(-1, 2)[corners.reshape(-1, 3)])


def bake_diffuse(source, target, device, mask_path=None):
    # Use the imported Base Color as diffuse color, even on metallic source regions.
    material = source.data.materials[0].copy()
    source.data.materials[0] = material
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output)
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    base = shader.inputs["Base Color"]
    diffuse.inputs["Color"].default_value = base.default_value
    if base.is_linked:
        links.new(base.links[0].from_socket, diffuse.inputs["Color"])
    links.new(diffuse.outputs[0], output.inputs["Surface"])

    target.data.materials.clear()
    material = bpy.data.materials.new("Blackwood baked RAW color")
    material.use_nodes = True
    target.data.materials.append(material)
    nodes = material.node_tree.nodes
    image = bpy.data.images.new("Blackwood RAW base color", width=2048, height=2048, alpha=False)
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    nodes.active = texture
    select(target, source)
    settings = {"cage_extrusion": 0.012, "max_ray_distance": 0.024}
    result = bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=True,
                                 use_cage=True, margin=16, **settings)
    if "FINISHED" not in result:
        raise PipelineError("GAME_BAKE: Blender did not finish the selected-to-active diffuse bake.")
    image.pack()
    if mask_path:
        mask = bpy.data.images.new("Blackwood bake coverage", width=2048, height=2048, alpha=False)
        texture.image = mask
        source_emission = source.data.materials[0].node_tree.nodes.new("ShaderNodeEmission")
        source_emission.inputs["Color"].default_value = (1, 1, 1, 1)
        links.new(source_emission.outputs[0], output.inputs["Surface"])
        if "FINISHED" not in bpy.ops.object.bake(type="EMIT", use_selected_to_active=True,
                                                use_cage=True, margin=0, **settings):
            raise PipelineError("GAME_BAKE: could not bake the coverage mask.")
        mask.filepath_raw = str(mask_path)
        mask.file_format = "PNG"
        mask.save()
        texture.image = image
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Metallic"].default_value = 0
    material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    return settings | {"device": device}


def main():
    args = blender_args(__doc__, ["raw"], ["trellis-python", "cumesh-site-packages", "bake-mask"],
                        flags=["remesh"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    device = configure_cycles()
    bpy.ops.import_scene.gltf(filepath=str(args.raw))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1 or meshes[0].parent or len(meshes[0].data.materials) != 1:
        raise PipelineError("RAW_LAYOUT: expected a single unparented textured mesh.")
    source = meshes[0]
    if not source.data.uv_layers or source.data.shape_keys:
        raise PipelineError("RAW_UV: expected a static textured atlas.")
    select(source)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    points, raw_faces = triangle_data(source.data)
    if not len(raw_faces):
        raise PipelineError("RAW_GEOMETRY: empty mesh.")
    before = normalize(points)
    set_points(source, before)
    model = copy_model(source)
    clean_and_triangulate(model.data)
    cu_args = (args.trellis_python, args.output.parent, args.cumesh_site_packages)
    use_cumesh = not args.remesh and cumesh_transform(model, *cu_args, simplify=TRIANGLE_TARGET)
    if args.remesh:
        after, faces = before, raw_faces
    elif use_cumesh:
        clean_and_triangulate(model.data)
        after, faces = triangle_data(model.data)
    else:
        after, faces = decimate(model)
    collapse = inspect(before, raw_faces, after, faces)
    if args.remesh:
        collapse["accepted"] = False
    method = "cumesh_collapse" if use_cumesh else "collapse"
    print(f"GAME {method}: {len(faces):,} triangles, silhouette {collapse['silhouette_iou']}, "
          f"extremities {collapse['extremities_present']}, accepted {collapse['accepted']}.", flush=True)
    fallback = {}
    if use_cumesh and not collapse["accepted"]:
        # Retain more geometry before trying a remesh when the first collapse loses the silhouette.
        for target in (60_000, 140_000, 220_000):
            candidate = copy_model(source)
            clean_and_triangulate(candidate.data)
            cumesh_transform(candidate, *cu_args, simplify=target)
            clean_and_triangulate(candidate.data)
            candidate_points, candidate_faces = triangle_data(candidate.data)
            checked = inspect(before, raw_faces, candidate_points, candidate_faces)
            print(f"GAME collapse retry at {target:,}: {checked['triangles']:,} triangles, "
                  f"silhouette {checked['silhouette_iou']}, unique {checked['unique_triangles']}, "
                  f"extremities {checked['extremities_present']}.", flush=True)
            if (checked["unique_triangles"] and checked["extremities_present"]
                    and min(checked["silhouette_iou"].values()) >= 0.90):
                bpy.data.objects.remove(model, do_unlink=True)
                model, after, faces = candidate, candidate_points, candidate_faces
                fallback["collapse_retry"] = {"target": target, "initial_check": collapse}
                collapse = checked | {"accepted": True}
                break
            bpy.data.objects.remove(candidate, do_unlink=True)
    if collapse["accepted"] and use_cumesh:
        unwrap, atlas_quality = unwrap_atlas(model, after, faces, cu_args, use_xatlas="collapse_retry" not in fallback)
        try:
            require_uv_quality(atlas_quality)
        except PipelineError as error:
            print(f"GAME collapse atlas rejected: {error}", flush=True)
            collapse["accepted"] = False
            fallback["collapse_uv_quality"] = atlas_quality
    if not collapse["accepted"]:
        bpy.data.objects.remove(model, do_unlink=True)
        model = copy_model(source)
        method, reason = remesh_shell(model, *cu_args, voxel=args.remesh)
        discarded = keep_outer_shell(model.data, prefer_surface_area=args.remesh)
        fallback |= {"reason": reason, "discarded_components": discarded,
                    "resolution": 512 if method == "cumesh_remesh" else None,
                    "voxel_m": VOXEL_M if method == "blender_voxel_remesh" else None,
                    "voxel_adaptivity": VOXEL_ADAPTIVITY if method == "blender_voxel_remesh" else None}
        voxel_shell = copy_model(model) if args.remesh and cu_args[0] else None
        if method == "cumesh_remesh" or voxel_shell:
            if not cumesh_transform(model, *cu_args, simplify=TRIANGLE_TARGET, repair_shell=True):
                raise PipelineError("CUMESH_FAILED: installed worker disappeared during simplification.")
            use_cumesh = True
        else:
            clean_and_triangulate(model.data)
            decimate(model)
        keep_outer_shell(model.data, prefer_surface_area=args.remesh)
        # Hole filling and edge collapse can leave slivers that invalidate xatlas.
        clean_and_triangulate(model.data)
        after, faces = triangle_data(model.data)
        if voxel_shell:
            probe = inspect(before, raw_faces, after, faces)
            if not probe["extremities_present"] or min(probe["silhouette_iou"].values()) < 0.8:
                bpy.data.objects.remove(model, do_unlink=True)
                model = voxel_shell
                after, faces = decimate(model)
                keep_outer_shell(model.data, prefer_surface_area=True)
                after, faces = triangle_data(model.data)
                use_cumesh = False
                fallback["simplification_reason"] = "CuMesh simplification failed to preserve the voxel shell."
            else:
                bpy.data.objects.remove(voxel_shell, do_unlink=True)
    quality = collapse if collapse["accepted"] else inspect(before, raw_faces, after, faces)
    if not quality["unique_triangles"] or not quality["extremities_present"] or min(quality["silhouette_iou"].values()) < 0.8:
        raise PipelineError(f"GAME_GEOMETRY: remesh lost source geometry: {quality}")
    if method != "collapse":
        if not collapse["accepted"]:
            unwrap, atlas_quality = unwrap_atlas(model, after, faces, cu_args)
        require_uv_quality(atlas_quality)
        fallback["unwrap"] = unwrap
        fallback["texture_transfer"] = bake_diffuse(source, model, device, args.bake_mask)
    set_points(model, normalize(after))
    sharp_edges = smooth_by_angle(model.data)
    model.location = Vector((0, 0, 0))
    select(model)
    bpy.ops.export_scene.gltf(filepath=str(args.output), export_format="GLB", use_selection=True,
                              export_yup=True, export_texcoords=True, export_normals=True)
    doc, binary = read_glb(args.output)
    xyz, uv, exported = static_mesh(doc, binary)
    atlas_quality = uv_quality(xyz, exported, uv[exported])
    uv_warnings = require_uv_quality(atlas_quality)
    color = doc["materials"][0].get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if color:
        image = doc["images"][doc["textures"][color["index"]]["source"]]
        if image["mimeType"] == "image/png":
            (args.previews / "atlas.png").write_bytes(view_bytes(doc, binary, image["bufferView"]))
    if not unique_triangles(xyz, exported):
        raise PipelineError("GAME_TRIANGLES: duplicate triangles in the exported GLB.")
    render_mesh_previews(args.output, args.previews, (("front", 0), ("side", 90), ("rear", 180)))
    write_json(args.report, {
        "method": method,
        "device": device,
        "mesh_device": ("CPU: Blender Decimate (CuMesh output rejected)" if "simplification_reason" in fallback else
                        f"CUDA: {GPU_NAME}" if use_cumesh or method.startswith("cumesh_") else CPU_ONLY),
        "remesh_device": CPU_ONLY if method == "blender_voxel_remesh" else
                         (f"CUDA: {GPU_NAME}" if method == "cumesh_remesh" else None),
        "preview_device": device,
        "blender_version": bpy.app.version_string,
        "raw_triangles": len(raw_faces),
        "game_triangles": len(exported),
        "triangle_target": TRIANGLE_TARGET,
        "uv_quality": atlas_quality,
        "normal_smoothing": {"angle_degrees": SMOOTH_ANGLE_DEGREES, "sharp_edges": sharp_edges},
        "unique_triangles": True,
        "height_m": float(np.ptp(xyz[:, 1])),
        "collapse": collapse,
        "fallback": fallback,
        "silhouette_iou": quality["silhouette_iou"],
        "extremities_present": quality["extremities_present"],
        "extremity_probes": quality["extremity_probes"],
        "warnings": uv_warnings + (["GAME exceeds the triangle budget."]
                                    if len(exported) > 1.1 * TRIANGLE_TARGET else []) +
                    (["GAME silhouette IoU is below 0.95. Compare against RAW."]
                     if min(quality["silhouette_iou"].values()) < MIN_SILHOUETTE_IOU else []),
    })


if __name__ == "__main__":
    main()
