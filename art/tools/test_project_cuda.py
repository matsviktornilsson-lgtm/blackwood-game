"""Live CUDA projection fixtures. Run with the configured ComfyUI Python."""

import unittest

import numpy as np
import torch

from model_pixels import fit_frame, fit_projection
from probe_torch_gpu import cuda_4090
from project_cuda import cuda_choose, cuda_contours, cuda_mask, fill_atlas_holes, project, projection_coverage


class CudaProjectionTests(unittest.TestCase):
    def test_hole_fill_preserves_dark_hits_and_island_boundaries(self):
        image = np.zeros((1, 7, 4), dtype=np.float32)
        image[0, 0, :3] = 1
        image[0, 3, :3] = 0.5
        labels = np.array([[1, 1, 0, 2, 2, 3, 3]])
        valid = np.array([[True, False, False, True, True, False, False]])
        filled = fill_atlas_holes(image, valid, labels)
        np.testing.assert_array_equal(filled, [[False, True, False, False, False, False, False]])
        np.testing.assert_array_equal(image[0, :, 0], [1, 1, 0, 0.5, 0, 0, 0])
    def test_projection_coverage_thresholds(self):
        with self.assertRaisesRegex(ValueError, r"PROJECTION_COVERAGE: 19/100"):
            projection_coverage(19, 100)
        with self.assertRaisesRegex(ValueError, r"PROJECTION_COVERAGE: 0/0"):
            projection_coverage(0, 0)
        self.assertEqual(len(projection_coverage(20, 100)[1]), 1)
        self.assertEqual(len(projection_coverage(49, 100)[1]), 1)
        self.assertEqual(projection_coverage(50, 100), (0.5, []))

    def setUp(self):
        self.device = cuda_4090()

    def tensor(self, data, dtype=torch.float32):
        return torch.as_tensor(data, device=self.device, dtype=dtype)

    def test_alignment_optimizes_uniform_scale_and_offset_on_cuda(self):
        xyz = np.array([[0, 0, 0], [2, 0, 0], [0, 1, 0]])
        faces = np.array([[0, 1, 2]])
        yy, xx = np.indices((120, 180)) + 0.5
        alpha = (xx >= 47) & (yy <= 94) & ((xx - 47) + 2 * (94 - yy) <= 80)
        _, report = fit_projection(
            xyz, faces, alpha.astype(float),
            rasterize=lambda points, _, width, height: cuda_mask(
                self.tensor(points), self.tensor(faces, torch.long), width, height).cpu().numpy(),
            contours=lambda a, b: cuda_contours(self.tensor(a, torch.bool), self.tensor(b, torch.bool)),
            choose=lambda ref, target, candidates: cuda_choose(ref, target, candidates, self.device),
        )
        self.assertGreater(report["iou"], 0.97)
        self.assertLessEqual(report["contour_p95_px"], 2)

    def test_visible_surface_only_and_shared_texels_unchanged(self):
        square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
        xyz = np.vstack([np.column_stack((square, np.ones(4))), np.column_stack((square, np.zeros(4)))])
        faces = self.tensor([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], torch.long)
        uv = np.array([[.03, .1], [.45, .1], [.45, .9], [.03, .9],
                       [.55, .1], [.96, .1], [.96, .9], [.55, .9]])
        base = np.ones((48, 48, 4), dtype=np.float32)
        base[:, :, :3] = np.array([51, 77, 128]) / 255
        cutout = np.zeros((64, 64, 4), dtype=np.float32)
        cutout[8:-8, 8:-8] = [1, 0, 0, 1]
        screen, scale = fit_frame(xyz[:, :2], 64, 64, 0.95)
        camera, _ = fit_frame(xyz[:, :2], 64, 64, 0.75)

        def run(atlas):
            return project(self.tensor(xyz), faces, self.tensor(atlas), self.tensor(base), self.tensor(cutout),
                           self.tensor([1, 1, 1]), self.tensor(screen), scale, self.tensor(camera), 64)

        result, count, front_count, eligible_count = run(uv)
        self.assertGreater(count, 100)
        self.assertGreaterEqual(front_count, eligible_count)
        self.assertGreaterEqual(eligible_count, count)
        self.assertEqual(result[24, 11].tolist(), [255, 0, 0, 255])
        self.assertEqual(result[24, 35].tolist(), [51, 77, 128, 255])
        shared, count, front_count, _ = run(np.vstack((uv[:4], uv[:4])))
        self.assertEqual(shared[24, 11].tolist(), [51, 77, 128, 255])
        with self.assertRaisesRegex(ValueError, "PROJECTION_COVERAGE"):
            projection_coverage(count, front_count)


if __name__ == "__main__":
    unittest.main()
