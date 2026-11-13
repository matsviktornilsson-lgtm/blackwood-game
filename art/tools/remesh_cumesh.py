"""Run TRELLIS.2's CuMesh dual contouring in its own Windows Python."""

import argparse
import importlib.util
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--simplify", type=int)
    operations.add_argument("--unwrap", action="store_true")
    parser.add_argument("--repair-shell", action="store_true")
    parser.add_argument("--site-packages")
    args = parser.parse_args()
    if args.site_packages:
        sys.path.insert(0, args.site_packages)
    if not importlib.util.find_spec("cumesh"):
        return 3

    import cumesh
    import numpy as np
    import torch
    from probe_torch_gpu import cuda_4090

    device = cuda_4090()
    with np.load(args.source, allow_pickle=False) as data, torch.inference_mode():
        vertices = torch.as_tensor(data["points"], dtype=torch.float32, device=device).contiguous()
        faces = torch.as_tensor(data["faces"], dtype=torch.int32, device=device).contiguous()
        mesh = cumesh.CuMesh()
        mesh.init(vertices, faces)
        if args.unwrap:
            atlas = cumesh.Atlas()
            atlas.add_mesh(vertices.cpu(), faces.cpu())
            atlas.compute_charts(max_cost=8, normal_deviation_weight=0.1, normal_seam_weight=0,
                                 straightness_weight=0.1, fix_winding=True)
            atlas.pack_charts(resolution=2048, padding=2)
            vertex_map, atlas_faces, uv = atlas.get_mesh(0)
            np.savez(args.output, faces=vertex_map[atlas_faces.long()].numpy(), uv=uv[atlas_faces.long()].numpy())
            return 0
        if args.simplify is not None:
            lower, upper = vertices.amin(dim=0), vertices.amax(dim=0)
            mesh.simplify(args.simplify, verbose=False)
            if args.repair_shell:
                vertices, faces = mesh.read()
                tolerance = (upper - lower).max() * 0.01
                bounded = ((vertices >= lower - tolerance) & (vertices <= upper + tolerance)).all(dim=1)
                mesh.init(vertices, faces[bounded[faces.long()].all(dim=1)].contiguous())
                mesh.remove_unreferenced_vertices()
                mesh.repair_non_manifold_edges()
                mesh.remove_non_manifold_faces()
                mesh.fill_holes(max_hole_perimeter=0.15)
            vertices, faces = mesh.read()
            np.savez(args.output, points=vertices.cpu().numpy(), faces=faces.cpu().numpy())
            return 0
        mesh.fill_holes(max_hole_perimeter=0.03)
        vertices, faces = mesh.read()
        lower, upper = vertices.amin(dim=0), vertices.amax(dim=0)
        center = (lower + upper) / 2
        resolution, band = 512, 1
        scale = (upper - lower).max().item() * (resolution + 3 * band) / resolution
        bvh = cumesh.cuBVH(vertices, faces)
        vertices, faces = cumesh.remeshing.remesh_narrow_band_dc(
            vertices, faces, center=center, scale=scale, resolution=resolution, band=band,
            project_back=0, verbose=False, bvh=bvh,
        )
        # Dual contouring can return outlier vertices far outside its source grid.
        padding = 4 * scale / resolution
        bounded = ((vertices >= lower - padding) & (vertices <= upper + padding)).all(dim=1)
        faces = faces[bounded[faces.long()].all(dim=1)].contiguous()
        mesh.init(vertices, faces)
        mesh.remove_unreferenced_vertices()
        mesh.repair_non_manifold_edges()
        mesh.fill_holes(max_hole_perimeter=0.15)
        vertices, faces = mesh.read()
        np.savez(args.output, points=vertices.cpu().numpy(), faces=faces.cpu().numpy())
    return 0


if __name__ == "__main__":
    sys.exit(main())
