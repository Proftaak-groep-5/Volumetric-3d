import json
from pathlib import Path
import unittest
from unittest import mock

from calibration.config import CalibrationConfig, QualityConfig


class _DummyAruco:
    # Minimal ArUco stub so Validation passes without OpenCV contrib install.
    DICT_4X4_50 = object()


class _DummyCv2:
    # Expose the stubbed aruco namespace expected by calibration.config.
    aruco = _DummyAruco()


def _load_payload() -> dict:
    # Use the real config as a baseline so tests follow current defaults.
    config_path = Path(__file__).resolve().parents[1] / "calibration_config.json"
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


class CalibrationConfigValidationTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {test_name}: {message}")

    def test_valid_config_passes_validation(self) -> None:
        # Validates that the shipped calibration_config.json is internally consistent.
        # This guards against accidental config edits that would break calibration startup.
        payload = _load_payload()
        with mock.patch("calibration.config.cv2", _DummyCv2()):
            try:
                config = CalibrationConfig.from_dict(payload)
                config.validate()
            except Exception as exc:
                self._report("valid_config", False, f"unexpected validation error: {exc}")
                self.fail(f"Unexpected validation error: {exc}")
            else:
                self._report(
                    "valid_config",
                    True,
                    "check=baseline config validates without errors",
                    "source=calibration_config.json",
                )

    def test_rejects_invalid_world_origin(self) -> None:
        # Ensures only the supported world origin is accepted (currently cube_center).
        # This prevents downstream pose math from silently using an unsupported frame.
        payload = _load_payload()
        payload["world_origin"] = "camera_center"
        with mock.patch("calibration.config.cv2", _DummyCv2()):
            with self.assertRaises(ValueError) as context:
                CalibrationConfig.from_dict(payload)
            self._report(
                "invalid_world_origin",
                True,
                "check=reject unsupported world_origin",
                f"error={context.exception}",
            )

    def test_rejects_duplicate_face_ids(self) -> None:
        # Face IDs identify ArUco markers on the cube; duplicates make faces ambiguous.
        # The config validator must reject duplicates to avoid mis-association.
        payload = _load_payload()
        payload["face_ids"]["right"] = 0
        with mock.patch("calibration.config.cv2", _DummyCv2()):
            with self.assertRaises(ValueError) as context:
                CalibrationConfig.from_dict(payload)
            self._report(
                "duplicate_face_ids",
                True,
                "check=reject duplicate cube face IDs",
                f"error={context.exception}",
            )

    def test_rejects_marker_larger_than_cube(self) -> None:
        # A marker cannot be physically larger than the cube face.
        # This prevents impossible geometry from entering the calibration pipeline.
        payload = _load_payload()
        payload["cube"]["marker_length"] = 0.25
        payload["cube"]["cube_length"] = 0.20
        with mock.patch("calibration.config.cv2", _DummyCv2()):
            with self.assertRaises(ValueError) as context:
                CalibrationConfig.from_dict(payload)
            self._report(
                "marker_larger_than_cube",
                True,
                "check=reject marker larger than cube",
                f"error={context.exception}",
            )


class CalibrationQualityAcceptanceTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {test_name}: {message}")

    def test_calibration_quality_acceptance(self) -> None:
        # Uses real calibration output JSON to verify quality metrics against thresholds
        # from calibration_config.json (translation std, rotation std, success rate).
        root = Path(__file__).resolve().parents[2]
        final_path = root / "calib_out" / "final_calibration.json"
        frames_path = root / "calib_out" / "per_frame_estimates.json"

        if not final_path.exists() or not frames_path.exists():
            self._report(
                "calibration_quality_acceptance",
                True,
                "check=skip when calibration outputs missing",
                "missing=calib_out/final_calibration.json or per_frame_estimates.json",
            )
            self.skipTest("Calibration output JSON not found")

        config_payload = _load_payload()
        quality_defaults = QualityConfig()
        quality_payload = config_payload.get("quality", {}) if isinstance(config_payload.get("quality"), dict) else {}
        translation_threshold_m = float(quality_payload.get("max_translation_std_m", quality_defaults.max_translation_std_m))
        rotation_threshold_deg = float(quality_payload.get("max_rotation_std_deg", quality_defaults.max_rotation_std_deg))

        frame_count = int(config_payload.get("frame_count", 60))
        min_valid_frames = int(quality_payload.get("min_valid_frames_per_camera", quality_defaults.min_valid_frames_per_camera))
        success_rate_threshold = min_valid_frames / max(1, frame_count)

        final_data = _load_json(final_path)
        frame_data = _load_json(frames_path)

        cameras = final_data.get("cameras", [])
        frame_cameras = {cam.get("camera_id"): cam.get("frames", []) for cam in frame_data.get("cameras", [])}

        threshold_msg = (
            f"thresholds: translation_std<={translation_threshold_m * 1000.0:.2f}mm, "
            f"rotation_std<={rotation_threshold_deg:.3f}deg, "
            f"success_rate>={success_rate_threshold * 100.0:.1f}%"
        )
        self._report(
            "calibration_quality_thresholds",
            True,
            "check=thresholds derived from config quality settings",
            threshold_msg,
        )

        for camera in cameras:
            camera_id = camera.get("camera_id")
            metrics = camera.get("quality_metrics", {}) or {}
            translation_std_m = metrics.get("translation_std_m")
            rotation_std_deg = metrics.get("rotation_std_deg")

            frames = frame_cameras.get(camera_id, [])
            if not frames:
                self._report(
                    f"{camera_id}_success_rate",
                    False,
                    "check=per-frame data required for success rate",
                    "error=missing per-frame data",
                )
                self.fail(f"Missing per-frame data for camera {camera_id}")

            total = len(frames)
            success_frames = sum(1 for frame in frames if frame.get("success"))
            success_rate = success_frames / max(1, total)

            if translation_std_m is None or rotation_std_deg is None:
                self._report(
                    f"{camera_id}_metrics",
                    False,
                    "check=quality metrics required",
                    "error=missing translation/rotation std",
                )
                self.fail(f"Missing metrics for camera {camera_id}")

            translation_ok = float(translation_std_m) <= translation_threshold_m
            rotation_ok = float(rotation_std_deg) <= rotation_threshold_deg
            success_ok = success_rate >= success_rate_threshold

            translation_mm = float(translation_std_m) * 1000.0
            self._report(
                f"{camera_id}_overall",
                translation_ok and rotation_ok and success_ok,
                "check=per-camera quality vs thresholds",
                f"translation_std={translation_mm:.3f}mm (max={translation_threshold_m * 1000.0:.3f}mm)",
                f"rotation_std={float(rotation_std_deg):.4f}deg (max={rotation_threshold_deg:.4f}deg)",
                f"success_rate={success_rate * 100.0:.1f}% ({success_frames}/{total} frames) (min={success_rate_threshold * 100.0:.1f}%)",
            )

            self.assertTrue(translation_ok, f"{camera_id} translation std above threshold")
            self.assertTrue(rotation_ok, f"{camera_id} rotation std above threshold")
            self.assertTrue(success_ok, f"{camera_id} success rate below threshold")


if __name__ == "__main__":
    unittest.main()
