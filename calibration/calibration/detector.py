from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

import cv2
import numpy as np
import numpy.typing as npt

from calibration.calibration.aruco_compat import (
    detect_markers,
    estimate_pose_single_marker,
    make_aruco_detector,
    make_aruco_dictionary,
    make_detector_parameters,
)
from calibration.camera.base import CameraFrame, CameraIntrinsics

ArrayF64 = npt.NDArray[np.float64]
LOGGER = logging.getLogger(__name__)


@dataclass
class MarkerObservation2D:
    marker_id: int
    corners: ArrayF64


@dataclass
class MarkerDetection:
    marker_id: int
    rvec: ArrayF64
    tvec: ArrayF64
    reprojection_error_px: float
    confidence: float
    corners: Optional[ArrayF64] = None
    pose_method: str = "unknown"


class ArucoMarkerDetector:
    def __init__(self, dictionary_id: int, marker_length: float, enable_diagnostics: bool = False) -> None:
        self._dictionary = make_aruco_dictionary(int(dictionary_id))
        self._marker_length = float(marker_length)
        self._enable_diagnostics = bool(enable_diagnostics)

        self._params = make_detector_parameters()
        self._aruco_detector = make_aruco_detector(self._dictionary, self._params)

        half = self._marker_length / 2.0
        self._marker_object_points = np.array(
            [
                [-half, +half, 0.0],
                [+half, +half, 0.0],
                [+half, -half, 0.0],
                [-half, -half, 0.0],
            ],
            dtype=np.float64,
        )

    def detect_markers_2d(self, frame: CameraFrame) -> List[MarkerObservation2D]:
        if frame.color is None:
            return []

        if frame.color.ndim != 3 or frame.color.shape[2] not in (3, 4):
            raise RuntimeError(
                f"Unsupported frame resolution/format for marker detection: shape={frame.color.shape}"
            )

        if frame.color.shape[2] == 4:
            gray = cv2.cvtColor(frame.color, cv2.COLOR_BGRA2GRAY)
        else:
            gray = cv2.cvtColor(frame.color, cv2.COLOR_BGR2GRAY)

        corners, ids, _ = detect_markers(
            gray_image=gray,
            dictionary=self._dictionary,
            params=self._params,
            detector=self._aruco_detector,
        )

        if ids is None or len(ids) == 0:
            if self._enable_diagnostics:
                LOGGER.debug("No markers detected in frame=%s camera=%s", frame.frame_index, frame.camera_id)
            return []

        marker_ids = [int(marker_id) for marker_id in ids.flatten().tolist()]
        observations: List[MarkerObservation2D] = []
        for idx, marker_id in enumerate(marker_ids):
            marker_corners = np.asarray(corners[idx], dtype=np.float64).reshape(4, 2)
            observations.append(MarkerObservation2D(marker_id=marker_id, corners=marker_corners))

        if self._enable_diagnostics:
            LOGGER.debug(
                "Detected markers camera=%s frame=%s ids=%s corners=%s",
                frame.camera_id,
                frame.frame_index,
                marker_ids,
                len(observations),
            )

        return observations

    def estimate_marker_poses(
        self,
        marker_observations: Sequence[MarkerObservation2D],
        intrinsics: CameraIntrinsics,
        max_reprojection_error_px: float,
    ) -> List[MarkerDetection]:
        intrinsics.validate()
        detections: List[MarkerDetection] = []

        for marker in marker_observations:
            success, rvec, tvec, pose_method = estimate_pose_single_marker(
                marker_corners=marker.corners,
                marker_length=self._marker_length,
                camera_matrix=intrinsics.camera_matrix,
                dist_coeffs=intrinsics.dist_coeffs,
            )

            if not success or rvec is None or tvec is None:
                LOGGER.warning("Marker %s detected but pose estimation failed", marker.marker_id)
                continue

            reproj_error = self._compute_reprojection_error(
                rvec=rvec,
                tvec=tvec,
                observed_corners=marker.corners,
                intrinsics=intrinsics,
            )

            if reproj_error > max_reprojection_error_px:
                if self._enable_diagnostics:
                    LOGGER.debug(
                        "Rejected marker %s by reprojection threshold: error=%.3f > %.3f",
                        marker.marker_id,
                        reproj_error,
                        max_reprojection_error_px,
                    )
                continue

            confidence = float(np.clip(1.0 - reproj_error / max_reprojection_error_px, 0.0, 1.0))
            detection = MarkerDetection(
                marker_id=marker.marker_id,
                rvec=np.asarray(rvec, dtype=np.float64).reshape(3),
                tvec=np.asarray(tvec, dtype=np.float64).reshape(3),
                reprojection_error_px=float(reproj_error),
                confidence=confidence,
                corners=marker.corners,
                pose_method=pose_method,
            )
            detections.append(detection)

            if self._enable_diagnostics:
                LOGGER.debug(
                    "Pose marker=%s method=%s rvec=%s tvec=%s error=%.3f",
                    marker.marker_id,
                    pose_method,
                    detection.rvec.tolist(),
                    detection.tvec.tolist(),
                    detection.reprojection_error_px,
                )

        return detections

    def detect(self, frame: CameraFrame, intrinsics: CameraIntrinsics, max_reprojection_error_px: float) -> List[MarkerDetection]:
        if frame.simulated_marker_poses:
            return [
                MarkerDetection(
                    marker_id=int(sim.marker_id),
                    rvec=np.asarray(sim.rvec, dtype=np.float64).reshape(3),
                    tvec=np.asarray(sim.tvec, dtype=np.float64).reshape(3),
                    reprojection_error_px=float(sim.reprojection_error_px),
                    confidence=float(sim.confidence),
                    corners=None,
                    pose_method="simulated",
                )
                for sim in frame.simulated_marker_poses
            ]

        marker_observations = self.detect_markers_2d(frame)
        return self.estimate_marker_poses(
            marker_observations=marker_observations,
            intrinsics=intrinsics,
            max_reprojection_error_px=max_reprojection_error_px,
        )

    def _compute_reprojection_error(
        self,
        rvec: Sequence[float],
        tvec: Sequence[float],
        observed_corners: ArrayF64,
        intrinsics: CameraIntrinsics,
    ) -> float:
        projected, _ = cv2.projectPoints(
            self._marker_object_points,
            np.asarray(rvec, dtype=np.float64).reshape(3, 1),
            np.asarray(tvec, dtype=np.float64).reshape(3, 1),
            intrinsics.camera_matrix,
            intrinsics.dist_coeffs,
        )
        projected_2d = projected.reshape(-1, 2)
        error = np.linalg.norm(projected_2d - observed_corners, axis=1)
        return float(np.mean(error))

