"""Project a cutout onto visible GAME texels without rewriting its geometry."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import numpy as np

from blender_model import base_color, blender_args, configure_cycles, image_pixels, render_mesh_previews, static_mesh
from model_glb import mesh_signature, read_glb, replace_base_color, write_glb
from send_to_game import PipelineError, read_json, write_json
from uv_quality import require_uv_quality, uv_islands, uv_quality


def main():
    args = blender_args(__doc__, ["game", "image", "comfy-python"], ["bake-mask"], flags=["face-preview"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    preview_device = configure_cycles()
    doc, binary = read_glb(args.game)
    xyz, uv, faces = static_mesh(doc, binary)
    atlas_quality = uv_quality(xyz, faces, uv[faces])
    uv_warnings = require_uv_quality(atlas_quality)
    base, factor = base_color(doc, binary, args.output.parent)
    cutout = image_pixels(args.image)
    with tempfile.TemporaryDirectory(prefix=".blackwood-projection-", dir=args.output.parent) as directory:
        root = Path(directory)
        inputs, texture, report = (root / name for name in ("inputs.npz", "texture.png", "report.json"))
        options = {}
        if args.bake_mask:
            mask = image_pixels(args.bake_mask)[:, :, 0] > 0.5
            if mask.shape != base.shape[:2] or not mask.any():
                raise PipelineError("GAME_BAKE: coverage mask is empty or has the wrong size.")
            options = {"bake_valid": mask, "islands": uv_islands(xyz, faces, uv[faces]) + 1}
        np.savez(inputs, xyz=xyz, faces=faces, uv=uv, base=base, cutout=cutout, factor=factor, **options)
        subprocess.run([str(args.comfy_python), "-B", "-X", "utf8", str(Path(__file__).with_name("project_cuda.py")),
                        str(inputs), str(texture), str(report), *(["--fill-holes"] if options else [])], check=True)
        evidence = read_json(report)
        texture_bytes = texture.read_bytes()
        baked, data = replace_base_color(doc, binary, texture_bytes)
    write_glb(args.output, baked, data)
    saved, saved_binary = read_glb(args.output)
    if mesh_signature(doc, binary) != mesh_signature(saved, saved_binary):
        raise PipelineError("PROJECTION_GEOMETRY_CHANGED: serialized GLB differs from GAME.")
    render_mesh_previews(args.output, args.previews,
                         (("front", 0), ("oblique30", 30), ("face", 0) if args.face_preview else ("rear", 180)))
    (args.previews / "atlas.png").write_bytes(texture_bytes)
    alignment = evidence["alignment"]
    write_json(args.report, {
        "method": "Orthographic +Z depth-tested UV rasterization",
        "blender_version": bpy.app.version_string,
        "geometry_preserved": True,
        "uv_preserved": True,
        "transform_preserved": True,
        **evidence,
        "preview_device": preview_device,
        "triangles": len(faces),
        "uv_quality": atlas_quality,
        "height_m": float(np.ptp(xyz[:, 1])),
        "alignment": alignment,
        "alpha_feather_px": 4,
        "uv_padding_px": 16,
        "warnings": uv_warnings + evidence["warnings"] +
                    (["Silhouette IoU below 0.80."] if alignment["iou"] < 0.8 else []),
    })


if __name__ == "__main__":
    main()
