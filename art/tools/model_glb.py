"""Read and update a static embedded GLB while preserving mesh data."""

import copy
import json
import struct

from send_to_game import PipelineError, check_glb


def read_glb(path):
    doc = check_glb(path)
    with path.open("rb") as source:
        source.seek(12)
        size = struct.unpack("<I", source.read(4))[0]
        source.seek(28 + size)
        return doc, source.read()


def write_glb(path, doc, binary):
    metadata = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
    metadata += b" " * (-len(metadata) % 4)
    binary += b"\0" * (-len(binary) % 4)
    with path.open("xb") as output:
        output.write(struct.pack("<4sIIII", b"glTF", 2, 28 + len(metadata) + len(binary), len(metadata), 0x4E4F534A))
        output.write(metadata)
        output.write(struct.pack("<II", len(binary), 0x004E4942))
        output.write(binary)


def view_bytes(doc, binary, index):
    view = doc["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def mesh_signature(doc, binary):
    # Buffer offsets are storage details. Preserve accessor metadata, bytes, mesh
    # connectivity and the original node/scene transforms independently of them.
    accessors = copy.deepcopy(doc["accessors"])
    contents = []
    for accessor in accessors:
        if "sparse" in accessor or "bufferView" not in accessor:
            raise PipelineError("PROJECTION_ACCESSOR: expected embedded, non-sparse mesh accessors.")
        index = accessor.pop("bufferView")
        layout = {key: value for key, value in doc["bufferViews"][index].items()
                  if key not in {"byteOffset", "name"}}
        contents.append((layout, view_bytes(doc, binary, index)))
    return (doc["meshes"], doc["nodes"], doc["scenes"], doc.get("scene", 0), accessors, contents)


def replace_base_color(doc, binary, png):
    if (doc.get("extensionsUsed") or len(doc.get("materials", [])) != 1 or
            len(doc.get("buffers", [])) != 1):
        raise PipelineError("PROJECTION_LAYOUT: expected a static GLB with one standard PBR material.")
    result = copy.deepcopy(doc)
    material = result["materials"][0]
    material.pop("normalTexture", None)
    material.pop("occlusionTexture", None)
    pbr = material.setdefault("pbrMetallicRoughness", {})
    base = pbr.get("baseColorTexture", {})
    if base.get("texCoord", 0) != 0 or base.get("extensions"):
        raise PipelineError("PROJECTION_UV: base color requires an untransformed TEXCOORD_0 atlas.")
    # Input factor is already folded into the new RGB atlas by the projector.
    pbr["baseColorFactor"] = [1, 1, 1, pbr.get("baseColorFactor", [1, 1, 1, 1])[3]]
    old_textures, old_images = doc.get("textures", []), doc.get("images", [])
    textures, images, views = [], [], []
    packed = bytearray()
    retained = {}

    def append_view(payload, descriptor):
        packed.extend(b"\0" * (-len(packed) % 4))
        views.append(descriptor | {"buffer": 0, "byteOffset": len(packed), "byteLength": len(payload)})
        packed.extend(payload)
        return len(views) - 1

    def keep_view(index):
        if index not in retained:
            retained[index] = append_view(view_bytes(doc, binary, index), doc["bufferViews"][index])
        return retained[index]

    for accessor in result["accessors"]:
        accessor["bufferView"] = keep_view(accessor["bufferView"])
    for slot in (pbr.get("metallicRoughnessTexture"), material.get("emissiveTexture")):
        if slot is None:
            continue
        old_texture = old_textures[slot["index"]]
        old_image = old_images[old_texture["source"]]
        images.append(old_image | {"bufferView": keep_view(old_image["bufferView"])})
        slot["index"] = len(textures)
        textures.append(old_texture | {"source": len(images) - 1})
    old_base = old_textures[base["index"]] if "index" in base else {}
    images.append({"name": "Blackwood projected color", "mimeType": "image/png", "bufferView": append_view(png, {})})
    pbr["baseColorTexture"] = {"index": len(textures)}
    textures.append(old_base | {"source": len(images) - 1})
    result["textures"], result["images"], result["bufferViews"] = textures, images, views
    result["buffers"] = [{"byteLength": len(packed)}]
    if mesh_signature(doc, binary) != mesh_signature(result, packed):
        raise PipelineError("PROJECTION_GEOMETRY_CHANGED")
    return result, bytes(packed)
