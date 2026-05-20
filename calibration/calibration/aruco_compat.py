from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import numpy.typing as npt

ArrayF64 = npt.NDArray[np.float64]

LOGGER = logging.getLogger(__name__)


def ensure_aruco_available() -> None:
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("OpenCV ArUco module is not available (install opencv-contrib-python)")


def make_aruco_dictionary(dictionary_id: int) -> Any:
    ensure_aruco_available()
    try:
        return cv2.aruco.getPredefinedDictionary(int(dictionary_id))
    except Exception as exc:
        raise RuntimeError(f"Failed to load ArUco dictionary ID {dictionary_id}: {exc}") from exc


def make_detector_parameters() -> Any:
    ensure_aruco_available()
    if hasattr(cv2.aruco, "DetectorParameters"):
        return cv2.aruco.DetectorParameters()
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        return cv2.aruco.DetectorParameters_create()
    raise RuntimeError("Unsupported OpenCV ArUco API: no DetectorParameters constructor found")


def make_aruco_detector(dictionary: Any, params: Any) -> Optional[Any]:
    ensure_aruco_available()
    if hasattr(cv2.aruco, "ArucoDetector"):
        return cv2.aruco.ArucoDetector(dictionary, params)
    return None


def detect_markers(gray_image: npt.NDArray[np.uint8], dictionary: any, params: any, detector: Optional[any] = None):
    if detector is not None:
        return detector.detectMarkers(gray_image)
    return cv2.aruco.detectMarkers(gray_image, dictionary, parameters=params)


def draw_detected_markers(image_bgr: npt.NDArray[np.uint8], corners: Sequence[ArrayF64], ids: Sequence[int]) -> None:
    ensure_aruco_available()
    if not corners:
        return
    marker_ids = np.asarray([int(x) for x in ids], dtype=np.int32).reshape(-1, 1)
    marker_corners = [np.asarray(corner, dtype=np.float32).reshape(1, 4, 2) for corner in corners]
    cv2.aruco.drawDetectedMarkers(image_bgr, marker_corners, marker_ids)


def _marker_object_points(marker_length: float) -> ArrayF64:
    half = float(marker_length) / 2.0
    return np.array(
        [
            [-half, +half, 0.0],
            [+half, +half, 0.0],
            [+half, -half, 0.0],
            [-half, -half, 0.0],
        ],
        dtype=np.float64,
    )


def _marker_facing_score(rvec: ArrayF64, tvec: ArrayF64) -> float:
    rotation, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    marker_normal_cam = rotation @ np.array([0.0, 0.0, 1.0], dtype=np.float64)
    view_direction = -np.asarray(tvec, dtype=np.float64).reshape(3)
    view_direction /= max(float(np.linalg.norm(view_direction)), 1e-12)
    return float(np.dot(marker_normal_cam, view_direction))


def _extract_reprojection_error(reprojection_errors: Optional[Any], idx: int) -> float:
    if reprojection_errors is None or len(reprojection_errors) <= idx:
        return float("inf")
    return float(np.asarray(reprojection_errors[idx], dtype=np.float64).reshape(-1)[0])


def _pick_disambiguated_ippe_candidate(
    rvec_candidates: Any,
    tvec_candidates: Any,
    reprojection_errors: Optional[Any],
) -> Optional[Tuple[ArrayF64, ArrayF64, str]]:
    if rvec_candidates is None or tvec_candidates is None or len(rvec_candidates) == 0:
        return None

    front_facing: List[Tuple[ArrayF64, ArrayF64, float, float]] = []
    z_positive: List[Tuple[ArrayF64, ArrayF64, float]] = []

    for idx in range(len(rvec_candidates)):
        rvec = np.asarray(rvec_candidates[idx], dtype=np.float64).reshape(3)
        tvec = np.asarray(tvec_candidates[idx], dtype=np.float64).reshape(3)
        if float(tvec[2]) <= 0.0:
            continue

        reproj = _extract_reprojection_error(reprojection_errors, idx)
        z_positive.append((rvec, tvec, reproj))

        facing = _marker_facing_score(rvec, tvec)
        if facing > 0.0:
            front_facing.append((rvec, tvec, facing, reproj))

    if front_facing:
        front_facing.sort(key=lambda item: (-item[2], item[3]))
        rvec, tvec, _, _ = front_facing[0]
        return rvec, tvec, "solvePnPGeneric(IPPE_SQUARE)-disambiguated"

    if z_positive:
        z_positive.sort(key=lambda item: item[2])
        rvec, tvec, _ = z_positive[0]
        return rvec, tvec, "solvePnPGeneric(IPPE_SQUARE)-zpositive"

    return None


