import sys
from pathlib import Path
import unittest

import numpy as np

# Ensure the backend app package is importable when running tests from repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.volumetric_capture import VolumetricCaptureService


class VolumetricCaptureUtilsTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        source = Path(__file__).name
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {source}::{test_name}: {message}")

    def test_apply_transform_rotates_and_translates(self) -> None:
        # Applies a known rotation+translation and verifies output points.
        # This validates the core math used for point cloud alignment.
        points = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        transform[:3, 3] = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        try:
            result = VolumetricCaptureService._apply_transform(points, transform)
            self.assertTrue(np.allclose(result, np.array([[1.0, 3.0, 3.0]])))
        except Exception as exc:
            self._report("apply_transform", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "apply_transform",
                True,
                "check=apply rotation+translation to points",
                "input=[1,0,0]",
                "rotation=90deg_z",
                "translation=[1,2,3]",
                f"output={np.array2string(result, precision=1)}",
            )

    def test_rescale_intrinsics_skips_small_changes(self) -> None:
        # Small deltas should be ignored to avoid camera intrinsics jitter.
        # This preserves stability when frame sizes are effectively unchanged.
        k = np.array([[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        try:
            scaled = VolumetricCaptureService._rescale_intrinsics_to_frame(k, target_width=640, target_height=480)
            self.assertTrue(np.allclose(scaled, k))
        except Exception as exc:
            self._report("rescale_intrinsics_skip", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "rescale_intrinsics_skip",
                True,
                "check=skip rescale when delta below epsilon",
                "target=640x480",
                "delta<epsilon",
                "intrinsics=unchanged",
            )

    def test_projection_score_increases_for_in_bounds_points(self) -> None:
        # Points inside the image should yield a non-zero score; this guards
        # against scoring regressions that would reject valid projections.
        color = np.zeros((100, 100, 3), dtype=np.uint8)
        k = np.array([[50.0, 0.0, 50.0], [0.0, 50.0, 50.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        points = np.array([[0.0, 0.0, 1.0], [10.0, 10.0, 1.0]], dtype=np.float64)
        try:
            score = VolumetricCaptureService._projection_score(color, points, k)
            self.assertGreaterEqual(score, 0.5)
        except Exception as exc:
            self._report("projection_score", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "projection_score",
                True,
                "check=score >= 0.5 for in-bounds points",
                f"score={score:.3f}",
                "expected>=0.5",
            )

    def test_voxel_fuse_reduces_points(self) -> None:
        # Voxel fusion should reduce (or keep) the number of points while
        # preserving color alignment between points and colors arrays.
        points = np.array(
            [[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [1.0, 1.0, 1.0]],
            dtype=np.float64,
        )
        colors = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.uint8)
        try:
            fused_points, fused_colors = VolumetricCaptureService._voxel_fuse(points, colors, voxel_size_m=0.01)
            self.assertLessEqual(fused_points.shape[0], points.shape[0])
            self.assertEqual(fused_points.shape[0], fused_colors.shape[0])
        except Exception as exc:
            self._report("voxel_fuse", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "voxel_fuse",
                True,
                "check=fuse nearby points within voxel size",
                f"before={points.shape[0]}",
                f"after={fused_points.shape[0]}",
                "voxel_size=0.01m",
            )

    def test_camera_to_world_inverts_transform(self) -> None:
        # camera_to_world should apply the inverse translation so points
        # move from camera space into world space correctly.
        points = np.array([[1.0, 2.0, 3.0]], dtype=np.float64)
        t_camera_world = np.eye(4, dtype=np.float64)
        t_camera_world[:3, 3] = np.array([1.0, 0.0, 0.0])
        try:
            world_points = VolumetricCaptureService._camera_to_world(points, t_camera_world)
            self.assertTrue(np.allclose(world_points, np.array([[0.0, 2.0, 3.0]])))
        except Exception as exc:
            self._report("camera_to_world", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "camera_to_world",
                True,
                "check=invert translation to world space",
                "translation=[1,0,0]",
                f"output={np.array2string(world_points, precision=1)}",
            )

    def test_depth_rgb_baseline_compare_within_tolerance(self) -> None:
        # Confirms baseline comparison accepts deltas <= 0.5 mm.
        calib = np.eye(4, dtype=np.float64)
        sdk = np.eye(4, dtype=np.float64)
        calib[0, 3] = -0.032
        sdk[0, 3] = -0.0324
        try:
            result = VolumetricCaptureService._compare_depth_rgb_transforms(calib, sdk, 0.0005)
            self.assertTrue(result.get("ok", False))
        except Exception as exc:
            self._report("depth_rgb_baseline_ok", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "depth_rgb_baseline_ok",
                True,
                "check=delta <= 0.5mm",
                f"delta={result.get('delta_translation_m')}",
            )

    def test_depth_rgb_baseline_compare_outside_tolerance(self) -> None:
        # Confirms baseline comparison flags deltas > 0.5 mm.
        calib = np.eye(4, dtype=np.float64)
        sdk = np.eye(4, dtype=np.float64)
        calib[0, 3] = -0.032
        sdk[0, 3] = -0.033
        try:
            result = VolumetricCaptureService._compare_depth_rgb_transforms(calib, sdk, 0.0005)
            self.assertFalse(result.get("ok", True))
        except Exception as exc:
            self._report("depth_rgb_baseline_fail", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "depth_rgb_baseline_fail",
                True,
                "check=delta > 0.5mm",
                f"delta={result.get('delta_translation_m')}",
            )


if __name__ == "__main__":
    unittest.main()
