"""Small CPU fixtures for the projector. Run with the available native NumPy."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from model_glb import mesh_signature, replace_base_color
from model_pixels import png_bytes, preview, project_color, fit_projection, silhouette_iou, pad_atlas
from repair_textured_mesh import compare_extremities, unique_triangles
from send_to_game import PipelineError, check_png
from uv_quality import require_uv_quality, uv_quality


class ProjectionTests(unittest.TestCase):
    def test_atlas_warns_about_tiny_islands_and_rejects_zero_area(self):
        xyz = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        connected = xyz[faces, :2] * 0.8
        good = uv_quality(xyz, faces, connected)
        self.assertEqual(good["islands"], 1)
        self.assertEqual(require_uv_quality(good), [])
        disconnected = connected * 0.0001
        disconnected[1] += 0.1
        bad = uv_quality(xyz, faces, disconnected)
        self.assertEqual(bad["islands"], len(faces))
        self.assertEqual(bad["fraction_triangles_below_one_px"], 1)
        self.assertEqual(len(require_uv_quality(bad)), 3)
        with self.assertRaisesRegex(PipelineError, "UV_QUALITY"):
            require_uv_quality(uv_quality(xyz, faces, np.zeros_like(connected)))

    def test_fit_optimizes_uniform_scale_and_translation(self):
        xyz = np.array([[0, 0, 0], [2, 0, 0], [0, 1, 0]])
        faces = np.array([[0, 1, 2]])
        yy, xx = np.indices((120, 180)) + 0.5
        alpha = (xx >= 47) & (yy <= 94) & ((xx - 47) + 2 * (94 - yy) <= 80)
        _, metrics = fit_projection(xyz, faces, alpha.astype(float))
        self.assertGreater(metrics["iou"], 0.97)
        self.assertLessEqual(metrics["contour_p95_px"], 2.0)

    def test_game_iou_does_not_normalize_away_missing_extents(self):
        before = np.array([[0., 0., 0.], [1., 1., 0.], [0., 0., 1.]])
        after = before.copy()
        after[1, :2] *= 0.8
        faces = np.array([[0, 1, 2]])
        self.assertEqual(silhouette_iou(before, faces, before, faces), {"front": 1.0, "side": 1.0})
        self.assertLess(silhouette_iou(before, faces, after, faces)["front"], 0.9)

    def test_game_extremity_gate_measures_top_of_head(self):
        before = np.array([[-.2, 0, 0], [.2, 0, 0], [-.4, 0, .6], [.4, 0, .6], [0, 0, .9], [0, 0, 1.]])
        after = before.copy()
        after[-1, 2] -= .03
        accepted, report = compare_extremities(before, after)
        self.assertFalse(accepted)
        self.assertAlmostEqual(report["head"]["extent_delta_m"], .03)

    def test_padding_keeps_other_islands_and_reaches_16_pixels(self):
        texture = np.zeros((40, 45, 3), dtype=np.float32)
        covered = np.zeros(texture.shape[:2], dtype=bool)
        changed = covered.copy()
        covered[20, 20] = changed[20, 20] = True
        covered[20, 30] = True
        texture[20, 20] = 1
        pad = pad_atlas(texture, covered, changed, 16)
        self.assertTrue(pad[20, 36])
        self.assertFalse(pad[20, 37])
        self.assertFalse(pad[20, 30])

    def test_game_uniqueness_compares_geometry_across_uv_seams(self):
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [0, 0, 1]])
        self.assertFalse(unique_triangles(points, np.array([[0, 1, 2], [3, 2, 1]])))
        self.assertFalse(unique_triangles(points, np.array([[0, 3, 1]])))
        self.assertTrue(unique_triangles(points, np.array([[0, 1, 2], [3, 2, 4]])))

    def test_depth_and_facing_keep_hidden_atlas_texels(self):
        square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
        xyz = np.vstack([np.column_stack((square, np.ones(4))), np.column_stack((square, np.zeros(4)))])
        # Both surfaces face the camera. Only the closer one receives paint.
        faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
        uv = np.array([[.03, .1], [.45, .1], [.45, .9], [.03, .9],
                       [.55, .1], [.96, .1], [.96, .9], [.55, .9]])
        base = np.ones((48, 48, 4), dtype=np.float32)
        base[:, :, :3] = np.array([51, 77, 128]) / 255
        cutout = np.zeros((64, 64, 4), dtype=np.float32)
        cutout[8:-8, 8:-8] = [1, 0, 0, 1]
        result, painted = project_color(xyz, uv, faces, base, cutout, np.ones(3), 64)
        self.assertGreater(painted, 100)
        np.testing.assert_array_equal(result[24, 11], [255, 0, 0, 255])
        np.testing.assert_array_equal(result[24, 35], [51, 77, 128, 255])
        with self.assertRaisesRegex(ValueError, "no visible foreground texels"):
            project_color(xyz, np.vstack([uv[:4], uv[:4]]), faces, base, cutout, np.ones(3), 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "front.png"
            path.write_bytes(preview(xyz, faces, uv, result / 255, 0, 64))
            check_png(path)

    def test_projection_repack_preserves_mesh_and_drops_unused_images(self):
        binary = b"geompbr!ao!!normbase"
        doc = {"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
               "nodes": [{"mesh": 0, "translation": [1, 2, 3]}], "scenes": [{"nodes": [0]}],
               "buffers": [{"byteLength": len(binary)}],
               "bufferViews": [{"buffer": 0, "byteOffset": offset, "byteLength": 4} for offset in range(0, len(binary), 4)],
               "accessors": [{"bufferView": 0}],
               "images": [{"bufferView": n} for n in (4, 1, 2, 3)],
               "textures": [{"source": n} for n in range(4)],
               "materials": [{"normalTexture": {"index": 3}, "occlusionTexture": {"index": 2},
                              "pbrMetallicRoughness": {"baseColorTexture": {"index": 0},
                                                      "metallicRoughnessTexture": {"index": 1}}}]}
        result, payload = replace_base_color(doc, binary, png_bytes(np.zeros((2, 2, 4), dtype=np.uint8)))
        self.assertEqual(mesh_signature(doc, binary), mesh_signature(result, payload))
        self.assertNotIn("occlusionTexture", result["materials"][0])
        self.assertNotIn("normalTexture", result["materials"][0])
        self.assertEqual(len(result["images"]), 2)
        self.assertIn(b"pbr!", payload)
        self.assertNotIn(b"ao!!", payload)


if __name__ == "__main__":
    unittest.main()