def _try_estimate_pose_ippe_generic(
    object_points: ArrayF64,
    image_points: ArrayF64,
    camera_matrix: ArrayF64,
    dist_coeffs: ArrayF64,
) -> Optional[Tuple[ArrayF64, ArrayF64, str]]:
    if not (hasattr(cv2, "solvePnPGeneric") and hasattr(cv2, "SOLVEPNP_IPPE_SQUARE")):
        return None

    try:
        result = cv2.solvePnPGeneric(
            object_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=int(cv2.SOLVEPNP_IPPE_SQUARE),
        )
        if len(result) < 3:
            return None

        success = bool(result[0])
        if not success:
            return None

        rvec_candidates = result[1]
        tvec_candidates = result[2]
        reprojection_errors = result[3] if len(result) >= 4 else None
        return _pick_disambiguated_ippe_candidate(rvec_candidates, tvec_candidates, reprojection_errors)
    except Exception as exc:
        LOGGER.debug("solvePnPGeneric(IPPE_SQUARE) failed, will try other methods: %s", exc)
        return None


def estimate_pose_single_marker(
    marker_corners: ArrayF64,
    marker_length: float,
    camera_matrix: ArrayF64,
    dist_coeffs: ArrayF64,
) -> Tuple[bool, Optional[ArrayF64], Optional[ArrayF64], str]:
    corners = np.asarray(marker_corners, dtype=np.float64).reshape(1, 4, 2)
    camera_matrix_arr = np.asarray(camera_matrix, dtype=np.float64)
    dist_coeffs_arr = np.asarray(dist_coeffs, dtype=np.float64)
    object_points = _marker_object_points(marker_length)
    image_points = np.asarray(marker_corners, dtype=np.float64).reshape(4, 2)

    generic_pose = _try_estimate_pose_ippe_generic(
        object_points=object_points,
        image_points=image_points,
        camera_matrix=camera_matrix_arr,
        dist_coeffs=dist_coeffs_arr,
    )
    if generic_pose is not None:
        rvec, tvec, method = generic_pose
        return True, rvec, tvec, method

    # Newer/older OpenCV builds may expose this function differently or not at all.
    if hasattr(cv2.aruco, "estimatePoseSingleMarkers"):
        try:
            rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
                corners,
                float(marker_length),
                camera_matrix_arr,
                dist_coeffs_arr,
            )
            if rvecs is None or tvecs is None or len(rvecs) < 1:
                return False, None, None, "estimatePoseSingleMarkers-empty"
            rvec = np.asarray(rvecs[0], dtype=np.float64).reshape(3)
            tvec = np.asarray(tvecs[0], dtype=np.float64).reshape(3)
            return True, rvec, tvec, "estimatePoseSingleMarkers"
        except Exception as exc:
            LOGGER.debug("estimatePoseSingleMarkers failed, will try solvePnP fallback: %s", exc)

    pnp_flags: List[int] = []
    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        pnp_flags.append(cv2.SOLVEPNP_IPPE_SQUARE)
    pnp_flags.append(cv2.SOLVEPNP_ITERATIVE)

    for flag in pnp_flags:
        try:
            success, rvec, tvec = cv2.solvePnP(
                object_points,
                image_points,
                camera_matrix_arr,
                dist_coeffs_arr,
                flags=int(flag),
            )
            if success:
                return True, np.asarray(rvec, dtype=np.float64).reshape(3), np.asarray(tvec, dtype=np.float64).reshape(3), f"solvePnP(flag={flag})"
        except Exception as exc:
            LOGGER.debug("solvePnP failed (flag=%s): %s", flag, exc)

    return False, None, None, "pose-estimation-failed"
