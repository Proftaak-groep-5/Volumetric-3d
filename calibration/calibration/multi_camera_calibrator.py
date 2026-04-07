from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
import numpy.typing as npt

from calibration.calibration.aruco_cube import ArucoCubeModel
from calibration.calibration.detector import ArucoMarkerDetector
from calibration.calibration.pose_estimation import (
    estimate_frame_cube_pose,
    marker_detections_to_cube_observations,
)
from calibration.camera.base import CameraDevice
from calibration.config import CalibrationConfig
from calibration.io.visualization import DebugVisualizer, DistanceOverlayMetrics
from calibration.math3d.transforms import average_transforms, invert_transform, rotation_angle_deg

LOGGER = logging.getLogger(__name__)
ArrayF64 = npt.NDArray[np.float64]


@dataclass
class FrameCalibrationRecord:
    frame_index: int
    timestamp_ns: int
    success: bool
    marker_ids: List[int]
    markers_used: int
    markers_total: int
    mean_reprojection_error_px: Optional[float]
    translation_spread_m: Optional[float]
    rotation_spread_deg: Optional[float]
    t_camera_cube: Optional[ArrayF64]
    t_world_camera: Optional[ArrayF64]
    depth_distance_m: Optional[float] = None
    image_distance_m: Optional[float] = None
    marker_surface_distance_m: Optional[float] = None
    marker_center_guess_distance_m: Optional[float] = None
    distance_delta_m: Optional[float] = None
    distance_delta_pct: Optional[float] = None
    distance_consistent: Optional[bool] = None
    reject_reason: Optional[str] = None


@dataclass
class CameraQualityMetrics:
    frames_requested: int
    frames_processed: int
    valid_frame_estimates: int
    inlier_frame_estimates: int
    total_marker_detections: int
    valid_marker_observations: int
    unique_markers_seen: List[int]
    mean_reprojection_error_px: Optional[float]
    translation_std_m: Optional[float]
    rotation_std_deg: Optional[float]


@dataclass
class CameraCalibrationResult:
    camera_id: str
    success: bool
    message: str
    timestamp_utc: str
    t_world_camera: Optional[ArrayF64]
    t_camera_world: Optional[ArrayF64]
    t_camera_cube: Optional[ArrayF64]
    markers_used: List[int]
    quality: CameraQualityMetrics
    per_frame_estimates: List[FrameCalibrationRecord]


@dataclass
class CalibrationRunResult:
    timestamp_utc: str
    camera_results: List[CameraCalibrationResult]
    successful_cameras: int
    failed_cameras: int


@dataclass
class _CameraAccumulationState:
    frames: List[FrameCalibrationRecord] = field(default_factory=list)
    marker_ids_seen: Set[int] = field(default_factory=set)
    total_marker_detections: int = 0
    valid_marker_observations: int = 0
    reprojection_errors: List[float] = field(default_factory=list)
    frames_processed: int = 0


