from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager, RawFrameSnapshot


@dataclass
class CaptureResult:
    file_path: Path
    preview_image_path: Path
    file_name: str
    preview_image_name: str
    points_total: int
    points_per_camera: dict[str, int]
    cameras_used: list[str]
    skipped_cameras: dict[str, str]


class VolumetricCaptureService:
    def __init__(
        self,
        camera_manager: CameraStreamManager,
        calibration_store: CalibrationStore,
        output_dir: Path,
        depth_scale_m: float = 0.001,
        depth_min_m: float = 0.2,
        depth_max_m: float = 5.0,
        pixel_step: int = 4,
    ) -> None:
        self._camera_manager = camera_manager
        self._calibration_store = calibration_store
        self._output_dir = output_dir
        self._depth_scale_m = float(depth_scale_m)
        self._depth_min_m = float(depth_min_m)
        self._depth_max_m = float(depth_max_m)
        self._pixel_step = max(1, int(pixel_step))

    def capture_once(
        self,
        camera_ids: list[str] | None = None,
        pixel_step: int | None = None,
        depth_min_m: float | None = None,
        depth_max_m: float | None = None,
    ) -> CaptureResult:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        selected_camera_ids = camera_ids or self._camera_manager.camera_ids()
        pixel_step_value = max(1, int(pixel_step if pixel_step is not None else self._pixel_step))
        depth_min_value = float(self._depth_min_m if depth_min_m is None else depth_min_m)
        depth_max_value = float(self._depth_max_m if depth_max_m is None else depth_max_m)
        all_points_world: list[np.ndarray] = []
        all_colors: list[np.ndarray] = []
        points_per_camera: dict[str, int] = {}
        cameras_used: list[str] = []
        skipped_cameras: dict[str, str] = {}
        stats = {
            "no_calibration": 0,
            "no_depth_frame": 0,
            "no_intrinsics": 0,
            "no_points_after_filter": 0,
        }

        for camera_id in selected_camera_ids:
            world_points, colors, skip_reason = self._capture_world_points_for_camera(
                camera_id,
                pixel_step=pixel_step_value,
                depth_min_m=depth_min_value,
                depth_max_m=depth_max_value,
                stats=stats,
            )
            if world_points is None or colors is None:
                if skip_reason is not None:
                    skipped_cameras[camera_id] = skip_reason
                continue

            all_points_world.append(world_points)
            all_colors.append(colors)
            points_per_camera[camera_id] = int(world_points.shape[0])
            cameras_used.append(camera_id)

        if not all_points_world:
            raise ValueError(self._build_empty_capture_message(selected_camera_ids, stats))

        stacked_points = np.vstack(all_points_world)
        stacked_colors = np.vstack(all_colors)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        ply_path = self._output_dir / f"volumetric_capture_{timestamp}.ply"
        preview_path = self._output_dir / f"volumetric_capture_{timestamp}_preview.png"

        self._write_ply(ply_path, stacked_points, stacked_colors)
        self._write_preview(preview_path, stacked_points, stacked_colors)

        return CaptureResult(
            file_path=ply_path,
            preview_image_path=preview_path,
            file_name=ply_path.name,
            preview_image_name=preview_path.name,
            points_total=int(stacked_points.shape[0]),
            points_per_camera=points_per_camera,
            cameras_used=sorted(cameras_used),
            skipped_cameras=skipped_cameras,
        )

    def _capture_world_points_for_camera(
        self,
        camera_id: str,
        *,
        pixel_step: int,
        depth_min_m: float,
        depth_max_m: float,
        stats: dict[str, int],
    ) -> tuple[np.ndarray | None, np.ndarray | None, str | None]:
        extrinsics = self._calibration_store.get(camera_id)
        if extrinsics is None:
            stats["no_calibration"] += 1
            return None, None, f"{camera_id}: missing calibration entry"

        frame = self._camera_manager.get_latest_raw_snapshot(camera_id, require_depth=True)
        if frame is None:
            frame = self._camera_manager.capture_raw_frame(
                camera_id,
                require_depth=True,
                timeout_ms=600,
                max_attempts=12,
            )
        if frame is None or frame.depth is None:
            stats["no_depth_frame"] += 1
            return None, None, f"{camera_id}: depth frame unavailable"

        intrinsics = self._depth_intrinsics_for_frame(camera_id, frame)
        if intrinsics is None:
            stats["no_intrinsics"] += 1
            return None, None, f"{camera_id}: intrinsics unavailable"

        color_intrinsics = self._camera_manager.intrinsics(camera_id)
        depth_to_color = self._camera_manager.depth_to_color_transform(camera_id)

        depth_points = self._depth_to_camera_points(
            frame,
            intrinsics,
            pixel_step=pixel_step,
            depth_min_m=depth_min_m,
            depth_max_m=depth_max_m,
        )
        if depth_points.size == 0:
            stats["no_points_after_filter"] += 1
            return None, None, f"{camera_id}: no valid points after depth filter"

        color_camera_points = self._depth_camera_to_color_camera(depth_points, depth_to_color)
        colors = self._sample_colors_from_projection(frame, color_camera_points, color_intrinsics)
        world_points = self._camera_to_world(color_camera_points, extrinsics.t_camera_world)
        return world_points, colors, None

    @staticmethod
    def _build_empty_capture_message(selected_camera_ids: list[str], stats: dict[str, int]) -> str:
        return (
            "No depth points captured. "
            f"selected={len(selected_camera_ids)} "
            f"no_calibration={stats['no_calibration']} "
            f"no_depth_frame={stats['no_depth_frame']} "
            f"no_intrinsics={stats['no_intrinsics']} "
            f"no_points_after_filter={stats['no_points_after_filter']}. "
            "Ensure CAMERA_USE_DEPTH=true and tune depth_min_m/depth_max_m if needed."
        )

    def _depth_intrinsics_for_frame(self, camera_id: str, frame: RawFrameSnapshot) -> np.ndarray | None:
        if frame.depth is None:
            return None

        depth_intrinsics = self._camera_manager.depth_intrinsics(camera_id)
        if depth_intrinsics is not None:
            return np.asarray(depth_intrinsics, dtype=np.float64)

        intrinsics = self._camera_manager.intrinsics(camera_id)
        if intrinsics is None:
            return None

        depth_height, depth_width = frame.depth.shape[:2]
        k = np.asarray(intrinsics, dtype=np.float64).copy()

        current_width = float(max(1.0, 2.0 * k[0, 2]))
        current_height = float(max(1.0, 2.0 * k[1, 2]))
        scale_x = float(depth_width) / current_width
        scale_y = float(depth_height) / current_height

        k[0, 0] *= scale_x
        k[1, 1] *= scale_y
        k[0, 2] *= scale_x
        k[1, 2] *= scale_y
        return k

    def _depth_to_camera_points(
        self,
        frame: RawFrameSnapshot,
        intrinsics: np.ndarray,
        *,
        pixel_step: int,
        depth_min_m: float,
        depth_max_m: float,
    ) -> np.ndarray:
        depth = np.asarray(frame.depth, dtype=np.uint16)
        if depth.size == 0:
            return np.empty((0, 3), dtype=np.float64)

        depth_scale_m = float(frame.depth_scale_m) if frame.depth_scale_m is not None else self._depth_scale_m
        if depth_scale_m <= 0.0:
            depth_scale_m = self._depth_scale_m

        sampled = depth[:: pixel_step, :: pixel_step]
        valid = sampled > 0
        if not np.any(valid):
            return np.empty((0, 3), dtype=np.float64)

        z = sampled.astype(np.float64) * depth_scale_m
        valid &= z >= depth_min_m
        valid &= z <= depth_max_m
        if not np.any(valid):
            return np.empty((0, 3), dtype=np.float64)

        rows, cols = np.nonzero(valid)
        cols = cols.astype(np.float64)
        rows = rows.astype(np.float64)
        z_values = z[valid]

        fx = float(intrinsics[0, 0])
        fy = float(intrinsics[1, 1])
        cx = float(intrinsics[0, 2]) / float(pixel_step)
        cy = float(intrinsics[1, 2]) / float(pixel_step)

        x_values = (cols - cx) * z_values / fx * float(pixel_step)
        y_values = (rows - cy) * z_values / fy * float(pixel_step)

        points = np.column_stack([x_values, y_values, z_values]).astype(np.float64)
        return points

    def _sample_colors_from_projection(
        self,
        frame: RawFrameSnapshot,
        color_camera_points: np.ndarray,
        intrinsics: np.ndarray | None,
    ) -> np.ndarray:
        point_count = int(color_camera_points.shape[0])
        if point_count <= 0:
            return np.empty((0, 3), dtype=np.uint8)
        if frame.color is None:
            return np.full((point_count, 3), 180, dtype=np.uint8)
        if intrinsics is None:
            return np.full((point_count, 3), 180, dtype=np.uint8)

        color = frame.color
        if color.ndim != 3 or color.shape[2] != 3:
            return np.full((point_count, 3), 180, dtype=np.uint8)

        fx = float(intrinsics[0, 0])
        fy = float(intrinsics[1, 1])
        cx = float(intrinsics[0, 2])
        cy = float(intrinsics[1, 2])

        x = color_camera_points[:, 0]
        y = color_camera_points[:, 1]
        z = color_camera_points[:, 2]

        colors = np.full((point_count, 3), 180, dtype=np.uint8)
        valid_z = z > 1e-6
        if not np.any(valid_z):
            return colors

        u = np.round((x[valid_z] * fx / z[valid_z]) + cx).astype(np.int32)
        v = np.round((y[valid_z] * fy / z[valid_z]) + cy).astype(np.int32)

        in_bounds = (u >= 0) & (u < color.shape[1]) & (v >= 0) & (v < color.shape[0])
        if np.any(in_bounds):
            valid_indices = np.nonzero(valid_z)[0]
            point_indices = valid_indices[in_bounds]
            colors[point_indices] = color[v[in_bounds], u[in_bounds]].astype(np.uint8)

        return colors

    @staticmethod
    def _depth_camera_to_color_camera(depth_points: np.ndarray, depth_to_color: np.ndarray | None) -> np.ndarray:
        if depth_to_color is None:
            return depth_points

        transform = np.asarray(depth_to_color, dtype=np.float64)
        if transform.shape != (4, 4):
            return depth_points

        rotation = transform[:3, :3]
        translation = transform[:3, 3]
        return (depth_points @ rotation.T) + translation

    @staticmethod
    def _camera_to_world(camera_points: np.ndarray, t_camera_world: np.ndarray) -> np.ndarray:
        t_world_camera = np.linalg.inv(np.asarray(t_camera_world, dtype=np.float64))
        rotation = t_world_camera[:3, :3]
        translation = t_world_camera[:3, 3]
        return (camera_points @ rotation.T) + translation

    @staticmethod
    def _write_ply(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
        with path.open("w", encoding="utf-8") as handle:
            handle.write("ply\n")
            handle.write("format ascii 1.0\n")
            handle.write(f"element vertex {points.shape[0]}\n")
            handle.write("property float x\n")
            handle.write("property float y\n")
            handle.write("property float z\n")
            handle.write("property uchar red\n")
            handle.write("property uchar green\n")
            handle.write("property uchar blue\n")
            handle.write("end_header\n")
            for idx in range(points.shape[0]):
                x, y, z = points[idx]
                b, g, r = colors[idx]
                handle.write(f"{x:.6f} {y:.6f} {z:.6f} {int(r)} {int(g)} {int(b)}\n")

    @staticmethod
    def _write_preview(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
        width = 900
        height = 900
        padding = 40

        canvas = np.full((height, width, 3), 18, dtype=np.uint8)
        xy = points[:, :2]

        mins = xy.min(axis=0)
        maxs = xy.max(axis=0)
        span = np.maximum(maxs - mins, 1e-6)

        normalized = (xy - mins) / span
        px = (padding + normalized[:, 0] * (width - 2 * padding)).astype(np.int32)
        py = (padding + normalized[:, 1] * (height - 2 * padding)).astype(np.int32)
        py = height - py

        for x_coord, y_coord, color in zip(px, py, colors, strict=False):
            b, g, r = color
            cv2.circle(canvas, (int(x_coord), int(y_coord)), 1, (int(b), int(g), int(r)), thickness=-1)

        cv2.imwrite(str(path), canvas)
