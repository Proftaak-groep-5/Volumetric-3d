from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np
import numpy.typing as npt

from calibration.calibration.detector import MarkerDetection
from calibration.calibration.pose_estimation import FrameCubePoseEstimate
from calibration.camera.base import CameraIntrinsics
from calibration.math3d.transforms import transform_to_rvec_tvec


@dataclass
class DistanceOverlayMetrics:
    depth_distance_m: Optional[float] = None
    image_distance_m: Optional[float] = None
    marker_surface_distance_m: Optional[float] = None
    marker_center_guess_distance_m: Optional[float] = None
    distance_delta_m: Optional[float] = None
    distance_consistent: Optional[bool] = None


class DebugVisualizer:
    def __init__(
        self,
        enabled: bool,
        show_windows: bool,
        save_images: bool,
        output_dir: Path,
        image_format: str = "jpg",
    ) -> None:
        self._enabled = bool(enabled)
        self._show_windows = bool(show_windows)
        self._save_images = bool(save_images)
        self._output_dir = output_dir
        self._image_format = image_format.lower().strip(".")

        if self._enabled and self._save_images:
            self._output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def render_frame(
        self,
        camera_id: str,
        frame_index: int,
        image_bgr: npt.NDArray[np.uint8],
        detections: Sequence[MarkerDetection],
        frame_pose: Optional[FrameCubePoseEstimate],
        intrinsics: CameraIntrinsics,
        marker_axis_length: float,
        cube_axis_length: float,
        distance_metrics: Optional[DistanceOverlayMetrics] = None,
    ) -> None:
        if not self._enabled:
            return

        annotated = image_bgr.copy()

        marker_corners = [
            np.asarray(det.corners, dtype=np.float32).reshape(1, 4, 2)
            for det in detections
            if det.corners is not None
        ]
        marker_ids = [int(det.marker_id) for det in detections if det.corners is not None]

        if marker_corners and hasattr(cv2, "aruco"):
            cv2.aruco.drawDetectedMarkers(
                annotated,
                marker_corners,
                np.asarray(marker_ids, dtype=np.int32).reshape(-1, 1),
            )

        for detection in detections:
            cv2.drawFrameAxes(
                annotated,
                intrinsics.camera_matrix,
                intrinsics.dist_coeffs,
                np.asarray(detection.rvec, dtype=np.float64).reshape(3, 1),
                np.asarray(detection.tvec, dtype=np.float64).reshape(3, 1),
                float(marker_axis_length),
                2,
            )

        if frame_pose is not None:
            cube_rvec, cube_tvec = transform_to_rvec_tvec(frame_pose.t_camera_cube)
            cv2.drawFrameAxes(
                annotated,
                intrinsics.camera_matrix,
                intrinsics.dist_coeffs,
                cube_rvec.reshape(3, 1),
                cube_tvec.reshape(3, 1),
                float(cube_axis_length),
                3,
            )
            cv2.putText(
                annotated,
                f"cube_pose markers={frame_pose.used_observation_count}/{frame_pose.total_observation_count}",
                (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (40, 220, 40),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                annotated,
                f"reproj={frame_pose.mean_reprojection_error_px:.2f}px",
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (220, 220, 220),
                2,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                annotated,
                "cube_pose unavailable",
                (20, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (30, 120, 255),
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            annotated,
            f"camera={camera_id} frame={frame_index}",
            (20, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )

        self._draw_distance_metrics(annotated, distance_metrics)

        if self._save_images:
            camera_dir = self._output_dir / camera_id
            camera_dir.mkdir(parents=True, exist_ok=True)
            output_path = camera_dir / f"frame_{frame_index:06d}.{self._image_format}"
            cv2.imwrite(str(output_path), annotated)

        if self._show_windows:
            cv2.imshow(f"Calibration Debug - {camera_id}", annotated)
            cv2.waitKey(1)

    def close(self) -> None:
        if self._show_windows:
            cv2.destroyAllWindows()

    @staticmethod
    def _draw_distance_metrics(
        annotated: npt.NDArray[np.uint8],
        distance_metrics: Optional[DistanceOverlayMetrics],
    ) -> None:
        if distance_metrics is None:
            return

        lines: list[tuple[str, tuple[int, int, int]]] = []
        if distance_metrics.image_distance_m is not None:
            lines.append((f"image_dist={distance_metrics.image_distance_m:.3f}m", (220, 220, 220)))
        if distance_metrics.depth_distance_m is not None:
            lines.append((f"depth_dist={distance_metrics.depth_distance_m:.3f}m", (220, 220, 220)))
        if distance_metrics.marker_surface_distance_m is not None:
            lines.append((f"marker_surface={distance_metrics.marker_surface_distance_m:.3f}m", (220, 220, 220)))
        if distance_metrics.marker_center_guess_distance_m is not None:
            lines.append((f"marker_guess_center={distance_metrics.marker_center_guess_distance_m:.3f}m", (220, 220, 220)))
        if distance_metrics.distance_delta_m is not None:
            color = (40, 220, 40) if distance_metrics.distance_consistent is not False else (30, 120, 255)
            label = "ok" if distance_metrics.distance_consistent is not False else "mismatch"
            lines.append((f"dist_delta={distance_metrics.distance_delta_m:.3f}m [{label}]", color))

        y = 118
        for text, color in lines:
            cv2.putText(
                annotated,
                text,
                (20, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )
            y += 28

