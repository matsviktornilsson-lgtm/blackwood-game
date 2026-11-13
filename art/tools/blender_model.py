"""Read the static glTF mesh and packed textures used by the Blender adapters."""

import argparse
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from model_glb import view_bytes
from gpu_runtime import GPU_NAME
from send_to_game import PipelineError


def configure_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    addon = bpy.context.preferences.addons.get("cycles")
    if addon:
        preferences = addon.preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                preferences.compute_device_type = backend
                devices = preferences.get_devices_for_type(backend)
                selected = {item.id for item in devices if item.type == backend and GPU_NAME in item.name}
            except (RuntimeError, TypeError, ValueError):
                continue
            if selected:
                for item in preferences.devices:
                    item.use = item.type == backend and item.id in selected
                scene.cycles.device = "GPU"
                return f"{backend}: {GPU_NAME}"
    raise PipelineError(f"BLENDER_GPU_REQUIRED: Cycles could not find {GPU_NAME} with OptiX or CUDA.")


def preview_lighting(scene, center, scale):
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("Blackwood preview world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.22, 0.22, 0.22, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.65
    for name, location, energy in (("Key", (3, -4, 4), 750), ("Fill", (-4, -1, 2), 400),
                                   ("Rim", (1, 3, 3), 650)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy * scale ** 2
        light.shape = "DISK"
        light.size = 3 * scale
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(location) * scale
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_mesh_previews(path, destination, views):
    scene = bpy.context.scene
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in scene.objects if obj.type == "MESH"
              for corner in obj.bound_box]
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center = (low + high) / 2
    extent = max(high - low)
    preview_lighting(scene, center, extent / 2.2)
    camera = bpy.data.objects.new("Blackwood orthographic preview", bpy.data.cameras.new("Preview"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = extent * 1.15
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    for label, degrees in views:
        angle = math.radians(degrees)
        focus = center.copy()
        camera.data.ortho_scale = extent * 1.15
        if label == "face":
            focus.z = high.z - (high.z - low.z) * 0.12
            camera.data.ortho_scale = extent * 0.30
        camera.location = focus + Vector((math.sin(angle), -math.cos(angle), 0)) * (3 * extent)
        camera.rotation_euler = (focus - camera.location).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(destination / f"{label}.png")
        if "FINISHED" not in bpy.ops.render.render(write_still=True):
            raise PipelineError(f"PREVIEW_RENDER_FAILED: {label}")


def blender_args(description, inputs, optional=(), *, flags=()):
    parser = argparse.ArgumentParser(description=description)
    for key in (*inputs, "output", "previews", "report"):
        parser.add_argument("--" + key, type=Path, required=True)
    for key in optional:
        parser.add_argument("--" + key, type=Path)
    for key in flags:
        parser.add_argument("--" + key, action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def accessor_data(doc, binary, index):
    accessor = doc["accessors"][index]
    view = doc["bufferViews"][accessor["bufferView"]]
    dtypes = {5121: "u1", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
    dims = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    dtype = np.dtype(dtypes[accessor["componentType"]])
    count, dim = accessor["count"], dims[accessor["type"]]
    stride = view.get("byteStride", dim * dtype.itemsize)
    if "sparse" in accessor or accessor.get("normalized") or stride < dim * dtype.itemsize:
        raise PipelineError("MODEL_ACCESSOR: unsupported sparse, normalized or malformed accessor.")
    offset = accessor.get("byteOffset", 0)
    payload = view_bytes(doc, binary, accessor["bufferView"])
    return np.ndarray((count, dim), dtype, payload, offset, (stride, dtype.itemsize))


def static_mesh(doc, binary):
    nodes, meshes = doc.get("nodes", []), doc["meshes"]
    if len(nodes) != 1 or len(meshes) != 1 or len(meshes[0]["primitives"]) != 1:
        raise PipelineError("MODEL_LAYOUT: expected one static mesh and primitive.")
    node = nodes[0]
    primitive = meshes[0]["primitives"][0]
    if node.get("mesh") != 0 or node.get("children") or doc.get("skins") or doc.get("animations"):
        raise PipelineError("MODEL_LAYOUT: expected a static GAME mesh.")
    if primitive.get("mode", 4) != 4 or primitive.get("material", 0) != 0 or primitive.get("targets"):
        raise PipelineError("MODEL_LAYOUT: expected static triangles using the first material.")
    attributes = primitive["attributes"]
    if "TEXCOORD_0" not in attributes or "COLOR_0" in attributes:
        raise PipelineError("MODEL_UV: expected a UV atlas and no vertex color multiplier.")
    positions = accessor_data(doc, binary, attributes["POSITION"])
    uv = accessor_data(doc, binary, attributes["TEXCOORD_0"])
    indices = accessor_data(doc, binary, primitive["indices"]) if "indices" in primitive else np.arange(len(positions))
    faces = indices.reshape(-1, 3)
    if not np.isfinite(positions).all() or not np.isfinite(uv).all() or np.any(faces >= len(positions)):
        raise PipelineError("MODEL_GEOMETRY: invalid position, UV or index data.")
    if len(positions) != len(uv) or np.any(uv < -1e-5) or np.any(uv > 1.00001):
        raise PipelineError("MODEL_UV: expected normalized atlas coordinates.")
    if "matrix" in node:
        matrix = np.asarray(node["matrix"], dtype=float).reshape(4, 4).T
    else:
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        matrix = np.asarray(Matrix.LocRotScale(Vector(node.get("translation", [0, 0, 0])),
                                              Quaternion((w, x, y, z)), Vector(node.get("scale", [1, 1, 1]))))
    xyz = positions @ matrix[:3, :3].T + matrix[:3, 3]
    return xyz, uv, faces


def image_pixels(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        width, height = image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        return pixels.reshape(height, width, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(image)


def base_color(doc, binary, work):
    pbr = doc["materials"][0].get("pbrMetallicRoughness", {})
    tex = pbr.get("baseColorTexture")
    factor = np.asarray(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3])
    if tex is None:
        return np.ones((1024, 1024, 4), dtype=np.float32), factor
    source = doc["textures"][tex["index"]]["source"]
    image = doc["images"][source]
    suffix = {"image/png": ".png", "image/jpeg": ".jpg"}[image["mimeType"]]
    with tempfile.TemporaryDirectory(prefix=".blackwood-image-", dir=work) as directory:
        path = Path(directory) / ("base-color" + suffix)
        path.write_bytes(view_bytes(doc, binary, image["bufferView"]))
        return image_pixels(path), factor
