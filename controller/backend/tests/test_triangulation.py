import sys
from pathlib import Path
import unittest

import numpy as np

# Ensure the backend app package is importable when running tests from repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.triangulation import TriangulationService


class _DummyCalibrationStore:
    def __init__(self, matrices: dict[str, np.ndarray]) -> None:
        self._matrices = matrices

    def get(self, camera_id: str):
        matrix = self._matrices.get(camera_id)
        if matrix is None:
            return None
        return type("Extrinsics", (), {"t_camera_world": matrix})


class _DummyCameraManager:
    def __init__(self, intrinsics: dict[str, np.ndarray]) -> None:
        self._intrinsics = intrinsics

    def intrinsics(self, camera_id: str):
        return self._intrinsics.get(camera_id)


class TriangulationServiceTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        source = Path(__file__).name
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {source}::{test_name}: {message}")

    def test_create_point_requires_two_observations(self) -> None:
        # Triangulation requires at least two valid observations; otherwise
        # there is no depth information and the method must reject the input.
        store = _DummyCalibrationStore({})
        manager = _DummyCameraManager({})
        service = TriangulationService(manager, store)
        with self.assertRaises(ValueError) as context:
            service.create_point([])
        self._report(
            "create_point_requires_two_observations",
            True,
            "check=reject when <2 valid observations",
            "observations=0",
            f"error={context.exception}",
        )

    def test_create_point_returns_world_point(self) -> None:
        # With two calibrated cameras and valid observations, create_point()
        # should return a finite 3D point and per-camera reprojection errors.
        intrinsics = {
            "cam-a": np.eye(3),
            "cam-b": np.eye(3),
        }
        t_camera_world_a = np.eye(4)
        t_camera_world_b = np.eye(4)
        t_camera_world_b[0, 3] = 1.0
        store = _DummyCalibrationStore({"cam-a": t_camera_world_a, "cam-b": t_camera_world_b})
        manager = _DummyCameraManager(intrinsics)
        service = TriangulationService(manager, store)

        obs = [
            type("Obs", (), {"camera_id": "cam-a", "u": 0.0, "v": 0.0}),
            type("Obs", (), {"camera_id": "cam-b", "u": 0.1, "v": 0.0}),
        ]
        try:
            point_world, reprojection = service.create_point(obs)
            self.assertEqual(point_world.shape, (3,))
            self.assertEqual(set(reprojection.keys()), {"cam-a", "cam-b"})
        except Exception as exc:
            self._report("create_point_returns_world_point", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "create_point_returns_world_point",
                True,
                "check=return finite world point and reprojection errors",
                f"point_world={np.array2string(point_world, precision=4)}",
                f"reprojection={{{', '.join(f'{k}:{v:.4f}' for k, v in reprojection.items())}}}",
            )

    def test_to_unity_flips_z(self) -> None:
        # Unity uses a different handedness; Z must be flipped to match
        # the engine coordinate system expected by the frontend.
        point = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        try:
            unity = TriangulationService.to_unity(point)
            self.assertTrue(np.allclose(unity, np.array([1.0, 2.0, -3.0])))
        except Exception as exc:
            self._report("to_unity_flips_z", False, f"unexpected error: {exc}")
            raise
        else:
            self._report(
                "to_unity_flips_z",
                True,
                "check=flip Z axis for Unity space",
                "input=[1.0,2.0,3.0]",
                f"output={np.array2string(unity, precision=1)}",
            )


if __name__ == "__main__":
    unittest.main()
