from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

import cv2
import numpy as np

from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager, RawFrameSnapshot

LOGGER = logging.getLogger(__name__)


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
    depth_rgb_baseline: dict[str, dict[str, float | bool | str]]


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
        self._depth_rgb_baseline_tol_m = float(os.getenv("VOLUMETRIC_DEPTH_RGB_BASELINE_TOL_M", "0.0005"))
        self._icp_enabled = os.getenv("VOLUMETRIC_ICP_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self._icp_coarse_max_points = max(500, int(os.getenv("VOLUMETRIC_ICP_COARSE_MAX_POINTS", "3200")))
        self._icp_fine_max_points = max(500, int(os.getenv("VOLUMETRIC_ICP_FINE_MAX_POINTS", "2200")))
        self._icp_max_iterations = max(3, int(os.getenv("VOLUMETRIC_ICP_MAX_ITER", "24")))
        self._icp_tolerance_m = float(os.getenv("VOLUMETRIC_ICP_TOLERANCE_M", "0.0005"))
        self._icp_trim_ratio = float(np.clip(float(os.getenv("VOLUMETRIC_ICP_TRIM_RATIO", "0.80")), 0.45, 1.0))
        self._icp_max_correspondence_m = max(
            0.005,
            float(os.getenv("VOLUMETRIC_ICP_MAX_CORRESPONDENCE_M", "0.08")),
        )
        self._icp_min_correspondence_m = max(
            0.003,
            float(os.getenv("VOLUMETRIC_ICP_MIN_CORRESPONDENCE_M", "0.015")),
        )
        self._icp_stage_distance_decay = float(
            np.clip(float(os.getenv("VOLUMETRIC_ICP_STAGE_DECAY", "0.55")), 0.35, 0.95)
        )
        self._icp_overlap_threshold = float(np.clip(float(os.getenv("VOLUMETRIC_ICP_MIN_OVERLAP", "0.28")), 0.05, 0.95))
        self._icp_max_mean_error_m = float(os.getenv("VOLUMETRIC_ICP_MAX_MEAN_ERROR_M", "0.025"))
        self._icp_max_translation_step_m = max(
            0.01,
            float(os.getenv("VOLUMETRIC_ICP_MAX_TRANSLATION_STEP_M", "0.20")),
        )
        self._icp_max_rotation_step_deg = max(
            0.5,
            float(os.getenv("VOLUMETRIC_ICP_MAX_ROTATION_STEP_DEG", "20.0")),
        )
        self._persistent_alignment_enabled = (
            os.getenv("VOLUMETRIC_PERSIST_ALIGNMENT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._persistent_alignment_alpha = float(
            np.clip(float(os.getenv("VOLUMETRIC_PERSIST_ALIGNMENT_ALPHA", "0.55")), 0.05, 1.0)
        )
        self._capture_volume_enabled = (
            os.getenv("VOLUMETRIC_CAPTURE_VOLUME_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._capture_volume_half_extents_m = np.asarray(
            [
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_HALF_X_M", "0.45")),
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_HALF_Y_M", "0.60")),
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_HALF_Z_M", "0.45")),
            ],
            dtype=np.float64,
        )
        self._capture_volume_half_extents_m = np.maximum(self._capture_volume_half_extents_m, 0.05)
        self._capture_volume_origin_m = np.asarray(
            [
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_ORIGIN_X_M", "0.0")),
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_ORIGIN_Y_M", "0.0")),
                float(os.getenv("VOLUMETRIC_CAPTURE_VOLUME_ORIGIN_Z_M", "0.0")),
            ],
            dtype=np.float64,
        )
        capture_max_radius_raw = float(os.getenv("VOLUMETRIC_CAPTURE_MAX_RADIUS_M", "0.60"))
        self._capture_volume_max_radius_m = capture_max_radius_raw if capture_max_radius_raw > 0.0 else None
        default_alignment_file = self._output_dir / "camera_alignment_state.json"
        self._alignment_state_file = Path(
            os.getenv("VOLUMETRIC_ALIGNMENT_STATE_FILE", str(default_alignment_file))
        ).resolve()
        self._rng = np.random.default_rng()
        self._camera_alignment_offsets = self._load_alignment_offsets()

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
        depth_rgb_baseline = self.check_depth_rgb_baseline(selected_camera_ids)
        
        pixel_step_value = max(1, int(config.pixel_step if config.pixel_step is not None else self._pixel_step))
        depth_min_value = float(self._depth_min_m if config.depth_min_m is None else config.depth_min_m)
        depth_max_value = float(self._depth_max_m if config.depth_max_m is None else config.depth_max_m)
        
        all_points_world: list[np.ndarray] = []
        all_colors: list[np.ndarray] = []
        per_camera_points: dict[str, np.ndarray] = {}
        per_camera_colors: dict[str, np.ndarray] = {}
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
            per_camera_points, per_camera_colors, points_per_camera,
            cameras_used, skipped_cameras, stats,
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

        if self._icp_enabled and len(cameras_used) > 1:
            self._refine_camera_alignment(
                cameras_used,
                per_camera_points,
                per_camera_colors,
                write_color=bool(config.write_color),
            )
            all_points_world = [per_camera_points[camera_id] for camera_id in cameras_used]
            if config.write_color:
                all_colors = [per_camera_colors[camera_id] for camera_id in cameras_used]

        stacked_points, stacked_colors = self._stack_and_process_points(all_points_world, all_colors, config)
        return self._write_capture_output(
            target_output_dir, stacked_points, stacked_colors,
            points_per_camera, cameras_used, skipped_cameras, depth_rgb_baseline, config
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
        per_camera_points: dict[str, np.ndarray], per_camera_colors: dict[str, np.ndarray],
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
                all_points_world, all_colors, per_camera_points, per_camera_colors,
                points_per_camera, cameras_used,
                skipped_cameras, stats,
            )
        else:
            self._process_cameras_sequential(
                selected_camera_ids, capture_for_camera, config.write_color,
                all_points_world, all_colors, per_camera_points, per_camera_colors,
                points_per_camera, cameras_used,
                skipped_cameras, stats,
            )

    def _process_cameras_parallel(
        self, camera_ids: list[str],
        capture_func: callable, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        per_camera_points: dict[str, np.ndarray], per_camera_colors: dict[str, np.ndarray],
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
                    all_points_world, all_colors, per_camera_points, per_camera_colors,
                    points_per_camera, cameras_used,
                    skipped_cameras, stats,
                )

    def _process_cameras_sequential(
        self, camera_ids: list[str],
        capture_func: callable, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        per_camera_points: dict[str, np.ndarray], per_camera_colors: dict[str, np.ndarray],
        points_per_camera: dict[str, int], cameras_used: list[str],
        skipped_cameras: dict[str, str], stats: dict[str, int],
    ) -> None:
        """Process cameras sequentially."""
        for camera_id in camera_ids:
            camera_id, world_points, colors, skip_reason, skip_code = capture_func(camera_id)
            self._add_camera_results(
                camera_id, world_points, colors, skip_reason, skip_code, write_color,
                all_points_world, all_colors, per_camera_points, per_camera_colors,
                points_per_camera, cameras_used,
                skipped_cameras, stats,
            )

    def _add_camera_results(
        self, camera_id: str, world_points: np.ndarray | None, colors: np.ndarray | None,
        skip_reason: str | None, skip_code: str | None, write_color: bool,
        all_points_world: list[np.ndarray], all_colors: list[np.ndarray],
        per_camera_points: dict[str, np.ndarray], per_camera_colors: dict[str, np.ndarray],
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
        per_camera_points[camera_id] = world_points
        if write_color and colors is not None:
            per_camera_colors[camera_id] = colors
        points_per_camera[camera_id] = int(world_points.shape[0])
        cameras_used.append(camera_id)

    def _refine_camera_alignment(
        self,
        cameras_used: list[str],
        per_camera_points: dict[str, np.ndarray],
        per_camera_colors: dict[str, np.ndarray],
        *,
        write_color: bool,
    ) -> None:
        if len(cameras_used) < 2:
            return

        # Keep world anchoring stable by always choosing the same camera id as reference.
        reference_id = sorted(cameras_used)[0]
        reference_points = per_camera_points.get(reference_id)
        if reference_points is None or reference_points.shape[0] < 80:
            return

        reference_cloud = self._prepare_icp_points(
            reference_points,
            max_points=max(self._icp_coarse_max_points * 4, 12000),
            voxel_size=max(self._icp_min_correspondence_m * 0.8, 0.004),
        )
        updated_offsets: dict[str, np.ndarray] = {}
        candidate_camera_ids = [camera_id for camera_id in cameras_used if camera_id != reference_id]
        candidate_camera_ids.sort(key=lambda camera_id: per_camera_points.get(camera_id, np.empty((0, 3))).shape[0], reverse=True)

        for camera_id in candidate_camera_ids:
            source_points = per_camera_points.get(camera_id)
            if source_points is None or source_points.shape[0] < 80:
                continue

            transform, metrics = self._icp_align(source_points, reference_cloud)
            if transform is None or metrics is None:
                LOGGER.debug("ICP skipped for %s: no stable transform found", camera_id)
                continue
            if not self._icp_alignment_is_valid(transform, metrics):
                LOGGER.debug(
                    "ICP rejected for %s: mean_error=%.4f overlap=%.3f inliers=%s",
                    camera_id,
                    float(metrics.get("mean_error_m", -1.0)),
                    float(metrics.get("overlap_ratio", -1.0)),
                    int(metrics.get("inliers", 0)),
                )
                continue

            refined_points = self._apply_transform(source_points, transform)
            per_camera_points[camera_id] = refined_points
            if write_color and camera_id in per_camera_colors:
                per_camera_colors[camera_id] = per_camera_colors[camera_id]
            reference_cloud = self._extend_reference_cloud(reference_cloud, refined_points)

            if self._persistent_alignment_enabled:
                previous_offset = self._camera_alignment_offsets.get(camera_id, np.eye(4, dtype=np.float64))
                damped_delta = self._scale_rigid_transform(transform, self._persistent_alignment_alpha)
                updated_offsets[camera_id] = damped_delta @ previous_offset

            LOGGER.info(
                "ICP accepted for %s -> %s: mean_error=%.4f overlap=%.3f inliers=%s",
                camera_id,
                reference_id,
                float(metrics.get("mean_error_m", -1.0)),
                float(metrics.get("overlap_ratio", -1.0)),
                int(metrics.get("inliers", 0)),
            )

        if updated_offsets:
            self._camera_alignment_offsets.update(updated_offsets)
            self._save_alignment_offsets()

    def _prepare_icp_points(self, points: np.ndarray, max_points: int, voxel_size: float) -> np.ndarray:
        if points.shape[0] <= 0:
            return points
        reduced = self._voxel_downsample_points(points, voxel_size)
        return self._icp_sample(reduced, max_points)

    def _icp_sample(self, points: np.ndarray, max_points: int) -> np.ndarray:
        if points.shape[0] <= max_points:
            return points
        indices = self._rng.choice(points.shape[0], size=max_points, replace=False)
        return points[indices]

    @staticmethod
    def _voxel_downsample_points(points: np.ndarray, voxel_size: float) -> np.ndarray:
        if points.shape[0] <= 1:
            return points
        step = float(max(voxel_size, 1e-4))
        voxel_indices = np.floor(points / step).astype(np.int64)
        _, inverse = np.unique(voxel_indices, axis=0, return_inverse=True)
        if inverse.size == 0:
            return points

        voxel_count = int(inverse.max()) + 1
        points_sum = np.zeros((voxel_count, 3), dtype=np.float64)
        counts = np.zeros((voxel_count,), dtype=np.int32)
        np.add.at(points_sum, inverse, points)
        np.add.at(counts, inverse, 1)

        valid = counts > 0
        return points_sum[valid] / counts[valid, None]

    def _icp_align(
        self,
        source_points: np.ndarray,
        target_points: np.ndarray,
    ) -> tuple[np.ndarray | None, dict[str, float | int] | None]:
        if source_points.shape[0] < 30 or target_points.shape[0] < 30:
            return None, None

        coarse_source = self._prepare_icp_points(
            source_points,
            self._icp_coarse_max_points,
            voxel_size=max(self._icp_min_correspondence_m * 1.8, 0.007),
        )
        coarse_target = self._prepare_icp_points(
            target_points,
            self._icp_coarse_max_points,
            voxel_size=max(self._icp_min_correspondence_m * 1.8, 0.007),
        )
        coarse_iterations = max(6, int(round(self._icp_max_iterations * 0.55)))
        coarse_transform, coarse_metrics = self._icp_stage(
            coarse_source,
            coarse_target,
            max_correspondence_m=self._icp_max_correspondence_m,
            iterations=coarse_iterations,
            trim_ratio=self._icp_trim_ratio,
        )
        if coarse_transform is None or coarse_metrics is None:
            return None, None

        fine_source_raw = self._prepare_icp_points(
            source_points,
            self._icp_fine_max_points,
            voxel_size=max(self._icp_min_correspondence_m * 0.9, 0.0035),
        )
        fine_target = self._prepare_icp_points(
            target_points,
            self._icp_fine_max_points,
            voxel_size=max(self._icp_min_correspondence_m * 0.9, 0.0035),
        )
        fine_source = self._apply_transform(fine_source_raw, coarse_transform)
        fine_distance = max(
            self._icp_min_correspondence_m,
            self._icp_max_correspondence_m * self._icp_stage_distance_decay,
        )
        fine_transform, fine_metrics = self._icp_stage(
            fine_source,
            fine_target,
            max_correspondence_m=fine_distance,
            iterations=self._icp_max_iterations,
            trim_ratio=min(0.95, max(self._icp_trim_ratio, 0.7)),
        )
        if fine_transform is None or fine_metrics is None:
            return coarse_transform, coarse_metrics

        return fine_transform @ coarse_transform, fine_metrics

    def _icp_stage(
        self,
        source: np.ndarray,
        target: np.ndarray,
        *,
        max_correspondence_m: float,
        iterations: int,
        trim_ratio: float,
    ) -> tuple[np.ndarray | None, dict[str, float | int] | None]:
        if source.shape[0] < 30 or target.shape[0] < 30:
            return None, None

        current = source.copy()
        transform_total = np.eye(4, dtype=np.float64)
        previous_error: float | None = None
        min_inliers = max(30, int(round(source.shape[0] * 0.08)))

        for _ in range(max(1, int(iterations))):
            matched, distances = self._nearest_neighbors_with_distance(current, target)
            inlier_mask = distances <= float(max_correspondence_m)
            if int(np.count_nonzero(inlier_mask)) < min_inliers:
                return None, None

            inlier_mask = self._trim_correspondences(inlier_mask, distances, trim_ratio=trim_ratio)
            inlier_count = int(np.count_nonzero(inlier_mask))
            if inlier_count < 6:
                return None, None

            source_inliers = current[inlier_mask]
            target_inliers = matched[inlier_mask]
            transform, mean_error = self._rigid_transform(source_inliers, target_inliers)
            if transform is None or mean_error is None:
                return None, None

            current = self._apply_transform(current, transform)
            transform_total = transform @ transform_total

            if previous_error is not None and abs(previous_error - mean_error) < self._icp_tolerance_m:
                break
            previous_error = mean_error

        matched_final, distances_final = self._nearest_neighbors_with_distance(current, target)
        inlier_mask_final = distances_final <= float(max_correspondence_m)
        inlier_mask_final = self._trim_correspondences(inlier_mask_final, distances_final, trim_ratio=trim_ratio)
        final_inliers = int(np.count_nonzero(inlier_mask_final))
        if final_inliers < min_inliers:
            return None, None
        mean_error_final = float(np.mean(distances_final[inlier_mask_final]))
        overlap_ratio = float(final_inliers) / float(max(1, current.shape[0]))

        metrics = {
            "mean_error_m": mean_error_final,
            "overlap_ratio": overlap_ratio,
            "inliers": final_inliers,
            "samples": int(current.shape[0]),
        }
        return transform_total, metrics

    @staticmethod
    def _nearest_neighbors_with_distance(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        diff = source[:, None, :] - target[None, :, :]
        distances_sq = np.sum(diff * diff, axis=2)
        indices = np.argmin(distances_sq, axis=1)
        nearest = target[indices]
        nearest_distance = np.sqrt(distances_sq[np.arange(source.shape[0]), indices])
        return nearest, nearest_distance

    @staticmethod
    def _trim_correspondences(inlier_mask: np.ndarray, distances: np.ndarray, *, trim_ratio: float) -> np.ndarray:
        if trim_ratio >= 0.999:
            return inlier_mask
        inlier_indices = np.nonzero(inlier_mask)[0]
        if inlier_indices.size <= 6:
            return inlier_mask
        keep_count = max(6, int(round(inlier_indices.size * float(trim_ratio))))
        ordered_local = np.argsort(distances[inlier_indices])
        keep_indices = inlier_indices[ordered_local[:keep_count]]
        trimmed_mask = np.zeros_like(inlier_mask, dtype=bool)
        trimmed_mask[keep_indices] = True
        return trimmed_mask

    def _icp_alignment_is_valid(self, transform: np.ndarray, metrics: dict[str, float | int]) -> bool:
        mean_error_m = float(metrics.get("mean_error_m", 999.0))
        overlap_ratio = float(metrics.get("overlap_ratio", 0.0))
        inliers = int(metrics.get("inliers", 0))
        translation_step_m = float(np.linalg.norm(transform[:3, 3]))
        rotation_step_deg = self._rotation_angle_deg(transform)
        if inliers < 30:
            return False
        if mean_error_m > self._icp_max_mean_error_m:
            return False
        if overlap_ratio < self._icp_overlap_threshold:
            return False
        if translation_step_m > self._icp_max_translation_step_m:
            return False
        if rotation_step_deg > self._icp_max_rotation_step_deg:
            return False
        return True

    def _extend_reference_cloud(self, reference_cloud: np.ndarray, aligned_source: np.ndarray) -> np.ndarray:
        if aligned_source.size == 0:
            return reference_cloud
        combined = np.vstack([reference_cloud, aligned_source])
        return self._prepare_icp_points(
            combined,
            max_points=max(self._icp_coarse_max_points * 5, 15000),
            voxel_size=max(self._icp_min_correspondence_m * 0.75, 0.003),
        )

    @staticmethod
    def _rotation_angle_deg(transform: np.ndarray) -> float:
        rotation = np.asarray(transform[:3, :3], dtype=np.float64)
        trace_value = float(np.trace(rotation))
        cosine = np.clip((trace_value - 1.0) * 0.5, -1.0, 1.0)
        return float(np.degrees(np.arccos(cosine)))

    @staticmethod
    def _scale_rigid_transform(transform: np.ndarray, alpha: float) -> np.ndarray:
        scaled = np.eye(4, dtype=np.float64)
        clamped_alpha = float(np.clip(alpha, 0.0, 1.0))
        rotation = np.asarray(transform[:3, :3], dtype=np.float64)
        translation = np.asarray(transform[:3, 3], dtype=np.float64)

        rvec, _ = cv2.Rodrigues(rotation)
        rvec = rvec.reshape(3) * clamped_alpha
        scaled_rotation, _ = cv2.Rodrigues(rvec.reshape(3, 1))
        scaled[:3, :3] = scaled_rotation
        scaled[:3, 3] = translation * clamped_alpha
        return scaled

    def _load_alignment_offsets(self) -> dict[str, np.ndarray]:
        if not self._persistent_alignment_enabled:
            return {}
        if not self._alignment_state_file.is_file():
            return {}
        try:
            payload = json.loads(self._alignment_state_file.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to read camera alignment state from %s: %s", self._alignment_state_file, exc)
            return {}

        raw_offsets = payload.get("camera_offsets", {})
        if not isinstance(raw_offsets, dict):
            return {}

        offsets: dict[str, np.ndarray] = {}
        for camera_id, transform in raw_offsets.items():
            if not isinstance(camera_id, str):
                continue
            matrix = np.asarray(transform, dtype=np.float64)
            if matrix.shape != (4, 4):
                continue
            if not np.all(np.isfinite(matrix)):
                continue
            matrix[3, :] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
            offsets[camera_id] = matrix

        if offsets:
            LOGGER.info("Loaded persistent camera alignment offsets: %s", sorted(offsets))
        return offsets

    def _save_alignment_offsets(self) -> None:
        if not self._persistent_alignment_enabled:
            return

        camera_offsets: dict[str, list[list[float]]] = {}
        for camera_id, transform in self._camera_alignment_offsets.items():
            matrix = np.asarray(transform, dtype=np.float64)
            if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
                continue
            safe_matrix = matrix.copy()
            safe_matrix[3, :] = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
            camera_offsets[camera_id] = safe_matrix.tolist()
        payload = {
            "version": 1,
            "updated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "camera_offsets": camera_offsets,
        }

        try:
            self._alignment_state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._alignment_state_file.with_suffix(f"{self._alignment_state_file.suffix}.tmp")
            temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.replace(self._alignment_state_file)
        except Exception as exc:
            LOGGER.warning("Failed to persist camera alignment offsets to %s: %s", self._alignment_state_file, exc)

    @staticmethod
    def _rigid_transform(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray | None, float | None]:
        if source.shape != target.shape or source.shape[0] < 3:
            return None, None

        source_mean = np.mean(source, axis=0)
        target_mean = np.mean(target, axis=0)
        source_centered = source - source_mean
        target_centered = target - target_mean

        covariance = source_centered.T @ target_centered
        u, _, vt = np.linalg.svd(covariance)
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1, :] *= -1
            rotation = vt.T @ u.T

        translation = target_mean - rotation @ source_mean
        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = rotation
        transform[:3, 3] = translation

        aligned = (source @ rotation.T) + translation
        error = np.linalg.norm(aligned - target, axis=1)
        return transform, float(np.mean(error))

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
        cameras_used: list[str], skipped_cameras: dict[str, str],
        depth_rgb_baseline: dict[str, dict[str, float | bool | str]],
        config: CaptureConfig,
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
            depth_rgb_baseline=depth_rgb_baseline,
        )

    def check_depth_rgb_baseline(
        self,
        camera_ids: list[str] | None = None,
    ) -> dict[str, dict[str, float | bool | str]]:
        selected = camera_ids or self._calibration_store.all_camera_ids()
        results: dict[str, dict[str, float | bool | str]] = {}

        for camera_id in selected:
            extrinsics = self._calibration_store.get(camera_id)
            if extrinsics is None or extrinsics.t_rgb_depth is None:
                results[camera_id] = {
                    "ok": False,
                    "reason": "missing_calibration_depth_rgb",
                }
                continue

            sdk_transform = self._camera_manager.depth_to_color_transform(camera_id)
            if sdk_transform is None:
                results[camera_id] = {
                    "ok": False,
                    "reason": "missing_sdk_depth_rgb",
                }
                continue

            results[camera_id] = self._compare_depth_rgb_transforms(
                extrinsics.t_rgb_depth,
                sdk_transform,
                self._depth_rgb_baseline_tol_m,
            )
        return results

    @staticmethod
    def _compare_depth_rgb_transforms(
        calib_transform: np.ndarray,
        sdk_transform: np.ndarray,
        tolerance_m: float,
    ) -> dict[str, float | bool | str]:
        calib = np.asarray(calib_transform, dtype=np.float64)
        sdk = np.asarray(sdk_transform, dtype=np.float64)
        if calib.shape != (4, 4) or sdk.shape != (4, 4):
            return {
                "ok": False,
                "reason": "invalid_transform_shape",
            }

        if not np.all(np.isfinite(calib)) or not np.all(np.isfinite(sdk)):
            return {
                "ok": False,
                "reason": "non_finite_transform",
            }

        calib_t = np.asarray(calib[:3, 3], dtype=np.float64)
        sdk_t = np.asarray(sdk[:3, 3], dtype=np.float64)
        delta_t = calib_t - sdk_t
        delta_norm = float(np.linalg.norm(delta_t))
        ok = delta_norm <= float(tolerance_m)
        return {
            "ok": bool(ok),
            "delta_translation_m": float(delta_norm),
            "delta_x_m": float(delta_t[0]),
            "calib_x_m": float(calib_t[0]),
            "sdk_x_m": float(sdk_t[0]),
            "tolerance_m": float(tolerance_m),
        }

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
        depth_to_color = extrinsics.t_rgb_depth
        if depth_to_color is None:
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
        camera_offset = self._camera_alignment_offsets.get(camera_id)
        if camera_offset is not None:
            world_points = self._apply_transform(world_points, camera_offset)
        if self._capture_volume_enabled:
            world_points, colors = self._filter_to_capture_volume(world_points, colors)
            if world_points.shape[0] == 0:
                return None, None, f"{camera_id}: no points inside capture volume", "no_points_after_filter"
        return world_points, colors, None, None

    def _filter_to_capture_volume(
        self,
        points_world: np.ndarray,
        colors: np.ndarray | None,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        if points_world.shape[0] == 0:
            return points_world, colors

        delta = points_world - self._capture_volume_origin_m[None, :]
        in_volume = np.all(np.abs(delta) <= self._capture_volume_half_extents_m[None, :], axis=1)
        if self._capture_volume_max_radius_m is not None:
            radius = np.linalg.norm(delta, axis=1)
            in_volume &= radius <= float(self._capture_volume_max_radius_m)
        if not np.any(in_volume):
            return np.empty((0, 3), dtype=points_world.dtype), (
                np.empty((0, 3), dtype=colors.dtype) if colors is not None else None
            )

        filtered_points = points_world[in_volume]
        filtered_colors = colors[in_volume] if colors is not None else None
        return filtered_points, filtered_colors

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
        width = 1200
        height = 900
        canvas = np.full((height, width, 3), 18, dtype=np.uint8)

        projected = VolumetricCaptureService._project_preview_points(points, width=width, height=height)
        if projected is None:
            cv2.imwrite(str(path), canvas)
            return

        px, py, depth, point_radius, visible = projected
        in_frame = (px >= 0) & (px < width) & (py >= 0) & (py < height)
        if not np.any(in_frame):
            cv2.imwrite(str(path), canvas)
            return

        px = px[in_frame]
        py = py[in_frame]
        depth = depth[in_frame]
        draw_colors = colors[visible][in_frame]
        point_radius = point_radius[in_frame]

        depth_span = max(float(np.ptp(depth)), 1e-6)
        depth_light = 1.0 - ((depth - float(depth.min())) / depth_span)
        shade = np.clip(0.74 + (depth_light * 0.22), 0.70, 1.04)
        draw_colors = np.clip(draw_colors.astype(np.float32) * shade[:, None], 0.0, 255.0).astype(np.uint8)

        order = np.argsort(depth)[::-1]
        for idx in order:
            x_coord = int(px[idx])
            y_coord = int(py[idx])
            radius = int(point_radius[idx])
            b, g, r = draw_colors[idx]
            cv2.circle(canvas, (x_coord, y_coord), radius + 1, (10, 10, 10), thickness=-1)
            cv2.circle(canvas, (x_coord, y_coord), radius, (int(b), int(g), int(r)), thickness=-1)

        cv2.imwrite(str(path), canvas)

    @staticmethod
    def _project_preview_points(
        points: np.ndarray,
        *,
        width: int,
        height: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
        if points.size == 0:
            return None

        world_points = np.asarray(points, dtype=np.float64)
        mins = world_points.min(axis=0)
        maxs = world_points.max(axis=0)
        center = (mins + maxs) * 0.5
        size = maxs - mins
        max_axis = float(np.max(size))
        scale = 1.4 / max_axis if max_axis > 1e-9 else 1.0
        preview_points = (world_points - center[None, :]) * scale

        eye = np.asarray([0.0, 0.35, 1.6], dtype=np.float64)
        target = np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
        up_hint = np.asarray([0.0, 1.0, 0.0], dtype=np.float64)

        forward = target - eye
        forward /= max(float(np.linalg.norm(forward)), 1e-9)
        right = np.cross(forward, up_hint)
        right /= max(float(np.linalg.norm(right)), 1e-9)
        up = np.cross(right, forward)

        relative = preview_points - eye[None, :]
        camera_x = relative @ right
        camera_y = relative @ up
        depth = relative @ forward
        visible = depth > 0.05
        if not np.any(visible):
            return None

        camera_x = camera_x[visible]
        camera_y = camera_y[visible]
        depth = depth[visible]

        focal = (float(height) * 0.5) / np.tan(np.deg2rad(45.0) * 0.5)
        px = np.rint((float(width) * 0.5) + ((camera_x / depth) * focal)).astype(np.int32)
        py = np.rint((float(height) * 0.5) - ((camera_y / depth) * focal)).astype(np.int32)

        diameter = np.clip((0.026 * focal) / depth, 4.0, 18.0)
        radius = np.maximum(2, np.rint(diameter * 0.5).astype(np.int32))
        return px, py, depth, radius, visible
