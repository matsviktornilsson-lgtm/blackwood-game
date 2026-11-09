"""Rig the generated Blackwood wolf with Blender 4.2 or later."""

import argparse
from math import radians
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledge_skeleton import PARENTS, create_ledge_skeleton


# Joint heights traced on front and side views of the selected TRELLIS.2 mesh.
# At each height, fit the horizontal center to opposing surfaces of the mesh.
# These guides are in the imported pose (Blender forward -Y, meters at 2.2 m).
AXIAL_GUIDES = {
    "Chest": (-.036, .017, 1.46),
    "Pelvis": (-.017, .146, 1.14),
    "Head": (-.030, -.209, 1.93),
    "Jaw": (-.030, -.278, 1.881),
    "Tail": (-.018, .264, 1.12),
}
SIDE_GUIDES = {
    "L": {  # Source right on screen becomes game left after the 180° turn.
        "Shoulder": (.217, -.050, 1.79),
        "Elbow": (.277, .125, 1.51),
        "Wrist": (.386, -.090, 1.23),
        "Hip": (.108, .131, 1.12),
        "Knee": (.153, -.130, .713),
        "Hock": (.199, .122, .194),
        "Toes": (.286, -.120, .047),
    },
    "R": {
        "Shoulder": (-.279, -.051, 1.79),
        "Elbow": (-.361, .043, 1.49),
        "Wrist": (-.418, -.137, 1.24),
        "Hip": (-.150, .150, 1.12),
        "Knee": (-.188, -.005, .660),
        "Hock": (-.242, .323, .180),
        "Toes": (-.296, .047, .045),
    },
}
TURN = Matrix.Rotation(radians(180), 4, "Z")


def select(active, *others):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (active, *others):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def import_skin(path):
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes or any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects):
        raise RuntimeError("Expected a static GLB with at least one mesh.")
    for obj in meshes:
        transform = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = transform
        select(obj)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    select(*meshes)
    if len(meshes) > 1:
        bpy.ops.object.join()
    skin = bpy.context.object
    skin.name = "Generated ledge werewolf"
    if not skin.data.uv_layers or not skin.data.materials:
        raise RuntimeError("The source GLB has no UVs or materials to preserve.")
    return skin


def fit_landmarks(skin):
    vertices = [vertex.co.copy() for vertex in skin.data.vertices]
    height = max(v.z for v in vertices) - min(v.z for v in vertices)
    unit = height / 2.2
    ground = Vector((0, 0, min(v.z for v in vertices)))
    surface = BVHTree.FromPolygons(vertices, [tuple(p.vertices) for p in skin.data.polygons])
    guides = dict(AXIAL_GUIDES)
    for side, joints in SIDE_GUIDES.items():
        guides.update({f"{name}.{side}": point for name, point in joints.items()})
    positions = {}
    for name, guide in guides.items():
        point = Vector(guide) * unit + ground
        # Keep the jaw hinge behind the lips. The muzzle cross section includes
        # the ruff and would pull that pivot forward.
        axes = ((1, 0, 0),) if name == "Jaw" else ((1, 0, 0), (0, 1, 0))
        for direction in axes:
            axis = Vector(direction)
            # Stop before the next limb or the crest of the mane can move the joint.
            reach = (.21 if name in ("Chest", "Pelvis") else .116) * unit
            a = surface.ray_cast(point - axis * reach, axis, reach * 2)[0]
            b = surface.ray_cast(point + axis * reach, -axis, reach * 2)[0]
            if a is not None and b is not None and (a - point).dot(axis) < 0 < (b - point).dot(axis):
                point += axis * max(-.04 * unit, min(.04 * unit, ((a + b) * .5 - point).dot(axis)))
        positions[name] = TURN @ point
    # Probe the mouth opening from the side, between the visible lip surfaces.
    has_opening = any(
        surface.ray_cast(Vector((-.16, depth, z)) * unit + ground, Vector((1, 0, 0)), .28 * unit)[0] is None
        for depth, z in ((-.37, 1.86), (-.38, 1.87), (-.39, 1.88))
    )
    return positions, vertices, unit, ground.z, has_opening


