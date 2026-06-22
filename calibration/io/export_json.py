from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from calibration.calibration.multi_camera_calibrator import CalibrationRunResult, CameraCalibrationResult, FrameCalibrationRecord
from calibration.config import CalibrationConfig
from calibration.math3d.transforms import invert_transform, rotation_matrix_to_quaternion


def _matrix_or_none(matrix: Optional[np.ndarray]) -> Optional[List[List[float]]]:
    if matrix is None:
        return None
    return np.asarray(matrix, dtype=np.float64).tolist()


def _vector_or_none(vector: Optional[np.ndarray]) -> Optional[List[float]]:
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float64).reshape(-1).tolist()


def _transform_or_none(transform: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if transform is None:
        return None
    return np.asarray(transform, dtype=np.float64)


def _convert_transform_to_unity(transform: Optional[np.ndarray]) -> Optional[np.ndarray]:
    transform_arr = _transform_or_none(transform)
    if transform_arr is None:
        return None

    # Convert from the calibration right-handed frame to Unity's left-handed frame by flipping Z.
    flip_z = np.diag([1.0, 1.0, -1.0])
    rotation = transform_arr[:3, :3]
    translation = transform_arr[:3, 3]

    unity_rotation = flip_z @ rotation @ flip_z
    unity_translation = flip_z @ translation

    unity_transform = np.eye(4, dtype=np.float64)
    unity_transform[:3, :3] = unity_rotation
    unity_transform[:3, 3] = unity_translation
    return unity_transform


def _unity_pose_from_world_camera_transform(t_world_camera: Optional[np.ndarray]) -> Dict[str, Any]:
    unity_world_camera = _convert_transform_to_unity(t_world_camera)
    if unity_world_camera is None:
        return {
            "T_world_camera": None,
            "T_camera_world": None,
            "rotation_matrix_world_camera": None,
            "translation_world_camera": None,
            "rotation_quaternion_xyzw_world_camera": None,
        }

    unity_rotation = unity_world_camera[:3, :3]
    unity_translation = unity_world_camera[:3, 3]
    unity_camera_world = invert_transform(unity_world_camera)
    quaternion_wxyz = rotation_matrix_to_quaternion(unity_rotation)
    quaternion_xyzw = [
        float(quaternion_wxyz[1]),
        float(quaternion_wxyz[2]),
        float(quaternion_wxyz[3]),
        float(quaternion_wxyz[0]),
    ]

    return {
        "T_world_camera": _matrix_or_none(unity_world_camera),
        "T_camera_world": _matrix_or_none(unity_camera_world),
        "rotation_matrix_world_camera": _matrix_or_none(unity_rotation),
        "translation_world_camera": _vector_or_none(unity_translation),
        "rotation_quaternion_xyzw_world_camera": quaternion_xyzw,
    }


def _camera_result_to_dict(camera_result: CameraCalibrationResult) -> Dict[str, Any]:
    world_matrix = camera_result.t_world_camera
    rotation = None
    translation = None
    if world_matrix is not None:
        rotation = np.asarray(world_matrix[:3, :3], dtype=np.float64)
        translation = np.asarray(world_matrix[:3, 3], dtype=np.float64)

    unity_pose = _unity_pose_from_world_camera_transform(world_matrix)

    return {
        "camera_id": camera_result.camera_id,
        "success": camera_result.success,
        "message": camera_result.message,
        "timestamp": camera_result.timestamp_utc,
        "T_world_camera": _matrix_or_none(camera_result.t_world_camera),
        "T_camera_world": _matrix_or_none(camera_result.t_camera_world),
        "T_camera_cube": _matrix_or_none(camera_result.t_camera_cube),
        "T_RGB_depth": _matrix_or_none(camera_result.t_depth_color),
        "T_RGB_depth_valid": camera_result.depth_color_valid,
        "rotation_matrix_world_camera": _matrix_or_none(rotation),
        "translation_world_camera": _vector_or_none(translation),
        "unity": unity_pose,
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
        "pose_method": record.pose_method,
        "pnp_reprojection_error_px": record.pnp_reprojection_error_px,
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
        "coordinate_system": {
            "calibration": "right-handed (x right, y up, z forward)",
            "unity": "left-handed (x right, y up, z forward)",
            "unity_conversion": "flip z axis (position z *= -1, rotation R_unity = S * R * S where S=diag(1,1,-1))",
        },
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