class MultiCameraCalibrator:
    def __init__(
        self,
        config: CalibrationConfig,
        cube_model: ArucoCubeModel,
        detector: ArucoMarkerDetector,
        cameras: Sequence[CameraDevice],
        visualizer: Optional[DebugVisualizer] = None,
    ) -> None:
        self._config = config
        self._cube_model = cube_model
        self._detector = detector
        self._cameras = list(cameras)
        self._visualizer = visualizer

    def run(self) -> CalibrationRunResult:
        timestamp = datetime.now(timezone.utc).isoformat()

        camera_results: List[CameraCalibrationResult] = []
        active_cameras: List[CameraDevice] = []
        intrinsics_by_camera: Dict[str, Any] = {}
        state_by_camera: Dict[str, _CameraAccumulationState] = {}

        for camera in self._cameras:
            try:
                camera.start()
                intrinsics = camera.get_intrinsics()
                intrinsics.validate()
                active_cameras.append(camera)
                intrinsics_by_camera[camera.camera_id] = intrinsics
                state_by_camera[camera.camera_id] = _CameraAccumulationState()
                LOGGER.info("Camera %s ready for calibration", camera.camera_id)
            except Exception as exc:
                LOGGER.exception("Camera %s failed to start: %s", camera.camera_id, exc)
                camera_results.append(
                    self._failure_result_for_camera(
                        camera_id=camera.camera_id,
                        message=f"Failed to initialize camera: {exc}",
                        timestamp=timestamp,
                    )
                )

        if not active_cameras:
            return CalibrationRunResult(
                timestamp_utc=timestamp,
                camera_results=camera_results,
                successful_cameras=0,
                failed_cameras=len(camera_results),
            )

        try:
            self._warmup_cameras(active_cameras)

            for frame_idx in range(self._config.frame_count):
                for camera in active_cameras:
                    self._process_single_camera_frame(
                        camera=camera,
                        frame_idx=frame_idx,
                        intrinsics=intrinsics_by_camera[camera.camera_id],
                        state=state_by_camera[camera.camera_id],
                    )
        finally:
            for camera in active_cameras:
                camera.stop()
            if self._visualizer is not None:
                self._visualizer.close()

        for camera in active_cameras:
            camera_id = camera.camera_id
            result = self._finalize_camera_result(
                camera_id=camera_id,
                timestamp=timestamp,
                state=state_by_camera[camera_id],
            )
            camera_results.append(result)

        successful = sum(1 for result in camera_results if result.success)
        failed = len(camera_results) - successful

        return CalibrationRunResult(
            timestamp_utc=timestamp,
            camera_results=camera_results,
            successful_cameras=successful,
            failed_cameras=failed,
        )

    def _warmup_cameras(self, cameras: Sequence[CameraDevice]) -> None:
        if self._config.warmup_frames <= 0:
            return

        LOGGER.info("Warmup: grabbing %s initial frame(s) per camera", self._config.warmup_frames)
        for _ in range(self._config.warmup_frames):
            for camera in cameras:
                _ = camera.get_frame(timeout_ms=1000)

    def _process_single_camera_frame(self, camera: CameraDevice, frame_idx: int, intrinsics: Any, state: _CameraAccumulationState) -> None:
        frame = camera.get_frame(timeout_ms=1500)
        if frame is None:
            state.frames.append(self._build_rejected_record(frame_index=frame_idx, timestamp_ns=0, reject_reason="no_frame"))
            return

        if frame.color is None:
            state.frames.append(
                self._build_rejected_record(
                    frame_index=frame.frame_index,
                    timestamp_ns=frame.timestamp_ns,
                    reject_reason="no_color_frame",
                )
            )
            return

        state.frames_processed += 1

        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(
                "Frame diagnostics camera=%s frame=%s shape=%s dtype=%s",
                frame.camera_id,
                frame.frame_index,
                frame.color.shape,
                frame.color.dtype,
            )

        try:
            detections = self._detector.detect(
                frame=frame,
                intrinsics=intrinsics,
                max_reprojection_error_px=self._config.quality.max_reprojection_error_px,
            )
        except Exception as exc:
            LOGGER.error("Detection failed camera=%s frame=%s: %s", frame.camera_id, frame.frame_index, exc)
            state.frames.append(
                self._build_rejected_record(
                    frame_index=frame.frame_index,
                    timestamp_ns=frame.timestamp_ns,
                    reject_reason="detector_error",
                )
            )
            return

        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(
                "Detection diagnostics camera=%s frame=%s marker_ids=%s",
                frame.camera_id,
                frame.frame_index,
                [det.marker_id for det in detections],
            )

        observations = marker_detections_to_cube_observations(detections, self._cube_model)

        state.total_marker_detections += len(detections)
        state.valid_marker_observations += len(observations)

        for obs in observations:
            state.marker_ids_seen.add(obs.marker_id)
            state.reprojection_errors.append(obs.reprojection_error_px)

        frame_pose = estimate_frame_cube_pose(
            observations=observations,
            min_markers_per_frame=self._config.quality.min_markers_per_frame,
            marker_outlier_translation_m=self._config.quality.marker_outlier_translation_m,
            marker_outlier_rotation_deg=self._config.quality.marker_outlier_rotation_deg,
        )

        if frame_pose is None:
            reason = "insufficient_observations"
            if len(observations) >= self._config.quality.min_markers_per_frame:
                reason = "marker_observations_rejected_as_outliers"
            record = self._build_rejected_record(
                frame_index=frame.frame_index,
                timestamp_ns=frame.timestamp_ns,
                reject_reason=reason,
                marker_ids=sorted({obs.marker_id for obs in observations}),
                markers_total=len(observations),
            )
        else:
            t_camera_cube = frame_pose.t_camera_cube
            t_world_camera = invert_transform(t_camera_cube)
            marker_surface_distance_m, marker_center_guess_distance_m = self._estimate_marker_center_guess_distance_m(
                detections=detections,
                cube_length_m=float(self._cube_model.cube_length),
            )
            depth_distance_m, image_distance_m, distance_delta_m, distance_delta_pct, distance_consistent = (
                self._compute_depth_crosscheck(
                    frame_depth=frame.depth,
                    color_shape=tuple(frame.color.shape[:2]),
                    detections=detections,
                    t_camera_cube=t_camera_cube,
                    camera_id=frame.camera_id,
                    frame_index=frame.frame_index,
                )
            )

            record = FrameCalibrationRecord(
                frame_index=frame.frame_index,
                timestamp_ns=frame.timestamp_ns,
                success=True,
                marker_ids=frame_pose.marker_ids,
                markers_used=frame_pose.used_observation_count,
                markers_total=frame_pose.total_observation_count,
                mean_reprojection_error_px=frame_pose.mean_reprojection_error_px,
                translation_spread_m=frame_pose.translation_spread_m,
                rotation_spread_deg=frame_pose.rotation_spread_deg,
                t_camera_cube=t_camera_cube,
                t_world_camera=t_world_camera,
                depth_distance_m=depth_distance_m,
                image_distance_m=image_distance_m,
                marker_surface_distance_m=marker_surface_distance_m,
                marker_center_guess_distance_m=marker_center_guess_distance_m,
                distance_delta_m=distance_delta_m,
                distance_delta_pct=distance_delta_pct,
                distance_consistent=distance_consistent,
                reject_reason=None,
            )

        state.frames.append(record)

        if self._visualizer is not None and self._visualizer.enabled and frame.color is not None:
            self._visualizer.render_frame(
                camera_id=camera.camera_id,
                frame_index=frame.frame_index,
                image_bgr=frame.color,
                detections=detections,
                frame_pose=frame_pose,
                intrinsics=intrinsics,
                marker_axis_length=self._cube_model.marker_length,
                cube_axis_length=self._cube_model.cube_length * 0.75,
                distance_metrics=DistanceOverlayMetrics(
                    depth_distance_m=record.depth_distance_m,
                    image_distance_m=record.image_distance_m,
                    marker_surface_distance_m=record.marker_surface_distance_m,
                    marker_center_guess_distance_m=record.marker_center_guess_distance_m,
                    distance_delta_m=record.distance_delta_m,
                    distance_consistent=record.distance_consistent,
                ),
            )

    @staticmethod
    def _build_rejected_record(
        frame_index: int,
        timestamp_ns: int,
        reject_reason: str,
        marker_ids: Optional[List[int]] = None,
        markers_total: int = 0,
    ) -> FrameCalibrationRecord:
        return FrameCalibrationRecord(
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            success=False,
            marker_ids=marker_ids or [],
            markers_used=0,
            markers_total=markers_total,
            mean_reprojection_error_px=None,
            translation_spread_m=None,
            rotation_spread_deg=None,
            t_camera_cube=None,
            t_world_camera=None,
            reject_reason=reject_reason,
        )

    def _compute_depth_crosscheck(
        self,
        frame_depth: Optional[npt.NDArray[np.uint16]],
        color_shape: Tuple[int, int],
        detections: Sequence[Any],
        t_camera_cube: ArrayF64,
        camera_id: str,
        frame_index: int,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[bool]]:
        depth_distance_m = self._estimate_depth_distance_m(frame_depth, detections, color_shape=color_shape)
        # Compare depth distance (camera optical Z) against pose-estimated cube center Z.
        image_distance_m = float(t_camera_cube[2, 3])

        if depth_distance_m is None or image_distance_m <= 1e-6:
            return depth_distance_m, image_distance_m, None, None, None

        distance_delta_m = abs(depth_distance_m - image_distance_m)
        distance_delta_pct = 100.0 * (distance_delta_m / image_distance_m)
        distance_consistent = (
            distance_delta_m <= self._config.quality.depth_distance_tolerance_m
            and distance_delta_pct <= self._config.quality.depth_distance_tolerance_pct
        )

        if distance_consistent is False and LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(
                "Depth cross-check mismatch camera=%s frame=%s depth=%.3fm image=%.3fm delta=%.3fm (%.2f%%)",
                camera_id,
                frame_index,
                depth_distance_m,
                image_distance_m,
                distance_delta_m,
                distance_delta_pct,
            )

        return depth_distance_m, image_distance_m, distance_delta_m, distance_delta_pct, distance_consistent

    @staticmethod
    def _estimate_depth_distance_m(
        depth: Optional[npt.NDArray[np.uint16]],
        detections: Sequence[Any],
        color_shape: Tuple[int, int],
    ) -> Optional[float]:
        if depth is None or depth.ndim != 2:
            return None
        if not detections:
            return None

        height, width = depth.shape
        color_h, color_w = int(color_shape[0]), int(color_shape[1])
        if color_w <= 0 or color_h <= 0:
            return None
        scale_x = float(width) / float(color_w)
        scale_y = float(height) / float(color_h)

        sampled_depth_mm: List[float] = []

        for detection in detections:
            sampled_depth_mm.extend(
                MultiCameraCalibrator._sample_detection_depths_mm(
                    depth,
                    width,
                    height,
                    detection,
                    scale_x=scale_x,
                    scale_y=scale_y,
                )
            )

        if not sampled_depth_mm:
            return None

        # Femto Bolt depth is reported in millimeters.
        return float(np.median(np.asarray(sampled_depth_mm, dtype=np.float64)) / 1000.0)

    @staticmethod
    def _estimate_marker_center_guess_distance_m(
        detections: Sequence[Any],
        cube_length_m: float,
    ) -> Tuple[Optional[float], Optional[float]]:
        if not detections:
            return None, None

        marker_distances_m: List[float] = []
        for detection in detections:
            tvec = getattr(detection, "tvec", None)
            if tvec is None:
                continue

            tvec_arr = np.asarray(tvec, dtype=np.float64).reshape(3)
            marker_distances_m.append(float(np.linalg.norm(tvec_arr)))

        if not marker_distances_m:
            return None, None

        marker_surface_distance_m = float(np.median(np.asarray(marker_distances_m, dtype=np.float64)))
        # Cube origin is the center; face marker lies on the surface, so add half edge length.
        marker_center_guess_distance_m = marker_surface_distance_m + (float(cube_length_m) / 2.0)
        return marker_surface_distance_m, marker_center_guess_distance_m

    @staticmethod
    def _sample_detection_depths_mm(
        depth: npt.NDArray[np.uint16],
        width: int,
        height: int,
        detection: Any,
        scale_x: float,
        scale_y: float,
    ) -> List[float]:
        corners = getattr(detection, "corners", None)
        if corners is None:
            return []

        points = np.asarray(corners, dtype=np.float64).reshape(-1, 2)
        if points.size == 0:
            return []

        sampled: List[float] = []
        center = np.mean(points, axis=0)
        points_with_center = np.vstack([points, center])

        for x_f, y_f in points_with_center:
            x_i = int(round(float(x_f) * scale_x))
            y_i = int(round(float(y_f) * scale_y))
            if x_i < 0 or y_i < 0 or x_i >= width or y_i >= height:
                continue

            x0 = max(0, x_i - 2)
            x1 = min(width - 1, x_i + 2)
            y0 = max(0, y_i - 2)
            y1 = min(height - 1, y_i + 2)
            patch = depth[y0 : y1 + 1, x0 : x1 + 1]
            if patch.size == 0:
                continue
            valid = patch[patch > 0]
            if valid.size == 0:
                continue
            sampled.append(float(np.median(valid.astype(np.float64))))

        return sampled

    def _finalize_camera_result(self, camera_id: str, timestamp: str, state: _CameraAccumulationState) -> CameraCalibrationResult:
        valid_records = [record for record in state.frames if record.success and record.t_camera_cube is not None]

        if len(valid_records) < self._config.quality.min_valid_frames_per_camera:
            message = (
                f"Not enough valid frame estimates for {camera_id}: "
                f"{len(valid_records)} < {self._config.quality.min_valid_frames_per_camera}"
            )
            return self._build_camera_failure_result(
                camera_id=camera_id,
                timestamp=timestamp,
                state=state,
                message=message,
                inlier_count=0,
            )

        transforms = [record.t_camera_cube for record in valid_records if record.t_camera_cube is not None]
        weights = np.array(
            [
                max(1e-3, 1.0 / max(record.mean_reprojection_error_px or 1.0, 1e-3))
                for record in valid_records
            ],
            dtype=np.float64,
        )

        inlier_indices = self._collect_frame_inliers(transforms=transforms, weights=weights)

        if len(inlier_indices) < self._config.quality.min_valid_frames_per_camera:
            message = (
                f"Insufficient inlier frame estimates for {camera_id}: "
                f"{len(inlier_indices)} < {self._config.quality.min_valid_frames_per_camera}"
            )
            return self._build_camera_failure_result(
                camera_id=camera_id,
                timestamp=timestamp,
                state=state,
                message=message,
                inlier_count=len(inlier_indices),
            )

        inlier_transforms = [transforms[idx] for idx in inlier_indices]
        inlier_weights = [weights[idx] for idx in inlier_indices]
        t_camera_cube = average_transforms(inlier_transforms, weights=inlier_weights)
        t_world_camera = invert_transform(t_camera_cube)

        translation_std, rotation_std = self._compute_pose_stability(
            inlier_transforms=inlier_transforms,
            reference_transform=t_camera_cube,
        )

        stable = (
            translation_std <= self._config.quality.max_translation_std_m
            and rotation_std <= self._config.quality.max_rotation_std_deg
        )

        if stable:
            message = "Calibration succeeded"
            LOGGER.info(
                "Camera %s calibrated: inliers=%s, translation_std=%.4f m, rotation_std=%.3f deg",
                camera_id,
                len(inlier_indices),
                translation_std,
                rotation_std,
            )
        else:
            message = (
                "Calibration unstable: "
                f"translation_std={translation_std:.4f} m, rotation_std={rotation_std:.3f} deg"
            )
            LOGGER.warning("Camera %s %s", camera_id, message)

        quality = self._build_quality_metrics(
            state,
            inlier_count=len(inlier_indices),
            translation_std=translation_std,
            rotation_std=rotation_std,
        )

        return CameraCalibrationResult(
            camera_id=camera_id,
            success=stable,
            message=message,
            timestamp_utc=timestamp,
            t_world_camera=t_world_camera,
            t_camera_world=t_camera_cube,
            t_camera_cube=t_camera_cube,
            markers_used=sorted(state.marker_ids_seen),
            quality=quality,
            per_frame_estimates=state.frames,
        )

    def _build_camera_failure_result(
        self,
        camera_id: str,
        timestamp: str,
        state: _CameraAccumulationState,
        message: str,
        inlier_count: int,
    ) -> CameraCalibrationResult:
        LOGGER.warning(message)
        quality = self._build_quality_metrics(state, inlier_count=inlier_count, translation_std=None, rotation_std=None)
        return CameraCalibrationResult(
            camera_id=camera_id,
            success=False,
            message=message,
            timestamp_utc=timestamp,
            t_world_camera=None,
            t_camera_world=None,
            t_camera_cube=None,
            markers_used=sorted(state.marker_ids_seen),
            quality=quality,
            per_frame_estimates=state.frames,
        )

    def _collect_frame_inliers(self, transforms: Sequence[ArrayF64], weights: np.ndarray) -> List[int]:
        best_indices: List[int] = []
        best_score = -1.0

        for seed_transform in transforms:
            candidate_indices = [
                idx
                for idx, transform in enumerate(transforms)
                if self._is_frame_transform_inlier(transform=transform, reference_transform=seed_transform)
            ]
            candidate_score = float(np.sum(weights[candidate_indices])) if candidate_indices else 0.0

            has_more_inliers = len(candidate_indices) > len(best_indices)
            tied_but_better = len(candidate_indices) == len(best_indices) and candidate_score > best_score
            if has_more_inliers or tied_but_better:
                best_indices = candidate_indices
                best_score = candidate_score

        if not best_indices:
            return []

        preliminary_transforms = [transforms[idx] for idx in best_indices]
        preliminary_weights = [weights[idx] for idx in best_indices]
        preliminary_mean = average_transforms(preliminary_transforms, weights=preliminary_weights)

        refined_indices = [
            idx
            for idx, transform in enumerate(transforms)
            if self._is_frame_transform_inlier(transform=transform, reference_transform=preliminary_mean)
        ]

        if len(refined_indices) >= self._config.quality.min_valid_frames_per_camera:
            return refined_indices
        return best_indices

    def _is_frame_transform_inlier(self, transform: ArrayF64, reference_transform: ArrayF64) -> bool:
        translation_delta = float(np.linalg.norm(transform[:3, 3] - reference_transform[:3, 3]))
        rotation_delta = rotation_angle_deg(transform[:3, :3], reference_transform[:3, :3])
        return (
            translation_delta <= self._config.quality.frame_outlier_translation_m
            and rotation_delta <= self._config.quality.frame_outlier_rotation_deg
        )

    @staticmethod
    def _compute_pose_stability(inlier_transforms: Sequence[ArrayF64], reference_transform: ArrayF64) -> Tuple[float, float]:
        translation_residuals = np.array(
            [
                np.linalg.norm(transform[:3, 3] - reference_transform[:3, 3])
                for transform in inlier_transforms
            ],
            dtype=np.float64,
        )
        rotation_residuals = np.array(
            [
                rotation_angle_deg(transform[:3, :3], reference_transform[:3, :3])
                for transform in inlier_transforms
            ],
            dtype=np.float64,
        )
        return float(np.std(translation_residuals)), float(np.std(rotation_residuals))

    def _build_quality_metrics(
        self,
        state: _CameraAccumulationState,
        inlier_count: int,
        translation_std: Optional[float],
        rotation_std: Optional[float],
    ) -> CameraQualityMetrics:
        valid_frame_estimates = sum(1 for record in state.frames if record.success)

        mean_reprojection = None
        if state.reprojection_errors:
            mean_reprojection = float(np.mean(np.asarray(state.reprojection_errors, dtype=np.float64)))

        return CameraQualityMetrics(
            frames_requested=self._config.frame_count,
            frames_processed=state.frames_processed,
            valid_frame_estimates=valid_frame_estimates,
            inlier_frame_estimates=inlier_count,
            total_marker_detections=state.total_marker_detections,
            valid_marker_observations=state.valid_marker_observations,
            unique_markers_seen=sorted(state.marker_ids_seen),
            mean_reprojection_error_px=mean_reprojection,
            translation_std_m=translation_std,
            rotation_std_deg=rotation_std,
        )

    def _failure_result_for_camera(self, camera_id: str, message: str, timestamp: str) -> CameraCalibrationResult:
        quality = CameraQualityMetrics(
            frames_requested=self._config.frame_count,
            frames_processed=0,
            valid_frame_estimates=0,
            inlier_frame_estimates=0,
            total_marker_detections=0,
            valid_marker_observations=0,
            unique_markers_seen=[],
            mean_reprojection_error_px=None,
            translation_std_m=None,
            rotation_std_deg=None,
        )
        return CameraCalibrationResult(
            camera_id=camera_id,
            success=False,
            message=message,
            timestamp_utc=timestamp,
            t_world_camera=None,
            t_camera_world=None,
            t_camera_cube=None,
            markers_used=[],
            quality=quality,
            per_frame_estimates=[],
        )

