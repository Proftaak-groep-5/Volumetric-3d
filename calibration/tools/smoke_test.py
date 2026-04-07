from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from calibration.calibration.aruco_compat import draw_detected_markers
from calibration.calibration.detector import ArucoMarkerDetector
from calibration.camera.femto_bolt import discover_femto_bolt_cameras
from calibration.config import CalibrationConfig, load_config

LOGGER = logging.getLogger(__name__)


@dataclass
class SmokeTestResult:
    success: bool
    mode: str
    camera_id: str
    marker_ids: list[int]
    raw_frame_path: Path
    depth_frame_path: Optional[Path]
    debug_image_path: Path
    calculated_cube_distance_m: Optional[float] = None
    measured_cube_distance_m: Optional[float] = None
    cube_distance_error_m: Optional[float] = None


def _estimate_depth_surface_distance_m(
    frame_depth: Optional[np.ndarray],
    detections: Sequence[any],
    color_shape: tuple[int, int],
) -> Optional[float]:
    if frame_depth is None or frame_depth.ndim != 2:
        return None
    if not detections:
        return None

    height, width = frame_depth.shape
    color_h, color_w = int(color_shape[0]), int(color_shape[1])
    if color_w <= 0 or color_h <= 0:
        return None

    scale_x = float(width) / float(color_w)
    scale_y = float(height) / float(color_h)
    sampled_mm: list[float] = []
    for detection in detections:
        sampled_mm.extend(
            _sample_detection_depth_mm(
                frame_depth=frame_depth,
                width=width,
                height=height,
                detection=detection,
                scale_x=scale_x,
                scale_y=scale_y,
            )
        )

    if not sampled_mm:
        return None

    return float(np.median(np.asarray(sampled_mm, dtype=np.float64)) / 1000.0)


def _estimate_marker_surface_distance_m(detections: Sequence[any]) -> Optional[float]:
    if not detections:
        return None

    # Use camera-forward Z as surface distance estimate (more stable for frontal setups).
    distances_m: list[float] = []
    for detection in detections:
        tvec = getattr(detection, "tvec", None)
        if tvec is None:
            continue
        tvec_arr = np.asarray(tvec, dtype=np.float64).reshape(3)
        if float(tvec_arr[2]) > 0:
            distances_m.append(float(tvec_arr[2]))

    if not distances_m:
        return None

    return float(np.median(np.asarray(distances_m, dtype=np.float64)))


def _sample_detection_depth_mm(
    frame_depth: np.ndarray,
    width: int,
    height: int,
    detection: any,
    scale_x: float,
    scale_y: float,
) -> list[float]:
    corners = getattr(detection, "corners", None)
    if corners is None:
        return []

    points = np.asarray(corners, dtype=np.float64).reshape(-1, 2)
    if points.size == 0:
        return []

    center = np.mean(points, axis=0)
    points_with_center = np.vstack([points, center])
    sampled_mm: list[float] = []

    for x_f, y_f in points_with_center:
        x_i = int(round(float(x_f) * scale_x))

        y_i = int(round(float(y_f) * scale_y))
        if x_i < 0 or y_i < 0 or x_i >= width or y_i >= height:
            continue

        # Use a small neighborhood to tolerate depth holes and slight color-depth misalignment.
        x0 = max(0, x_i - 2)
        x1 = min(width - 1, x_i + 2)
        y0 = max(0, y_i - 2)
        y1 = min(height - 1, y_i + 2)
        patch = frame_depth[y0 : y1 + 1, x0 : x1 + 1]
        if patch.size == 0:
            continue
        valid_patch = patch[patch > 0]
        if valid_patch.size == 0:
            continue
        sampled_mm.append(float(np.median(valid_patch.astype(np.float64))))

    return sampled_mm


def _build_smoke_result(
    mode: str,
    camera_id: str,
    marker_ids: list[int],
    raw_frame_path: Path,
    depth_frame_path: Optional[Path],
    debug_image_path: Path,
    calculated_cube_distance_m: Optional[float] = None,
    measured_cube_distance_m: Optional[float] = None,
    cube_distance_error_m: Optional[float] = None,
) -> SmokeTestResult:
    return SmokeTestResult(
        success=True,
        mode=mode,
        camera_id=camera_id,
        marker_ids=marker_ids,
        raw_frame_path=raw_frame_path,
        depth_frame_path=depth_frame_path,
        debug_image_path=debug_image_path,
        calculated_cube_distance_m=calculated_cube_distance_m,
        measured_cube_distance_m=measured_cube_distance_m,
        cube_distance_error_m=cube_distance_error_m,
    )