def proxy_mesh(skin, voxel_size):
    proxy = bpy.data.objects.new("Weight proxy", skin.data.copy())
    bpy.context.collection.objects.link(proxy)
    proxy.data.materials.clear()
    edit = bmesh.new()
    edit.from_mesh(proxy.data)
    bmesh.ops.remove_doubles(edit, verts=list(edit.verts), dist=voxel_size * .025)
    bmesh.ops.holes_fill(edit, edges=[edge for edge in edit.edges if edge.is_boundary], sides=12)
    bmesh.ops.recalc_face_normals(edit, faces=list(edit.faces))
    edit.to_mesh(proxy.data)
    edit.free()
    select(proxy)
    proxy.data.remesh_voxel_size = voxel_size
    bpy.ops.object.voxel_remesh()

    # Floating flecks can have no nearby bone. Keep the body shell for the solve.
    edit = bmesh.new()
    edit.from_mesh(proxy.data)
    remaining = set(edit.verts)
    islands = []
    while remaining:
        island = [remaining.pop()]
        for vertex in island:
            for edge in vertex.link_edges:
                neighbor = edge.other_vert(vertex)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    island.append(neighbor)
        islands.append(island)
    if not islands:
        edit.free()
        raise RuntimeError("Voxel remesh did not produce a body shell.")
    islands.sort(key=len, reverse=True)
    bmesh.ops.delete(edit, geom=[v for island in islands[1:] for v in island], context="VERTS")
    if any(not edge.is_manifold for edge in edit.edges):
        edit.free()
        raise RuntimeError("The voxel proxy has non-manifold edges.")
    count = len(edit.verts)
    edit.to_mesh(proxy.data)
    edit.free()
    return proxy, count


def weight_proxy(proxy, positions):
    # Heat diffusion needs limb-length segments. The exported rig uses Blackwood's
    # short, parallel bones, so solve with a temporary armature at the same pivots.
    solver = create_ledge_skeleton(positions)
    bpy.ops.object.mode_set(mode="EDIT")
    bones = solver.data.edit_bones
    for name, offset in {"Chest": (0, 0, .23), "Pelvis": (0, 0, .14), "Head": (0, .034, .13)}.items():
        bones[name].tail = bones[name].head + Vector(offset)
    for side in SIDE_GUIDES:
        for a, b in (("Shoulder", "Elbow"), ("Elbow", "Wrist"), ("Hip", "Knee"),
                     ("Knee", "Hock"), ("Hock", "Toes")):
            start = bones[f"{a}.{side}"]
            start.tail = start.head.lerp(bones[f"{b}.{side}"].head, .90)
        for name, offset in (("Wrist", (0, .012, -.13)), ("Toes", (0, .065, 0))):
            bone = bones[f"{name}.{side}"]
            bone.tail = bone.head + Vector(offset)
    bones["Jaw"].use_deform = False
    bones["Tail"].use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    select(solver, proxy)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    missing = sum(not any(group.weight > 0 for group in v.groups) for v in proxy.data.vertices)
    if missing:
        raise RuntimeError(f"Bone heat left {missing} proxy vertices without weights.")
    proxy.parent = None
    proxy.modifiers.clear()
    bpy.data.objects.remove(solver, do_unlink=True)


def transfer_weights(proxy, skin):
    for group in proxy.vertex_groups:
        skin.vertex_groups.new(name=group.name)
    select(skin)
    transfer = skin.modifiers.new("Proxy weight transfer", "DATA_TRANSFER")
    transfer.object = proxy
    transfer.use_vert_data = True
    transfer.data_types_verts = {"VGROUP_WEIGHTS"}
    transfer.vert_mapping = "POLYINTERP_NEAREST"
    transfer.layers_vgroup_select_src = "ALL"
    transfer.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier=transfer.name)
    bpy.data.objects.remove(proxy, do_unlink=True)


def smooth(low, high, value):
    t = max(0, min(1, (value - low) / (high - low)))
    return t * t * (3 - 2 * t)


def normalize_skin(skin, original, positions, unit, floor, has_opening):
    groups = {group.name: group for group in skin.vertex_groups}
    for name in PARENTS:
        if name not in groups:
            groups[name] = skin.vertex_groups.new(name=name)
    names = {group.index: name for name, group in groups.items()}
    heat_bones = positions.keys() - {"Jaw", "Tail"}
    jaw_vertices = 0
    unweighted = 0
    max_influences = 0
    for vertex, point in zip(skin.data.vertices, original):
        x, depth, z = point / unit
        z -= floor / unit
        # Only the chin and lower lip move. Exclude the nasal pad, upper lip and ruff.
        jaw = 0
        if has_opening:
            seam = 1.854 + .020 * smooth(-.423, -.367, depth)
            jaw = ((1 - smooth(seam - .021, seam, z))
                   * (1 - smooth(-.334, -.284, depth))
                   * smooth(-.457, -.418, depth)
                   * (1 - smooth(.053, .090, abs(x + .030)))
                   * smooth(1.745, 1.798, z))
        tail = smooth(.269, .431, depth) * (1 - smooth(.125, .197, abs(x + .03)))
        tail *= smooth(.46, .68, z) * (1 - smooth(1.12, 1.25, z))
        weights = {names[g.group]: g.weight for g in vertex.groups
                   if g.weight > .00001 and names[g.group] not in ("Jaw", "Tail")}
        total = sum(weights.values())
        if not total:
            nearest = min(heat_bones, key=lambda name: (positions[name] - vertex.co).length_squared)
            weights[nearest] = total = 1
            unweighted += 1
        weights = {name: weight * (1 - jaw - tail) / total for name, weight in weights.items()}
        weights.update(Jaw=jaw, Tail=tail)
        strongest = sorted(((name, weight) for name, weight in weights.items() if weight > .00001),
                           key=lambda item: item[1], reverse=True)[:4]
        total = sum(weight for _, weight in strongest)
        for assignment in list(vertex.groups):
            skin.vertex_groups[assignment.group].remove([vertex.index])
        for name, weight in strongest:
            groups[name].add([vertex.index], weight / total, "REPLACE")
        jaw_vertices += any(name == "Jaw" for name, _ in strongest)
        max_influences = max(max_influences, len(strongest))
    return jaw_vertices, unweighted, max_influences


