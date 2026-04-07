from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from calibration.calibration.aruco_cube import ArucoCubeModel
from calibration.calibration.detector import ArucoMarkerDetector
from calibration.calibration.multi_camera_calibrator import MultiCameraCalibrator
from calibration.camera.base import CameraDevice
from calibration.camera.femto_bolt import discover_femto_bolt_cameras
from calibration.camera.mock_camera import create_mock_cameras
from calibration.config import CalibrationConfig, load_config
from calibration.io.export_json import export_calibration_results
from calibration.io.visualization import DebugVisualizer
from calibration.tools.smoke_test import run_single_camera_smoke_test

LOGGER = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Volumetric multi-camera calibration tool")
    parser.add_argument("--config", type=Path, required=True, help="Path to calibration JSON config")
    parser.add_argument("--debug", action="store_true", help="Enable debug overlays")
    parser.add_argument("--show-debug-windows", action="store_true", help="Show live OpenCV debug windows")
    parser.add_argument("--mock", action="store_true", help="Use mock cameras instead of Femto Bolt hardware")
    parser.add_argument("--mock-camera-count", type=int, default=3, help="Number of mock cameras (1..6)")
    parser.add_argument("--mock-seed", type=int, default=42, help="Random seed for mock camera simulation")
    parser.add_argument("--frame-count", type=int, default=None, help="Override number of calibration frames")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override output directory")
    parser.add_argument("--max-cameras", type=int, default=None, help="Override max camera count")
    parser.add_argument(
        "--single-camera-smoke-test",
        action="store_true",
        help="Run real-hardware smoke test for exactly one camera and exit",
    )
    parser.add_argument(
        "--smoke-test-mode",
        type=str,
        default="full",
        choices=["full", "frame", "detect", "pose"],
        help="Smoke test stage when --single-camera-smoke-test is enabled",
    )
    parser.add_argument(
        "--smoke-test-output-dir",
        type=Path,
        default=None,
        help="Override output folder for smoke test images",
    )
    parser.add_argument(
        "--smoke-test-max-frame-retries",
        type=int,
        default=30,
        help="Maximum frame capture retries for smoke test",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def apply_overrides(config: CalibrationConfig, args: argparse.Namespace) -> CalibrationConfig:
    if args.frame_count is not None:
        config.frame_count = int(args.frame_count)
    if args.output_dir is not None:
        config.output = Path(args.output_dir)
    if args.max_cameras is not None:
        config.max_cameras = int(args.max_cameras)

    if args.debug:
        config.debug.enabled = True

    if args.show_debug_windows:
        config.debug.enabled = True
        config.debug.show_windows = True

    config.validate()
    return config


def build_cameras(args: argparse.Namespace, config: CalibrationConfig, cube_model: ArucoCubeModel) -> list[CameraDevice]:
    if args.mock:
        camera_count = int(args.mock_camera_count)
        if camera_count < 1 or camera_count > 6:
            raise ValueError("--mock-camera-count must be in range 1..6")

        camera_count = min(camera_count, config.max_cameras)
        LOGGER.info("Using %s mock camera(s)", camera_count)

        return create_mock_cameras(
            camera_count=camera_count,
            cube_model=cube_model,
            color_resolution=config.color_resolution,
            fps=config.fps,
            seed=int(args.mock_seed),
        )

    cameras = discover_femto_bolt_cameras(
        color_resolution=config.color_resolution,
        fps=config.fps,
        max_cameras=config.max_cameras,
        use_depth=config.use_depth,
        allowed_camera_ids=config.camera_ids,
        camera_tuning=config.camera.to_dict(),
    )

    return list(cameras)


def load_and_prepare_config(args: argparse.Namespace) -> CalibrationConfig:
    config_path = args.config
    config = load_config(config_path)
    return apply_overrides(config, args)


def run_smoke_test_mode(args: argparse.Namespace, config: CalibrationConfig) -> int:
    smoke_output_dir = Path(args.smoke_test_output_dir) if args.smoke_test_output_dir else Path(config.output) / "smoke_test"
    try:
        result = run_single_camera_smoke_test(
            config=config,
            mode=args.smoke_test_mode,
            output_dir=smoke_output_dir,
            max_frame_retries=int(args.smoke_test_max_frame_retries),
            debug=bool(config.debug.enabled),
            show_windows=bool(config.debug.show_windows),
        )
        LOGGER.info(
            "Smoke test succeeded mode=%s camera=%s markers=%s raw=%s debug=%s",
            result.mode,
            result.camera_id,
            result.marker_ids,
            result.raw_frame_path,
            result.debug_image_path,
        )
        return 0
    except Exception as exc:
        LOGGER.error("Single-camera smoke test failed: %s", exc)
        if config.debug.enabled:
            LOGGER.exception("Smoke test failure diagnostics")
        return 2


def run_calibration_mode(args: argparse.Namespace, config: CalibrationConfig) -> int:
    cube_model = ArucoCubeModel(
        cube_length=config.cube.cube_length,
        marker_length=config.cube.marker_length,
        face_ids=config.face_ids,
    )

    detector = ArucoMarkerDetector(
        dictionary_id=config.aruco_dictionary_id(),
        marker_length=config.cube.marker_length,
        enable_diagnostics=bool(config.debug.enabled),
    )

    cameras = build_cameras(args=args, config=config, cube_model=cube_model)
    if not cameras:
        LOGGER.error("No cameras available for calibration")
        return 2

    output_dir = Path(config.output)
    debug_dir = output_dir / "debug"

    visualizer = DebugVisualizer(
        enabled=config.debug.enabled,
        show_windows=config.debug.show_windows,
        save_images=config.debug.save_images,
        output_dir=debug_dir,
        image_format=config.debug.image_format,
    )

    calibrator = MultiCameraCalibrator(
        config=config,
        cube_model=cube_model,
        detector=detector,
        cameras=cameras,
        visualizer=visualizer,
    )
    try:
        run_result = calibrator.run()
    except Exception as exc:
        LOGGER.error("Calibration runtime failed: %s", exc)
        if config.debug.enabled:
            LOGGER.exception("Calibration runtime diagnostics")
        return 2

    try:
        outputs = export_calibration_results(
            run_result=run_result,
            config=config,
            output_dir=output_dir,
        )
    except Exception as exc:
        LOGGER.error("Failed to export calibration output JSON: %s", exc)
        if config.debug.enabled:
            LOGGER.exception("Calibration export diagnostics")
        return 2

    LOGGER.info("Calibration finished: success=%s, failed=%s", run_result.successful_cameras, run_result.failed_cameras)
    LOGGER.info("Final calibration JSON: %s", outputs["final_calibration"])
    LOGGER.info("Per-frame estimates JSON: %s", outputs["per_frame_estimates"])

    for camera_result in run_result.camera_results:
        level = logging.INFO if camera_result.success else logging.WARNING
        LOGGER.log(level, "[%s] %s", camera_result.camera_id, camera_result.message)

    if run_result.successful_cameras == 0:
        return 2
    if run_result.failed_cameras > 0:
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        config = load_and_prepare_config(args)
    except Exception as exc:
        LOGGER.error("Failed to load/validate config '%s': %s", args.config, exc)
        return 2

    if args.single_camera_smoke_test:
        return run_smoke_test_mode(args, config)

    return run_calibration_mode(args, config)


if __name__ == "__main__":
    raise SystemExit(main())

