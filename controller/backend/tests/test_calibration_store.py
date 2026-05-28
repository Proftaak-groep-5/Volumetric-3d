import json
import sys
from pathlib import Path
import tempfile
import unittest

import numpy as np

# Ensure the backend app package is importable when running tests from repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.calibration_store import CalibrationStore


class CalibrationStoreTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        source = Path(__file__).name
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {source}::{test_name}: {message}")

    def test_load_uses_t_camera_world_when_present(self) -> None:
        # Confirms that when T_camera_world is provided, it is used as-is.
        # This prevents unintended inversions that would flip camera frames.
        payload = {
            "cameras": [
                {
                    "camera_id": "cam-a",
                    "success": True,
                    "T_camera_world": np.eye(4).tolist(),
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calib.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = CalibrationStore(path)
            try:
                store.load()
                extrinsics = store.get("cam-a")
                self.assertIsNotNone(extrinsics)
                self.assertTrue(np.allclose(extrinsics.t_camera_world, np.eye(4)))
            except Exception as exc:
                self._report("load_uses_t_camera_world", False, f"unexpected error: {exc}")
                raise
            else:
                self._report(
                    "load_uses_t_camera_world",
                    True,
                    "check=preserve T_camera_world when present",
                    "camera_id=cam-a",
                    "t_camera_world=identity",
                )

    def test_load_inverts_t_world_camera_when_needed(self) -> None:
        # When only T_world_camera is present, load() should invert it.
        # This ensures downstream code always has T_camera_world available.
        t_world_camera = np.eye(4)
        t_world_camera[0, 3] = 1.0
        payload = {
            "cameras": [
                {
                    "camera_id": "cam-b",
                    "success": True,
                    "T_world_camera": t_world_camera.tolist(),
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calib.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = CalibrationStore(path)
            try:
                store.load()
                extrinsics = store.get("cam-b")
                self.assertIsNotNone(extrinsics)
                expected = np.linalg.inv(t_world_camera)
                self.assertTrue(np.allclose(extrinsics.t_camera_world, expected))
            except Exception as exc:
                self._report("load_inverts_t_world_camera", False, f"unexpected error: {exc}")
                raise
            else:
                self._report(
                    "load_inverts_t_world_camera",
                    True,
                    "check=invert T_world_camera when T_camera_world missing",
                    "camera_id=cam-b",
                    "t_world_camera_translation_x=1.0",
                    "used_inverse=True",
                )

    def test_load_skips_invalid_entries(self) -> None:
        # Invalid entries (missing ID, failed calibration, or wrong matrix shape)
        # should be ignored so they do not poison the calibration store.
        payload = {
            "cameras": [
                {"camera_id": "", "success": True, "T_camera_world": np.eye(4).tolist()},
                {"camera_id": "cam-c", "success": False, "T_camera_world": np.eye(4).tolist()},
                {"camera_id": "cam-d", "success": True, "T_camera_world": [[1.0, 0.0], [0.0, 1.0]]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calib.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = CalibrationStore(path)
            try:
                store.load()
                self.assertEqual(store.all_camera_ids(), [])
            except Exception as exc:
                self._report("load_skips_invalid_entries", False, f"unexpected error: {exc}")
                raise
            else:
                self._report(
                    "load_skips_invalid_entries",
                    True,
                    "check=skip invalid/unsuccessful camera entries",
                    "skipped_invalid=3",
                    "kept_valid=0",
                )


if __name__ == "__main__":
    unittest.main()