def export_skin(skin, rig, path):
    skin.parent = rig
    modifier = skin.modifiers.new("Ledge skin", "ARMATURE")
    modifier.object = rig
    select(rig, skin)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_animations=False, export_cameras=False, export_lights=False,
    )


def render_diagnostics(skin, rig, output):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.color_type = "TEXTURE"
    shading.light = "STUDIO"
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    for mat in skin.data.materials:
        if mat and mat.use_nodes:
            shader = next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
            if shader and shader.inputs["Base Color"].is_linked:
                mat.node_tree.nodes.active = shader.inputs["Base Color"].links[0].from_node
    scene.render.resolution_x = 720
    scene.render.resolution_y = 840
    scene.render.resolution_percentage = 100
    cam = bpy.data.objects.new("Diagnostic camera", bpy.data.cameras.new("Diagnostic camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    full_scale = skin.dimensions.z * 1.19
    center = Vector((0, 0, (min(v.co.z for v in skin.data.vertices) + max(v.co.z for v in skin.data.vertices)) * .5))
    mouth = rig.data.bones["Jaw"].head_local + Vector((0, .05, .02)) * (skin.dimensions.z / 2.2)
    for pose in ("rest", "test"):
        if pose == "test":
            for name, degrees in (("Elbow.L", 60), ("Elbow.R", 60), ("Jaw", -25)):
                bone = rig.pose.bones[name]
                axis = bone.bone.matrix_local.to_quaternion().inverted() @ Vector((1, 0, 0))
                bone.rotation_quaternion = Quaternion(axis, radians(degrees))
            bpy.context.view_layer.update()
        views = (("front", (0, 1, 0), center, full_scale), ("side", (1, 0, 0), center, full_scale),
                 ("back", (0, -1, 0), center, full_scale), ("jaw", (1, .15, -.06), mouth, full_scale * .19))
        for view, direction, target, scale in views:
            cam.data.ortho_scale = scale
            cam.location = target + Vector(direction) * 5
            cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = str(output / f"{pose}-{view}.png")
            bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    source, target = args.source.resolve(), args.output.resolve()
    if source == target or target.suffix.lower() != ".glb":
        parser.error("Provide a separate .glb output path.")
    target.parent.mkdir(parents=True, exist_ok=True)
    diagnostics = target.with_name(target.stem + "-diagnostics")
    diagnostics.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    skin = import_skin(source)
    positions, original, unit, floor, has_opening = fit_landmarks(skin)
    skin.data.transform(TURN)
    skin.data.update()
    report = [f"Blender {bpy.app.version_string}", f"Source: {source.name}",
              "Joint pivots in game coordinates (meters; X right, Y up, -Z forward):"]
    for name in PARENTS:
        x, y, z = positions[name]
        report.append(f"  {name:12} ({x:+.3f}, {z:+.3f}, {-y:+.3f})")
    print("\n".join(report), flush=True)
    proxy, proxy_vertices = proxy_mesh(skin, .016 * unit)
    weight_proxy(proxy, positions)
    transfer_weights(proxy, skin)
    jaw_vertices, fallback, max_influences = normalize_skin(skin, original, positions, unit, floor, has_opening)
    rig = create_ledge_skeleton(positions)
    export_skin(skin, rig, target)
    skin.data.calc_loop_triangles()
    report += [
        f"Watertight proxy: {proxy_vertices:,} vertices",
        f"Original mesh: {len(skin.data.vertices):,} vertices, {len(skin.data.loop_triangles):,} triangles",
        f"Vertices without weights: {sum(not v.groups for v in skin.data.vertices):,}",
        f"Vertices requiring nearest-bone fallback: {fallback:,}",
        f"Maximum influences per vertex: {max_influences}",
        f"Vertices with jaw influence: {jaw_vertices:,}",
        ("Mouth: lateral opening detected. Inspect the jaw renders for a fused lip or missing cavity."
         if has_opening else "Mouth: no lateral opening detected. Jaw weights were left at zero."),
        f"Export size: {target.stat().st_size:,} bytes",
    ]
    render_diagnostics(skin, rig, diagnostics)
    (diagnostics / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[3:]), flush=True)


if __name__ == "__main__":
    main()
