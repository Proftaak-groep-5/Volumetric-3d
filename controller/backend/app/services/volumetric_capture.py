from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path

import cv2
import numpy as np

from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager, RawFrameSnapshot


@dataclass
class CaptureConfig:
    """Configuration for volumetric capture processing."""
    camera_ids: list[str] | None = None
    frames_by_camera: dict[str, RawFrameSnapshot] | None = None
    pixel_step: int | None = None
    depth_min_m: float | None = None
    depth_max_m: float | None = None
    output_dir: Path | None = None
    file_stem: str | None = None
    write_preview: bool = True
    ply_binary: bool = False
    use_synchronized_snapshots: bool = True
    synchronized_max_skew_ms: float = 75.0
    synchronized_timeout_ms: int = 1200
    allow_direct_capture_fallback: bool = True
    apply_brightness_balance: bool = True
    voxel_size_m: float | None = 0.0075
    parallel_camera_processing: bool = False
    direct_capture_timeout_ms: int = 600
    direct_capture_max_attempts: int = 12
    sample_projected_color: bool = True
    direct_capture_prefer_depth_only: bool = False
    write_color: bool = True
    min_required_cameras: int = 1


@dataclass
class CaptureResult:
    file_path: Path
    preview_image_path: Path | None
    file_name: str
    preview_image_name: str | None
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
        depth_max_m: float = 2.0,
        pixel_step: int = 1,
    ) -> None:
        self._camera_manager = camera_manager
        self._calibration_store = calibration_store
        self._output_dir = output_dir
        self._depth_scale_m = float(depth_scale_m)
        self._depth_min_m = float(depth_min_m)
        self._depth_max_m = float(depth_max_m)
        self._pixel_step = max(1, int(pixel_step))
        mode = os.getenv("VOLUMETRIC_DEPTH_TO_COLOR_MODE", "forward").strip().lower()
        self._depth_to_color_mode = mode if mode in {"forward", "inverse", "identity", "auto"} else "forward"

    def capture_once(
        self,
        camera_ids: list[str] | None = None,
        frames_by_camera: dict[str, RawFrameSnapshot] | None = None,
        pixel_step: int | None = None,
        depth_min_m: float | None = None,
        depth_max_m: float | None = None,
        output_dir: Path | None = None,
        file_stem: str | None = None,
        write_preview: bool = True,
        ply_binary: bool = False,
        use_synchronized_snapshots: bool = True,
        synchronized_max_skew_ms: float = 75.0,
        synchronized_timeout_ms: int = 1200,
        allow_direct_capture_fallback: bool = True,
        apply_brightness_balance: bool = True,
        voxel_size_m: float | None = 0.0075,
        parallel_camera_processing: bool = False,
        direct_capture_timeout_ms: int = 600,
        direct_capture_max_attempts: int = 12,
        sample_projected_color: bool = True,
        direct_capture_prefer_depth_only: bool = False,
        write_color: bool = True,
        min_required_cameras: int = 1,
    ) -> CaptureResult:  # noqa: PLR0913,C901
        config = CaptureConfig(
            camera_ids=camera_ids,
            frames_by_camera=frames_by_camera,
            pixel_step=pixel_step,
            depth_min_m=depth_min_m,
            depth_max_m=depth_max_m,
            output_dir=output_dir,
            file_stem=file_stem,
            write_preview=write_preview,
            ply_binary=ply_binary,
            use_synchronized_snapshots=use_synchronized_snapshots,
            synchronized_max_skew_ms=synchronized_max_skew_ms,
            synchronized_timeout_ms=synchronized_timeout_ms,
            allow_direct_capture_fallback=allow_direct_capture_fallback,
            apply_brightness_balance=apply_brightness_balance,
            voxel_size_m=voxel_size_m,
            parallel_camera_processing=parallel_camera_processing,
            direct_capture_timeout_ms=direct_capture_timeout_ms,
            direct_capture_max_attempts=direct_capture_max_attempts,
            sample_projected_color=sample_projected_color,
            direct_capture_prefer_depth_only=direct_capture_prefer_depth_only,
            write_color=write_color,
            min_required_cameras=min_required_cameras,
        )
        return self._capture_impl(config)

    def _capture_impl(self, config: CaptureConfig) -> CaptureResult:  # noqa: C901
        """Implementation of capture logic delegated from capture_once for reduced complexity."""
        target_output_dir = config.output_dir if config.output_dir is not None else self._output_dir
        selected_camera_ids = sorted(set(config.camera_ids or self._camera_manager.camera_ids()))
        synchronized_frames = self._get_synchronized_frames(selected_camera_ids, config)
        
        pixel_step_value = max(1, int(config.pixel_step if config.pixel_step is not None else self._pixel_step))
        depth_min_value = float(self._depth_min_m if config.depth_min_m is None else config.depth_min_m)
        depth_max_value = float(self._depth_max_m if config.depth_max_m is None else config.depth_max_m)
        
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

        self._process_cameras(
            selected_camera_ids, config, synchronized_frames, pixel_step_value,
            depth_min_value, depth_max_value, all_points_world, all_colors,
            points_per_camera, cameras_used, skipped_cameras, stats,
        )

        if not all_points_world:
            raise ValueError(self._build_empty_capture_message(selected_camera_ids, stats))
        if len(cameras_used) < max(1, int(config.min_required_cameras)):
            raise ValueError(
                "Insufficient cameras produced points for capture. "
                f"required={max(1, int(config.min_required_cameras))} "
                f"used={len(cameras_used)} "
                f"selected={len(selected_camera_ids)}"
            )

        stacked_points, stacked_colors = self._stack_and_process_points(
            all_points_world, all_colors, config
        )
        return self._write_capture_output(
            target_output_dir, stacked_points, stacked_colors,
            points_per_camera, cameras_used, skipped_cameras, config
        )

    def _get_synchronized_frames(
        self, selected_camera_ids: list[str], config: CaptureConfig
    ) -> dict[str, RawFrameSnapshot]:
        """Fetch frames from cameras based on sync configuration."""
        if config.frames_by_camera is not None:
            return {
                camera_id: config.frames_by_camera.get(camera_id)
                for camera_id in selected_camera_ids
                if config.frames_by_camera.get(camera_id) is not None
            }
        if config.use_synchronized_snapshots:
            return self._camera_manager.synchronized_raw_snapshots(
                selected_camera_ids,
                require_depth=True,
                max_skew_ms=float(config.synchronized_max_skew_ms),
                timeout_ms=int(config.synchronized_timeout_ms),
            )
        synchronized_frames: dict[str, RawFrameSnapshot] = {}
        for camera_id in selected_camera_ids:
            frame = self._camera_manager.get_latest_raw_snapshot(camera_id, require_depth=True)
            if frame is not None:
                synchronized_frames[camera_id] = frame
        return synchronized_frames

    def _process_cameras(
        self, selected_camera_ids: list[str], config: CaptureConfig,
        synchronized_frames: dict[str, RawFrameSnapshot],
        pixel_step_value: int, depth_min_value: float, depth_max_value: float,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        points_per_camera: dict[str, int], cameras_used: list[str],
        skipped_cameras: dict[str, str], stats: dict[str, int],
    ) -> None:
        """Process all cameras in parallel or sequential mode."""
        def capture_for_camera(camera_id: str) -> tuple[str, np.ndarray | None, np.ndarray | None, str | None, str | None]:
            return camera_id, *self._capture_world_points_for_camera(
                camera_id,
                frame=synchronized_frames.get(camera_id),
                pixel_step=pixel_step_value,
                depth_min_m=depth_min_value,
                depth_max_m=depth_max_value,
                allow_direct_capture_fallback=config.allow_direct_capture_fallback,
                direct_capture_timeout_ms=config.direct_capture_timeout_ms,
                direct_capture_max_attempts=config.direct_capture_max_attempts,
                sample_projected_color=config.sample_projected_color,
                direct_capture_prefer_depth_only=config.direct_capture_prefer_depth_only,
                write_color=config.write_color,
            )

        if config.parallel_camera_processing and len(selected_camera_ids) > 1:
            self._process_cameras_parallel(
                selected_camera_ids, capture_for_camera, config.write_color,
                all_points_world, all_colors, points_per_camera, cameras_used,
                skipped_cameras, stats,
            )
        else:
            self._process_cameras_sequential(
                selected_camera_ids, capture_for_camera, config.write_color,
                all_points_world, all_colors, points_per_camera, cameras_used,
                skipped_cameras, stats,
            )

    def _process_cameras_parallel(
        self, camera_ids: list[str],
        capture_func: callable, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        points_per_camera: dict[str, int], cameras_used: list[str],
        skipped_cameras: dict[str, str], stats: dict[str, int],
    ) -> None:
        """Process cameras using parallel execution."""
        max_workers = min(8, len(camera_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(capture_func, camera_id) for camera_id in camera_ids]
            for future in as_completed(futures):
                camera_id, world_points, colors, skip_reason, skip_code = future.result()
                self._add_camera_results(
                    camera_id, world_points, colors, skip_reason, skip_code, write_color,
                    all_points_world, all_colors, points_per_camera, cameras_used,
                    skipped_cameras, stats,
                )

    def _process_cameras_sequential(
        self, camera_ids: list[str],
        capture_func: callable, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        points_per_camera: dict[str, int], cameras_used: list[str],
        skipped_cameras: dict[str, str], stats: dict[str, int],
    ) -> None:
        """Process cameras sequentially."""
        for camera_id in camera_ids:
            camera_id, world_points, colors, skip_reason, skip_code = capture_func(camera_id)
            self._add_camera_results(
                camera_id, world_points, colors, skip_reason, skip_code, write_color,
                all_points_world, all_colors, points_per_camera, cameras_used,
                skipped_cameras, stats,
            )

    def _add_camera_results(
        self, camera_id: str, world_points: np.ndarray | None, colors: np.ndarray | None,
        skip_reason: str | None, skip_code: str | None, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        points_per_camera: dict[str, int], cameras_used: list[str],
        skipped_cameras: dict[str, str], stats: dict[str, int],
    ) -> None:
        """Add results from a single camera to aggregated lists."""
        if world_points is None or (write_color and colors is None):
            if skip_reason is not None:
                skipped_cameras[camera_id] = skip_reason
            if skip_code is not None and skip_code in stats:
                stats[skip_code] += 1
            return
        
        all_points_world.append(world_points)
        if write_color and colors is not None:
            all_colors.append(colors)
        points_per_camera[camera_id] = int(world_points.shape[0])
        cameras_used.append(camera_id)

    def _stack_and_process_points(
        self, all_points_world: list[np.ndarray],
        all_colors: list[np.ndarray], config: CaptureConfig,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Stack points and apply post-processing."""
        if config.write_color and config.apply_brightness_balance:
            all_colors = self._balance_camera_brightness(all_colors)
        stacked_points = np.vstack(all_points_world)
        stacked_colors: np.ndarray | None = np.vstack(all_colors) if config.write_color else None
        if (config.write_color and config.voxel_size_m is not None and
            float(config.voxel_size_m) > 0.0 and stacked_colors is not None):
            stacked_points, stacked_colors = self._voxel_fuse(
                stacked_points, stacked_colors, voxel_size_m=float(config.voxel_size_m)
            )
        return stacked_points, stacked_colors

    def _write_capture_output(
        self, output_dir: Path, stacked_points: np.ndarray,
        stacked_colors: np.ndarray | None, points_per_camera: dict[str, int],
        cameras_used: list[str], skipped_cameras: dict[str, str], config: CaptureConfig,
    ) -> CaptureResult:
        """Write capture output files and return result."""
        file_stem = config.file_stem
        if file_stem is None:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            file_stem = f"volumetric_capture_{timestamp}"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        ply_path = output_dir / f"{file_stem}.ply"
        preview_path: Path | None = None

        self._write_ply(
            ply_path,
            stacked_points,
            stacked_colors,
            binary=bool(config.ply_binary),
            write_color=bool(config.write_color),
        )
        
        if config.write_preview:
            preview_colors = stacked_colors
            if preview_colors is None:
                preview_colors = np.full((stacked_points.shape[0], 3), 180, dtype=np.uint8)
            preview_path = output_dir / f"{file_stem}_preview.png"
            self._write_preview(preview_path, stacked_points, preview_colors)

        return CaptureResult(
            file_path=ply_path,
            preview_image_path=preview_path,
            file_name=ply_path.name,
            preview_image_name=preview_path.name if preview_path is not None else None,
            points_total=int(stacked_points.shape[0]),
            points_per_camera=points_per_camera,
            cameras_used=sorted(cameras_used),
            skipped_cameras=skipped_cameras,
        )

    def _capture_world_points_for_camera(
        self,
        camera_id: str,
        *,
        frame: RawFrameSnapshot | None,
        pixel_step: int,
        depth_min_m: float,
        depth_max_m: float,
        allow_direct_capture_fallback: bool,
        direct_capture_timeout_ms: int,
        direct_capture_max_attempts: int,
        sample_projected_color: bool,
        direct_capture_prefer_depth_only: bool,
        write_color: bool,
    ) -> tuple[np.ndarray | None, np.ndarray | None, str | None, str | None]:  # noqa: C901
        extrinsics = self._calibration_store.get(camera_id)
        if extrinsics is None:
            return None, None, f"{camera_id}: missing calibration entry", "no_calibration"

        if frame is None:
            frame = self._camera_manager.get_latest_raw_snapshot(camera_id, require_depth=True)
        if frame is None and allow_direct_capture_fallback:
            frame = self._camera_manager.capture_raw_frame(
                camera_id,
                require_depth=True,
                timeout_ms=max(20, int(direct_capture_timeout_ms)),
                max_attempts=max(1, int(direct_capture_max_attempts)),
                prefer_depth_only=bool(direct_capture_prefer_depth_only),
            )
        if frame is None or frame.depth is None:
            return None, None, f"{camera_id}: depth frame unavailable", "no_depth_frame"

        intrinsics = self._depth_intrinsics_for_frame(camera_id, frame)
        if intrinsics is None:
            return None, None, f"{camera_id}: intrinsics unavailable", "no_intrinsics"

        color_intrinsics = self._camera_manager.intrinsics(camera_id) if sample_projected_color else None
        depth_to_color = self._camera_manager.depth_to_color_transform(camera_id)

        depth_points = self._depth_to_camera_points(
            frame,
            intrinsics,
            pixel_step=pixel_step,
            depth_min_m=depth_min_m,
            depth_max_m=depth_max_m,
        )
        if depth_points.size == 0:
            return None, None, f"{camera_id}: no valid points after depth filter", "no_points_after_filter"

        color_camera_points = self._map_depth_points_to_color_camera(
            depth_points,
            depth_to_color,
            frame=frame,
            intrinsics=color_intrinsics,
        )
        if sample_projected_color:
            colors, color_valid = self._sample_colors_from_projection(frame, color_camera_points, color_intrinsics)
            if color_valid.shape[0] == color_camera_points.shape[0]:
                if not np.any(color_valid):
                    return None, None, f"{camera_id}: no valid projected color samples", "no_points_after_filter"
                color_camera_points = color_camera_points[color_valid]
                colors = colors[color_valid]
                if color_camera_points.size == 0:
                    return None, None, f"{camera_id}: no valid projected color samples", "no_points_after_filter"
        else:
            colors = np.full((color_camera_points.shape[0], 3), 180, dtype=np.uint8) if write_color else None
        
        world_points = self._camera_to_world(color_camera_points, extrinsics.t_camera_world)
        return world_points, colors, None, None

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
        color_width: int | None = None
        color_height: int | None = None
        if frame.color is not None and frame.color.ndim >= 2:
            color_height, color_width = frame.color.shape[:2]

        # Prefer actual frame dimensions when available; principal-point based scaling is only a fallback.
        if color_width is not None and color_height is not None and color_width > 0 and color_height > 0:
            scale_x = float(depth_width) / float(color_width)
            scale_y = float(depth_height) / float(color_height)
        else:
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
    ) -> tuple[np.ndarray, np.ndarray]:
        point_count = int(color_camera_points.shape[0])
        if point_count <= 0:
            return np.empty((0, 3), dtype=np.uint8), np.empty((0,), dtype=bool)
        if frame.color is None:
            return np.full((point_count, 3), 180, dtype=np.uint8), np.ones((point_count,), dtype=bool)
        if intrinsics is None:
            return np.full((point_count, 3), 180, dtype=np.uint8), np.ones((point_count,), dtype=bool)

        color = frame.color
        if color.ndim != 3 or color.shape[2] != 3:
            return np.full((point_count, 3), 180, dtype=np.uint8), np.ones((point_count,), dtype=bool)

        intrinsics = self._rescale_intrinsics_to_frame(
            np.asarray(intrinsics, dtype=np.float64),
            target_width=int(color.shape[1]),
            target_height=int(color.shape[0]),
        )

        fx = float(intrinsics[0, 0])
        fy = float(intrinsics[1, 1])
        cx = float(intrinsics[0, 2])
        cy = float(intrinsics[1, 2])

        x = color_camera_points[:, 0]
        y = color_camera_points[:, 1]
        z = color_camera_points[:, 2]

        colors = np.full((point_count, 3), 180, dtype=np.uint8)
        valid_mask = np.zeros((point_count,), dtype=bool)
        valid_z = z > 1e-6
        if not np.any(valid_z):
            return colors, valid_mask

        u = np.round((x[valid_z] * fx / z[valid_z]) + cx).astype(np.int32)
        v = np.round((y[valid_z] * fy / z[valid_z]) + cy).astype(np.int32)

        in_bounds = (u >= 0) & (u < color.shape[1]) & (v >= 0) & (v < color.shape[0])
        if np.any(in_bounds):
            valid_indices = np.nonzero(valid_z)[0]
            point_indices = valid_indices[in_bounds]
            colors[point_indices] = color[v[in_bounds], u[in_bounds]].astype(np.uint8)
            valid_mask[point_indices] = True

        return colors, valid_mask

    @staticmethod
    def _balance_camera_brightness(color_batches: list[np.ndarray]) -> list[np.ndarray]:
        if len(color_batches) <= 1:
            return color_batches

        luminance_means: list[float] = []
        for colors in color_batches:
            if colors.size == 0:
                luminance_means.append(0.0)
                continue
            b = colors[:, 0].astype(np.float32)
            g = colors[:, 1].astype(np.float32)
            r = colors[:, 2].astype(np.float32)
            luminance = (0.114 * b) + (0.587 * g) + (0.299 * r)
            luminance_means.append(float(np.mean(luminance)))

        valid_means = [value for value in luminance_means if value > 1.0]
        if len(valid_means) <= 1:
            return color_batches

        target_luminance = float(np.median(np.asarray(valid_means, dtype=np.float32)))
        balanced: list[np.ndarray] = []
        for colors, current_luminance in zip(color_batches, luminance_means, strict=False):
            if colors.size == 0 or current_luminance <= 1.0:
                balanced.append(colors)
                continue

            gain = target_luminance / current_luminance
            gain = float(np.clip(gain, 0.70, 1.30))
            if abs(gain - 1.0) < 0.03:
                balanced.append(colors)
                continue

            corrected = np.clip(colors.astype(np.float32) * gain, 0.0, 255.0).astype(np.uint8)
            balanced.append(corrected)
        return balanced

    @staticmethod
    def _voxel_fuse(points: np.ndarray, colors: np.ndarray, voxel_size_m: float) -> tuple[np.ndarray, np.ndarray]:
        if points.size == 0 or colors.size == 0:
            return points, colors

        voxel_size = float(max(1e-4, voxel_size_m))
        voxel_indices = np.floor(points / voxel_size).astype(np.int64)
        _, inverse = np.unique(voxel_indices, axis=0, return_inverse=True)
        if inverse.size == 0:
            return points, colors

        voxel_count = int(inverse.max()) + 1
        points_sum = np.zeros((voxel_count, 3), dtype=np.float64)
        colors_sum = np.zeros((voxel_count, 3), dtype=np.float64)
        counts = np.zeros((voxel_count,), dtype=np.int32)

        np.add.at(points_sum, inverse, points)
        np.add.at(colors_sum, inverse, colors.astype(np.float64))
        np.add.at(counts, inverse, 1)

        valid_voxels = counts > 0
        fused_points = points_sum[valid_voxels] / counts[valid_voxels, None]
        fused_colors = np.clip(
            np.rint(colors_sum[valid_voxels] / counts[valid_voxels, None]),
            0.0,
            255.0,
        ).astype(np.uint8)
        return fused_points, fused_colors

    def _map_depth_points_to_color_camera(
        self,
        depth_points: np.ndarray,
        depth_to_color: np.ndarray | None,
        *,
        frame: RawFrameSnapshot,
        intrinsics: np.ndarray | None,
    ) -> np.ndarray:
        if depth_to_color is None:
            return depth_points

        transform = np.asarray(depth_to_color, dtype=np.float64)
        if transform.shape != (4, 4):
            return depth_points

        mode = self._depth_to_color_mode
        if mode == "identity":
            return depth_points
        if mode == "inverse":
            try:
                return self._apply_transform(depth_points, np.linalg.inv(transform))
            except np.linalg.LinAlgError:
                return depth_points
        if mode == "forward":
            return self._apply_transform(depth_points, transform)

        # Auto mode: keep legacy behavior as an explicit opt-in for diagnostics.
        forward_candidate = self._apply_transform(depth_points, transform)
        candidates: list[tuple[str, np.ndarray]] = [
            ("forward", forward_candidate),
            ("identity", depth_points),
        ]

        if intrinsics is None or frame.color is None:
            return forward_candidate

        color_h, color_w = frame.color.shape[:2]
        intrinsics_scaled = self._rescale_intrinsics_to_frame(
            np.asarray(intrinsics, dtype=np.float64),
            target_width=int(color_w),
            target_height=int(color_h),
        )

        try:
            inverse_candidate = self._apply_transform(depth_points, np.linalg.inv(transform))
        except np.linalg.LinAlgError:
            inverse_candidate = None
        if inverse_candidate is not None:
            candidates.append(("inverse", inverse_candidate))

        scored: list[tuple[str, float, np.ndarray]] = []
        for name, candidate in candidates:
            score = self._projection_score(frame.color, candidate, intrinsics_scaled)
            scored.append((name, score, candidate))

        preference = {"forward": 0, "identity": 1, "inverse": 2}
        scored.sort(key=lambda item: (-item[1], preference.get(item[0], 99)))
        return scored[0][2]

    @staticmethod
    def _apply_transform(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
        rotation = transform[:3, :3]
        translation = transform[:3, 3]
        return (points @ rotation.T) + translation

    @staticmethod
    def _projection_score(color: np.ndarray, color_camera_points: np.ndarray, intrinsics: np.ndarray) -> float:
        if color.ndim != 3 or color.shape[2] != 3 or color_camera_points.size == 0:
            return -1.0

        z = color_camera_points[:, 2]
        valid_z = z > 1e-6
        if not np.any(valid_z):
            return 0.0

        fx = float(intrinsics[0, 0])
        fy = float(intrinsics[1, 1])
        cx = float(intrinsics[0, 2])
        cy = float(intrinsics[1, 2])

        x = color_camera_points[valid_z, 0]
        y = color_camera_points[valid_z, 1]
        z_valid = z[valid_z]
        u = (x * fx / z_valid) + cx
        v = (y * fy / z_valid) + cy

        in_bounds = (u >= 0.0) & (u < float(color.shape[1])) & (v >= 0.0) & (v < float(color.shape[0]))
        return float(np.count_nonzero(in_bounds)) / float(color_camera_points.shape[0])

    @staticmethod
    def _rescale_intrinsics_to_frame(intrinsics: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
        k = np.asarray(intrinsics, dtype=np.float64).copy()
        if k.shape != (3, 3):
            return k

        width = max(1.0, float(target_width))
        height = max(1.0, float(target_height))
        cx = float(k[0, 2])
        cy = float(k[1, 2])
        approx_width = max(1.0, 2.0 * cx)
        approx_height = max(1.0, 2.0 * cy)
        scale_x = width / approx_width
        scale_y = height / approx_height

        # Skip tiny corrections to avoid unnecessary per-frame numeric jitter.
        if abs(scale_x - 1.0) < 0.02 and abs(scale_y - 1.0) < 0.02:
            return k

        k[0, 0] *= scale_x
        k[1, 1] *= scale_y
        k[0, 2] *= scale_x
        k[1, 2] *= scale_y
        return k

    @staticmethod
    def _camera_to_world(camera_points: np.ndarray, t_camera_world: np.ndarray) -> np.ndarray:
        t_world_camera = np.linalg.inv(np.asarray(t_camera_world, dtype=np.float64))
        rotation = t_world_camera[:3, :3]
        translation = t_world_camera[:3, 3]
        return (camera_points @ rotation.T) + translation

    @staticmethod
    def _write_ply(
        path: Path,
        points: np.ndarray,
        colors: np.ndarray | None,
        *,
        binary: bool = False,
        write_color: bool = True,
    ) -> None:
        point_count = int(points.shape[0])
        if binary:
            if write_color:
                header = (
                    "ply\n"
                    "format binary_little_endian 1.0\n"
                    f"element vertex {point_count}\n"
                    "property float x\n"
                    "property float y\n"
                    "property float z\n"
                    "property uchar red\n"
                    "property uchar green\n"
                    "property uchar blue\n"
                    "end_header\n"
                )
                vertex_dtype = np.dtype(
                    [
                        ("x", "<f4"),
                        ("y", "<f4"),
                        ("z", "<f4"),
                        ("red", "u1"),
                        ("green", "u1"),
                        ("blue", "u1"),
                    ]
                )
            else:
                header = (
                    "ply\n"
                    "format binary_little_endian 1.0\n"
                    f"element vertex {point_count}\n"
                    "property float x\n"
                    "property float y\n"
                    "property float z\n"
                    "end_header\n"
                )
                vertex_dtype = np.dtype(
                    [
                        ("x", "<f4"),
                        ("y", "<f4"),
                        ("z", "<f4"),
                    ]
                )
            vertices = np.empty((point_count,), dtype=vertex_dtype)
            vertices["x"] = points[:, 0].astype(np.float32, copy=False)
            vertices["y"] = points[:, 1].astype(np.float32, copy=False)
            vertices["z"] = points[:, 2].astype(np.float32, copy=False)
            if write_color and colors is not None:
                # Internal color order is BGR; write PLY as RGB.
                vertices["red"] = colors[:, 2].astype(np.uint8, copy=False)
                vertices["green"] = colors[:, 1].astype(np.uint8, copy=False)
                vertices["blue"] = colors[:, 0].astype(np.uint8, copy=False)

            with path.open("wb") as handle:
                handle.write(header.encode("ascii"))
                vertices.tofile(handle)
            return

        with path.open("w", encoding="utf-8") as handle:
            handle.write("ply\n")
            handle.write("format ascii 1.0\n")
            handle.write(f"element vertex {point_count}\n")
            handle.write("property float x\n")
            handle.write("property float y\n")
            handle.write("property float z\n")
            if write_color:
                handle.write("property uchar red\n")
                handle.write("property uchar green\n")
                handle.write("property uchar blue\n")
            handle.write("end_header\n")
            if write_color and colors is not None:
                for idx in range(point_count):
                    x, y, z = points[idx]
                    b, g, r = colors[idx]
                    handle.write(f"{x:.6f} {y:.6f} {z:.6f} {int(r)} {int(g)} {int(b)}\n")
            else:
                for idx in range(point_count):
                    x, y, z = points[idx]
                    handle.write(f"{x:.6f} {y:.6f} {z:.6f}\n")

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
