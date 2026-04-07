from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from calibration.calibration.multi_camera_calibrator import CalibrationRunResult, CameraCalibrationResult, FrameCalibrationRecord
from calibration.config import CalibrationConfig


def _matrix_or_none(matrix: Optional[np.ndarray]) -> Optional[List[List[float]]]:
    if matrix is None:
        return None
    return np.asarray(matrix, dtype=np.float64).tolist()


def _vector_or_none(vector: Optional[np.ndarray]) -> Optional[List[float]]:
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float64).reshape(-1).tolist()


def _camera_result_to_dict(camera_result: CameraCalibrationResult) -> Dict[str, Any]:
    world_matrix = camera_result.t_world_camera
    rotation = None
    translation = None
    if world_matrix is not None:
        rotation = np.asarray(world_matrix[:3, :3], dtype=np.float64)
        translation = np.asarray(world_matrix[:3, 3], dtype=np.float64)

    return {
        "camera_id": camera_result.camera_id,
        "success": camera_result.success,
        "message": camera_result.message,
        "timestamp": camera_result.timestamp_utc,
        "T_world_camera": _matrix_or_none(camera_result.t_world_camera),
        "T_camera_world": _matrix_or_none(camera_result.t_camera_world),
        "T_camera_cube": _matrix_or_none(camera_result.t_camera_cube),
        "rotation_matrix_world_camera": _matrix_or_none(rotation),
        "translation_world_camera": _vector_or_none(translation),
        "markers_used": list(camera_result.markers_used),
        "quality_metrics": {
            "frames_requested": camera_result.quality.frames_requested,
            "frames_processed": camera_result.quality.frames_processed,
            "valid_frame_estimates": camera_result.quality.valid_frame_estimates,
            "inlier_frame_estimates": camera_result.quality.inlier_frame_estimates,
            "total_marker_detections": camera_result.quality.total_marker_detections,
            "valid_marker_observations": camera_result.quality.valid_marker_observations,
            "unique_markers_seen": list(camera_result.quality.unique_markers_seen),
            "mean_reprojection_error_px": camera_result.quality.mean_reprojection_error_px,
            "translation_std_m": camera_result.quality.translation_std_m,
            "rotation_std_deg": camera_result.quality.rotation_std_deg,
        },
    }


def _frame_record_to_dict(record: FrameCalibrationRecord) -> Dict[str, Any]:
    return {
        "frame_index": record.frame_index,
        "timestamp_ns": record.timestamp_ns,
        "success": record.success,
        "marker_ids": list(record.marker_ids),
        "markers_used": record.markers_used,
        "markers_total": record.markers_total,
        "mean_reprojection_error_px": record.mean_reprojection_error_px,
        "translation_spread_m": record.translation_spread_m,
        "rotation_spread_deg": record.rotation_spread_deg,
        "T_camera_cube": _matrix_or_none(record.t_camera_cube),
        "T_world_camera": _matrix_or_none(record.t_world_camera),
        "depth_distance_m": record.depth_distance_m,
        "image_distance_m": record.image_distance_m,
        "marker_surface_distance_m": record.marker_surface_distance_m,
        "marker_center_guess_distance_m": record.marker_center_guess_distance_m,
        "distance_delta_m": record.distance_delta_m,
        "distance_delta_pct": record.distance_delta_pct,
        "distance_consistent": record.distance_consistent,
        "reject_reason": record.reject_reason,
    }


def export_calibration_results(
    run_result: CalibrationRunResult,
    config: CalibrationConfig,
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    final_json = {
        "timestamp_utc": run_result.timestamp_utc,
        "world_origin": config.world_origin,
        "successful_cameras": run_result.successful_cameras,
        "failed_cameras": run_result.failed_cameras,
        "camera_count": len(run_result.camera_results),
        "cameras": [_camera_result_to_dict(result) for result in run_result.camera_results],
    }

    per_frame_json = {
        "timestamp_utc": run_result.timestamp_utc,
        "frame_count_requested": config.frame_count,
        "cameras": [
            {
                "camera_id": result.camera_id,
                "frames": [_frame_record_to_dict(record) for record in result.per_frame_estimates],
            }
            for result in run_result.camera_results
        ],
    }

    summary_path = output_dir / "final_calibration.json"
    frames_path = output_dir / "per_frame_estimates.json"

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(final_json, f, indent=2)

    with frames_path.open("w", encoding="utf-8") as f:
        json.dump(per_frame_json, f, indent=2)

    return {
        "final_calibration": summary_path,
        "per_frame_estimates": frames_path,
    }
