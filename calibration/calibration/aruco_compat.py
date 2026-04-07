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


def estimate_pose_single_marker(
    marker_corners: ArrayF64,
    marker_length: float,
    camera_matrix: ArrayF64,
    dist_coeffs: ArrayF64,
) -> Tuple[bool, Optional[ArrayF64], Optional[ArrayF64], str]:
    corners = np.asarray(marker_corners, dtype=np.float64).reshape(1, 4, 2)

    # Newer/older OpenCV builds may expose this function differently or not at all.
    if hasattr(cv2.aruco, "estimatePoseSingleMarkers"):
        try:
            rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
                corners,
                float(marker_length),
                np.asarray(camera_matrix, dtype=np.float64),
                np.asarray(dist_coeffs, dtype=np.float64),
            )
            if rvecs is None or tvecs is None or len(rvecs) < 1:
                return False, None, None, "estimatePoseSingleMarkers-empty"
            rvec = np.asarray(rvecs[0], dtype=np.float64).reshape(3)
            tvec = np.asarray(tvecs[0], dtype=np.float64).reshape(3)
            return True, rvec, tvec, "estimatePoseSingleMarkers"
        except Exception as exc:
            LOGGER.debug("estimatePoseSingleMarkers failed, will try solvePnP fallback: %s", exc)

    half = float(marker_length) / 2.0
    object_points = np.array(
        [
            [-half, +half, 0.0],
            [+half, +half, 0.0],
            [+half, -half, 0.0],
            [-half, -half, 0.0],
        ],
        dtype=np.float64,
    )
    image_points = np.asarray(marker_corners, dtype=np.float64).reshape(4, 2)

    pnp_flags: List[int] = []
    if hasattr(cv2, "SOLVEPNP_IPPE_SQUARE"):
        pnp_flags.append(cv2.SOLVEPNP_IPPE_SQUARE)
    pnp_flags.append(cv2.SOLVEPNP_ITERATIVE)

    for flag in pnp_flags:
        try:
            success, rvec, tvec = cv2.solvePnP(
                object_points,
                image_points,
                np.asarray(camera_matrix, dtype=np.float64),
                np.asarray(dist_coeffs, dtype=np.float64),
                flags=int(flag),
            )
            if success:
                return True, np.asarray(rvec, dtype=np.float64).reshape(3), np.asarray(tvec, dtype=np.float64).reshape(3), f"solvePnP(flag={flag})"
        except Exception as exc:
            LOGGER.debug("solvePnP failed (flag=%s): %s", flag, exc)

    return False, None, None, "pose-estimation-failed"
