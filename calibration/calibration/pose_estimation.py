from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np
import numpy.typing as npt

from calibration.calibration.aruco_cube import ArucoCubeModel
from calibration.calibration.detector import MarkerDetection
from calibration.math3d.transforms import (
    average_transforms,
    compose_transforms,
    invert_transform,
    rotation_angle_deg,
    rvec_tvec_to_transform,
)

ArrayF64 = npt.NDArray[np.float64]


@dataclass
class CubePoseObservation:
    marker_id: int
    face_name: str
    t_camera_cube: ArrayF64
    reprojection_error_px: float
    confidence: float


@dataclass
class FrameCubePoseEstimate:
    t_camera_cube: ArrayF64
    marker_ids: List[int]
    used_observation_count: int
    total_observation_count: int
    mean_reprojection_error_px: float
    translation_spread_m: float
    rotation_spread_deg: float


def marker_detections_to_cube_observations(
    detections: Sequence[MarkerDetection],
    cube_model: ArucoCubeModel,
) -> List[CubePoseObservation]:
    observations: List[CubePoseObservation] = []

    for detection in detections:
        face_name = cube_model.marker_id_to_face(detection.marker_id)
        if face_name is None:
            continue

        face_transform = cube_model.get_transform_for_marker_id(detection.marker_id)

        # OpenCV pose estimate: T_camera_marker maps marker-frame points to camera-frame points.
        t_camera_marker = rvec_tvec_to_transform(detection.rvec, detection.tvec)

        # Cube model provides T_cube_marker. Therefore:
        # T_camera_cube = T_camera_marker * inverse(T_cube_marker)
        t_camera_cube = compose_transforms(t_camera_marker, invert_transform(face_transform.t_cube_marker))

        observations.append(
            CubePoseObservation(
                marker_id=detection.marker_id,
                face_name=face_name,
                t_camera_cube=t_camera_cube,
                reprojection_error_px=float(detection.reprojection_error_px),
                confidence=float(detection.confidence),
            )
        )

    return observations


def _is_inlier(
    candidate_transform: ArrayF64,
    reference_transform: ArrayF64,
    translation_threshold_m: float,
    rotation_threshold_deg: float,
) -> bool:
    translation_delta = float(np.linalg.norm(candidate_transform[:3, 3] - reference_transform[:3, 3]))
    rotation_delta = rotation_angle_deg(candidate_transform[:3, :3], reference_transform[:3, :3])
    return translation_delta <= translation_threshold_m and rotation_delta <= rotation_threshold_deg


def _collect_inlier_indices(
    observations: Sequence[CubePoseObservation],
    reference_transform: ArrayF64,
    translation_threshold_m: float,
    rotation_threshold_deg: float,
) -> List[int]:
    return [
        idx
        for idx, obs in enumerate(observations)
        if _is_inlier(
            candidate_transform=obs.t_camera_cube,
            reference_transform=reference_transform,
            translation_threshold_m=translation_threshold_m,
            rotation_threshold_deg=rotation_threshold_deg,
        )
    ]


def _best_consensus_inliers(
    observations: Sequence[CubePoseObservation],
    weights: np.ndarray,
    translation_threshold_m: float,
    rotation_threshold_deg: float,
) -> List[int]:
    best_inlier_indices: List[int] = []
    best_inlier_score = -1.0

    for seed_transform in [obs.t_camera_cube for obs in observations]:
        candidate_inliers = _collect_inlier_indices(
            observations=observations,
            reference_transform=seed_transform,
            translation_threshold_m=translation_threshold_m,
            rotation_threshold_deg=rotation_threshold_deg,
        )
        candidate_score = float(np.sum(weights[candidate_inliers])) if candidate_inliers else 0.0

        has_more_inliers = len(candidate_inliers) > len(best_inlier_indices)
        same_count_better_score = len(candidate_inliers) == len(best_inlier_indices) and candidate_score > best_inlier_score
        if has_more_inliers or same_count_better_score:
            best_inlier_indices = candidate_inliers
            best_inlier_score = candidate_score

    return best_inlier_indices


def estimate_frame_cube_pose(
    observations: Sequence[CubePoseObservation],
    min_markers_per_frame: int,
    marker_outlier_translation_m: float,
    marker_outlier_rotation_deg: float,
) -> Optional[FrameCubePoseEstimate]:
    if len(observations) < min_markers_per_frame:
        return None

    weights = np.array([max(obs.confidence, 1e-4) for obs in observations], dtype=np.float64)

    best_inlier_indices = _best_consensus_inliers(
        observations=observations,
        weights=weights,
        translation_threshold_m=marker_outlier_translation_m,
        rotation_threshold_deg=marker_outlier_rotation_deg,
    )

    if len(best_inlier_indices) < min_markers_per_frame:
        return None

    preliminary_transforms = [observations[idx].t_camera_cube for idx in best_inlier_indices]
    preliminary_weights = [weights[idx] for idx in best_inlier_indices]
    preliminary_mean = average_transforms(preliminary_transforms, weights=preliminary_weights)

    refined_inlier_indices = _collect_inlier_indices(
        observations=observations,
        reference_transform=preliminary_mean,
        translation_threshold_m=marker_outlier_translation_m,
        rotation_threshold_deg=marker_outlier_rotation_deg,
    )

    inlier_indices = refined_inlier_indices if len(refined_inlier_indices) >= min_markers_per_frame else best_inlier_indices

    inlier_transforms = [observations[idx].t_camera_cube for idx in inlier_indices]
    inlier_weights = [weights[idx] for idx in inlier_indices]
    final_mean = average_transforms(inlier_transforms, weights=inlier_weights)

    reprojection_errors = np.array([observations[idx].reprojection_error_px for idx in inlier_indices], dtype=np.float64)

    translation_residuals = np.array(
        [
            np.linalg.norm(observations[idx].t_camera_cube[:3, 3] - final_mean[:3, 3])
            for idx in inlier_indices
        ],
        dtype=np.float64,
    )
    rotation_residuals = np.array(
        [
            rotation_angle_deg(observations[idx].t_camera_cube[:3, :3], final_mean[:3, :3])
            for idx in inlier_indices
        ],
        dtype=np.float64,
    )

    marker_ids = sorted({observations[idx].marker_id for idx in inlier_indices})

    return FrameCubePoseEstimate(
        t_camera_cube=final_mean,
        marker_ids=marker_ids,
        used_observation_count=len(inlier_indices),
        total_observation_count=len(observations),
        mean_reprojection_error_px=float(np.mean(reprojection_errors)),
        translation_spread_m=float(np.std(translation_residuals)),
        rotation_spread_deg=float(np.std(rotation_residuals)),
    )