def _depth_to_visual(depth_frame: np.ndarray) -> np.ndarray:
    valid = depth_frame[depth_frame > 0]
    if valid.size == 0:
        return np.zeros((depth_frame.shape[0], depth_frame.shape[1], 3), dtype=np.uint8)

    near = float(np.percentile(valid, 5))
    far = float(np.percentile(valid, 95))
    if far <= near:
        far = near + 1.0

    clipped = np.clip(depth_frame.astype(np.float32), near, far)
    normalized = ((clipped - near) / (far - near) * 255.0).astype(np.uint8)
    return cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)


def _draw_distance_lines(
    debug_image: np.ndarray,
    calculated_cube_distance_m: Optional[float],
    measured_cube_distance_m: Optional[float],
    cube_distance_error_m: Optional[float],
) -> None:
    if calculated_cube_distance_m is not None:
        cv2.putText(
            debug_image,
            f"calculated_cube_dist={calculated_cube_distance_m:.3f}m",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
    if measured_cube_distance_m is not None:
        cv2.putText(
            debug_image,
            f"measured_cube_dist={measured_cube_distance_m:.3f}m",
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
    if cube_distance_error_m is not None:
        cv2.putText(
            debug_image,
            f"cube_dist_error={cube_distance_error_m:.3f}m",
            (20, 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (40, 220, 40),
            2,
            cv2.LINE_AA,
        )


def _log_distance_summary(
    calculated_cube_distance_m: Optional[float],
    measured_cube_distance_m: Optional[float],
    cube_distance_error_m: Optional[float],
) -> None:
    LOGGER.info(
        "Distance summary: calculated_cube=%s measured_cube=%s error=%s",
        f"{calculated_cube_distance_m:.4f}m" if calculated_cube_distance_m is not None else "n/a",
        f"{measured_cube_distance_m:.4f}m" if measured_cube_distance_m is not None else "n/a",
        f"{cube_distance_error_m:.4f}m" if cube_distance_error_m is not None else "n/a",
    )


def _run_pose_stage(
    detector: ArucoMarkerDetector,
    marker_observations,
    intrinsics,
    config: CalibrationConfig,
    frame,
    debug_image: np.ndarray,
    camera_id: str,
    mode: str,
    raw_frame_path: Path,
    depth_frame_path: Optional[Path],
    debug_image_path: Path,
    show_windows: bool,
) -> SmokeTestResult:
    detections = detector.estimate_marker_poses(
        marker_observations=marker_observations,
        intrinsics=intrinsics,
        max_reprojection_error_px=config.quality.max_reprojection_error_px,
    )

    if len(detections) == 0:
        raise RuntimeError(
            "Marker(s) were detected but pose estimation failed. "
            "Check camera intrinsics, marker length in config, and frame/intrinsics resolution alignment."
        )

    for detection in detections:
        LOGGER.info(
            "Pose marker=%s method=%s rvec=%s tvec=%s reproj_error_px=%.4f",
            detection.marker_id,
            detection.pose_method,
            detection.rvec.tolist(),
            detection.tvec.tolist(),
            detection.reprojection_error_px,
        )
        cv2.drawFrameAxes(
            debug_image,
            intrinsics.camera_matrix,
            intrinsics.dist_coeffs,
            detection.rvec.reshape(3, 1),
            detection.tvec.reshape(3, 1),
            float(config.cube.marker_length),
            2,
        )

    half_cube = float(config.cube.cube_length) / 2.0
    marker_surface_distance_m = _estimate_marker_surface_distance_m(detections)
    color_shape = tuple(frame.color.shape[:2]) if frame.color is not None else (0, 0)
    depth_surface_distance_m = _estimate_depth_surface_distance_m(frame.depth, detections, color_shape)

    marker_norm_distance_m = float(
        np.median([np.linalg.norm(np.asarray(det.tvec, dtype=np.float64).reshape(3)) for det in detections])
    )

    if frame.depth is not None and frame.color is not None:
        LOGGER.info(
            "Depth sampling map: color=%sx%s depth=%sx%s",
            frame.color.shape[1],
            frame.color.shape[0],
            frame.depth.shape[1],
            frame.depth.shape[0],
        )

    LOGGER.info(
        "Marker distance diagnostics: surface_z=%s surface_norm=%s",
        f"{marker_surface_distance_m:.4f}m" if marker_surface_distance_m is not None else "n/a",
        f"{marker_norm_distance_m:.4f}m",
    )

    calculated_cube_distance_m = marker_surface_distance_m + half_cube if marker_surface_distance_m is not None else None
    measured_cube_distance_m = depth_surface_distance_m + half_cube if depth_surface_distance_m is not None else None
    cube_distance_error_m = None
    if calculated_cube_distance_m is not None and measured_cube_distance_m is not None:
        cube_distance_error_m = abs(calculated_cube_distance_m - measured_cube_distance_m)

    _draw_distance_lines(
        debug_image=debug_image,
        calculated_cube_distance_m=calculated_cube_distance_m,
        measured_cube_distance_m=measured_cube_distance_m,
        cube_distance_error_m=cube_distance_error_m,
    )
    _log_distance_summary(
        calculated_cube_distance_m=calculated_cube_distance_m,
        measured_cube_distance_m=measured_cube_distance_m,
        cube_distance_error_m=cube_distance_error_m,
    )

    _save_image(debug_image_path, debug_image)
    LOGGER.info("Saved pose-debug image: %s", debug_image_path)

    if show_windows:
        cv2.imshow("smoke_test_pose", debug_image)
        cv2.waitKey(1)

    return _build_smoke_result(
        mode=mode,
        camera_id=camera_id,
        marker_ids=[d.marker_id for d in detections],
        raw_frame_path=raw_frame_path,
        depth_frame_path=depth_frame_path,
        debug_image_path=debug_image_path,
        calculated_cube_distance_m=calculated_cube_distance_m,
        measured_cube_distance_m=measured_cube_distance_m,
        cube_distance_error_m=cube_distance_error_m,
    )


def _save_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image)
    if not ok:
        raise RuntimeError(f"Failed to write image to: {path}")


def _capture_color_frame(camera, max_retries: int, require_depth: bool = False) -> any:
    for attempt in range(1, max_retries + 1):
        frame = camera.get_frame(timeout_ms=1500)
        if frame is None:
            LOGGER.debug("Frame attempt %s/%s: no frame", attempt, max_retries)
            continue
        if frame.color is None:
            LOGGER.debug("Frame attempt %s/%s: no color payload", attempt, max_retries)
            continue
        if require_depth and frame.depth is None:
            LOGGER.debug("Frame attempt %s/%s: no depth payload", attempt, max_retries)
            continue

        if frame.color.ndim != 3 or frame.color.shape[2] not in (3, 4):
            raise RuntimeError(
                f"Unsupported frame resolution/format: shape={frame.color.shape}. Expected HxWx3 or HxWx4 color frame"
            )

        return frame

    raise RuntimeError(
        f"Failed to capture a valid {'color+depth' if require_depth else 'color'} frame after {max_retries} attempts. "
        "Check USB bandwidth, camera stream profile, and SDK health."
    )


def run_single_camera_smoke_test(
    config: CalibrationConfig,
    mode: str,
    output_dir: Path,
    max_frame_retries: int = 30,
    debug: bool = False,
    show_windows: bool = False,
) -> SmokeTestResult:
    if mode not in {"full", "frame", "detect", "pose"}:
        raise ValueError(f"Unsupported smoke test mode: {mode}")

    cameras = discover_femto_bolt_cameras(
        color_resolution=config.color_resolution,
        fps=config.fps,
        max_cameras=1,
        use_depth=True,
        allowed_camera_ids=config.camera_ids,
        camera_tuning=config.camera.to_dict(),
    )
    if not cameras:
        raise RuntimeError(
            "No Orbbec Femto Bolt camera found. Connect one camera and verify pyorbbecsdk can enumerate devices."
        )

    camera = cameras[0]
    detector = ArucoMarkerDetector(
        dictionary_id=config.aruco_dictionary_id(),
        marker_length=config.cube.marker_length,
        enable_diagnostics=debug,
    )

    raw_frame_path = output_dir / f"{camera.camera_id}_raw_color.png"
    depth_frame_path = output_dir / f"{camera.camera_id}_raw_depth.png"
    debug_image_path = output_dir / f"{camera.camera_id}_debug_{mode}.png"

    camera.start()
    try:
        intrinsics = camera.get_intrinsics()
        intrinsics.validate()

        LOGGER.info(
            "Smoke test using camera id=%s name=%s serial=%s",
            camera.camera_id,
            getattr(camera, "device_name", "unknown"),
            getattr(camera, "serial_number", "unknown"),
        )
        LOGGER.info("Intrinsics camera_matrix=\n%s", intrinsics.camera_matrix)
        LOGGER.info("Intrinsics dist_coeffs=%s", intrinsics.dist_coeffs.reshape(-1).tolist())

        frame = _capture_color_frame(
            camera=camera,
            max_retries=max_frame_retries,
            require_depth=mode in {"full", "pose"},
        )

        LOGGER.info(
            "Captured frame camera=%s index=%s shape=%s dtype=%s depth=%s",
            frame.camera_id,
            frame.frame_index,
            frame.color.shape,
            frame.color.dtype,
            "yes" if frame.depth is not None else "no",
        )

        _save_image(raw_frame_path, frame.color)
        LOGGER.info("Saved raw color frame: %s", raw_frame_path)

        saved_depth_path: Optional[Path] = None
        if frame.depth is not None:
            depth_visual = _depth_to_visual(frame.depth)
            _save_image(depth_frame_path, depth_visual)
            saved_depth_path = depth_frame_path
            LOGGER.info("Saved raw depth frame: %s", depth_frame_path)

        if mode == "frame":
            if show_windows:
                cv2.imshow("smoke_test_frame", frame.color)
                cv2.waitKey(1)
            return _build_smoke_result(
                mode=mode,
                camera_id=camera.camera_id,
                marker_ids=[],
                raw_frame_path=raw_frame_path,
                depth_frame_path=saved_depth_path,
                debug_image_path=debug_image_path,
            )

        marker_observations = detector.detect_markers_2d(frame)
        marker_ids = [obs.marker_id for obs in marker_observations]
        LOGGER.info("Detected marker IDs: %s", marker_ids)
        LOGGER.info("Detected corner sets: %s", len(marker_observations))

        if len(marker_observations) == 0:
            raise RuntimeError(
                "No ArUco markers detected in captured frame. "
                f"Verify dictionary={config.aruco_dict}, marker visibility, focus, and lighting."
            )

        debug_image = frame.color.copy()
        draw_detected_markers(
            image_bgr=debug_image,
            corners=[obs.corners for obs in marker_observations],
            ids=marker_ids,
        )

        if mode == "detect":
            _save_image(debug_image_path, debug_image)
            LOGGER.info("Saved marker-debug image: %s", debug_image_path)
            if show_windows:
                cv2.imshow("smoke_test_detect", debug_image)
                cv2.waitKey(1)
            return _build_smoke_result(
                mode=mode,
                camera_id=camera.camera_id,
                marker_ids=marker_ids,
                raw_frame_path=raw_frame_path,
                depth_frame_path=saved_depth_path,
                debug_image_path=debug_image_path,
            )

        return _run_pose_stage(
            detector=detector,
            marker_observations=marker_observations,
            intrinsics=intrinsics,
            config=config,
            frame=frame,
            debug_image=debug_image,
            camera_id=camera.camera_id,
            mode=mode,
            raw_frame_path=raw_frame_path,
            depth_frame_path=saved_depth_path,
            debug_image_path=debug_image_path,
            show_windows=show_windows,
        )
    finally:
        camera.stop()
        if show_windows:
            cv2.destroyAllWindows()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Single-camera real-hardware smoke test for Orbbec Femto Bolt")
    parser.add_argument("--config", type=Path, required=True, help="Path to calibration JSON config")
    parser.add_argument("--mode", type=str, default="full", choices=["full", "frame", "detect", "pose"], help="Smoke test stage")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output folder for smoke test images")
    parser.add_argument("--max-frame-retries", type=int, default=30, help="Maximum frame capture retries")
    parser.add_argument("--debug", action="store_true", help="Enable verbose diagnostics")
    parser.add_argument("--show-windows", action="store_true", help="Show OpenCV debug windows")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        config = load_config(args.config)
    except Exception as exc:
        LOGGER.error("Failed to load config '%s': %s", args.config, exc)
        return 2

    output_dir = Path(args.output_dir) if args.output_dir is not None else Path(config.output) / "smoke_test"

    try:
        result = run_single_camera_smoke_test(
            config=config,
            mode=args.mode,
            output_dir=output_dir,
            max_frame_retries=int(args.max_frame_retries),
            debug=bool(args.debug),
            show_windows=bool(args.show_windows),
        )
        LOGGER.info(
            "Smoke test succeeded mode=%s camera=%s markers=%s raw=%s depth=%s debug=%s calculated_cube=%s measured_cube=%s error=%s",
            result.mode,
            result.camera_id,
            result.marker_ids,
            result.raw_frame_path,
            result.depth_frame_path if result.depth_frame_path is not None else "n/a",
            result.debug_image_path,
            f"{result.calculated_cube_distance_m:.4f}m" if result.calculated_cube_distance_m is not None else "n/a",
            f"{result.measured_cube_distance_m:.4f}m" if result.measured_cube_distance_m is not None else "n/a",
            f"{result.cube_distance_error_m:.4f}m" if result.cube_distance_error_m is not None else "n/a",
        )
        return 0
    except Exception as exc:
        LOGGER.error("Smoke test failed: %s", exc)
        if args.debug:
            LOGGER.exception("Smoke test failure diagnostics")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

