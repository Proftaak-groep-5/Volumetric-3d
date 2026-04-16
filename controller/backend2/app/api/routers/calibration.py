from __future__ import annotations

import base64
import logging
from typing import Annotated

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_app_state
from app.services.app_state import BackendAppState


logger = logging.getLogger(__name__)
router = APIRouter()

StateDep = Annotated[BackendAppState, Depends(get_app_state)]

DESC_FIRST_CAMERA_ID = "First camera ID"
DESC_SECOND_CAMERA_ID = "Second camera ID"
DESC_CHECKERBOARD_COLS = "Number of inner corners (columns)"
DESC_CHECKERBOARD_ROWS = "Number of inner corners (rows)"
DESC_SQUARE_SIZE = "Square size in meters"

FRAME_NOT_AVAILABLE = "Frame not available"
COLOR_DATA_NOT_AVAILABLE = "Color data not available"

CameraId1Query = Annotated[str, Query(..., description=DESC_FIRST_CAMERA_ID)]
CameraId2Query = Annotated[str, Query(..., description=DESC_SECOND_CAMERA_ID)]
CheckerboardColsQuery = Annotated[int, Query(8, description=DESC_CHECKERBOARD_COLS)]
CheckerboardRowsQuery = Annotated[int, Query(5, description=DESC_CHECKERBOARD_ROWS)]
SquareSizeQuery = Annotated[float, Query(0.025, description=DESC_SQUARE_SIZE)]

RESPONSE_400 = {"description": "Bad Request"}
RESPONSE_404 = {"description": "Not Found"}
RESPONSE_500 = {"description": "Internal Server Error"}


@router.get("/api/calibration/status")
async def get_calibration_status(state: StateDep) -> dict:
    cameras_status: dict[str, dict] = {}
    stereo_status: dict[str, dict] = {}

    camera_infos = state.camera_service.list_cameras()
    camera_ids = [camera.camera_id for camera in camera_infos]

    for camera in camera_infos:
        depth_intrinsics = state.camera_service.get_depth_intrinsics(camera.camera_id)
        has_external_pose = state.calibration_service.has_camera(camera.camera_id)

        cameras_status[camera.camera_id] = {
            "calibrated": bool(has_external_pose or depth_intrinsics),
            "has_intrinsics": depth_intrinsics is not None,
            "depth_resolution": camera.depth_resolution,
            "color_resolution": camera.color_resolution,
            "intrinsics": depth_intrinsics.as_dict() if depth_intrinsics else None,
        }

    for index, cam_1 in enumerate(camera_ids):
        for cam_2 in camera_ids[index + 1 :]:
            key = f"{cam_1}_{cam_2}"
            stereo = state.calibration_service.get_stereo_transform(cam_1, cam_2)
            if stereo is None:
                stereo_status[key] = {"calibrated": False}
            else:
                translation = [
                    float(stereo.t[0, 0]),
                    float(stereo.t[1, 0]),
                    float(stereo.t[2, 0]),
                ]
                stereo_status[key] = {
                    "calibrated": True,
                    "translation": translation,
                }

    return {"cameras": cameras_status, "stereo": stereo_status}


@router.get("/api/calibration/{camera_id}", responses={404: RESPONSE_404})
async def get_camera_calibration(camera_id: str, state: StateDep) -> dict:
    if not state.camera_service.has_camera(camera_id):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    depth_intrinsics = state.camera_service.get_depth_intrinsics(camera_id)
    color_intrinsics = state.camera_service.get_color_intrinsics(camera_id)
    distortion = state.camera_service.get_distortion_coeffs(camera_id)
    pose = state.calibration_service.get_camera_pose(camera_id)

    if depth_intrinsics is None and pose is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not calibrated")

    camera_matrix = None
    if depth_intrinsics is not None:
        camera_matrix = [
            [depth_intrinsics.fx, 0.0, depth_intrinsics.cx],
            [0.0, depth_intrinsics.fy, depth_intrinsics.cy],
            [0.0, 0.0, 1.0],
        ]

    payload = {
        "camera_id": camera_id,
        "depth_resolution": [depth_intrinsics.width, depth_intrinsics.height] if depth_intrinsics else None,
        "color_resolution": [color_intrinsics.width, color_intrinsics.height] if color_intrinsics else None,
        "camera_matrix": camera_matrix,
        "distortion_coeffs": distortion,
        "depth_intrinsics": depth_intrinsics.as_dict() if depth_intrinsics else None,
        "color_intrinsics": color_intrinsics.as_dict() if color_intrinsics else None,
    }

    if pose is not None:
        payload["T_world_camera"] = pose.t_world_camera.tolist()
        payload["T_camera_world"] = pose.t_camera_world.tolist()

    return payload


@router.get("/api/calibration/stereo/{camera_id_1}/{camera_id_2}", responses={404: RESPONSE_404})
async def get_stereo_calibration(
    camera_id_1: str,
    camera_id_2: str,
    state: StateDep,
) -> dict:
    if not state.camera_service.has_camera(camera_id_1):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if not state.camera_service.has_camera(camera_id_2):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")

    stereo = state.calibration_service.get_stereo_transform(camera_id_1, camera_id_2)
    if stereo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Stereo calibration not found for {camera_id_1} and {camera_id_2}",
        )

    return stereo.as_api_dict()


@router.post("/api/calibration/capture", responses={400: RESPONSE_400, 404: RESPONSE_404})
async def capture_calibration_image(
    camera_id_1: CameraId1Query,
    camera_id_2: CameraId2Query,
    checkerboard_cols: CheckerboardColsQuery,
    checkerboard_rows: CheckerboardRowsQuery,
    state: StateDep,
) -> dict:
    _ = checkerboard_cols
    _ = checkerboard_rows

    if not state.camera_service.has_camera(camera_id_1):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if not state.camera_service.has_camera(camera_id_2):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")

    if not state.camera_service.is_running(camera_id_1):
        raise HTTPException(
            status_code=400,
            detail=f"Camera {camera_id_1} is not running. Please start the cameras first.",
        )
    if not state.camera_service.is_running(camera_id_2):
        raise HTTPException(
            status_code=400,
            detail=f"Camera {camera_id_2} is not running. Please start the cameras first.",
        )

    frames = state.camera_service.get_latest_frames()

    if camera_id_1 not in frames:
        raise HTTPException(
            status_code=400,
            detail=f"Frame not available for camera {camera_id_1}. Make sure cameras are streaming.",
        )
    if camera_id_2 not in frames:
        raise HTTPException(
            status_code=400,
            detail=f"Frame not available for camera {camera_id_2}. Make sure cameras are streaming.",
        )

    frame_1 = frames[camera_id_1]
    frame_2 = frames[camera_id_2]

    if frame_1.color_data is None:
        raise HTTPException(
            status_code=400,
            detail=f"Color data not available for camera {camera_id_1}. Make sure color stream is enabled.",
        )
    if frame_2.color_data is None:
        raise HTTPException(
            status_code=400,
            detail=f"Color data not available for camera {camera_id_2}. Make sure color stream is enabled.",
        )

    return state.capture_compat_service.capture(
        camera_id_1=camera_id_1,
        camera_id_2=camera_id_2,
        img_1_rgb=frame_1.color_data,
        img_2_rgb=frame_2.color_data,
        timestamp=frame_1.timestamp,
    )


@router.get("/api/calibration/capture/status")
async def get_calibration_capture_status(state: StateDep) -> dict:
    return state.capture_compat_service.status()


@router.post("/api/calibration/capture/clear")
async def clear_calibration_captures(state: StateDep) -> dict:
    return state.capture_compat_service.clear()


@router.get("/api/calibration/debug-image/{camera_id}", responses={400: RESPONSE_400, 404: RESPONSE_404, 500: RESPONSE_500})
async def get_debug_image(camera_id: str, state: StateDep) -> dict:
    if not state.camera_service.has_camera(camera_id):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    frames = state.camera_service.get_latest_frames()
    frame = frames.get(camera_id)
    if frame is None:
        raise HTTPException(status_code=400, detail=FRAME_NOT_AVAILABLE)
    if frame.color_data is None:
        raise HTTPException(status_code=400, detail=COLOR_DATA_NOT_AVAILABLE)

    image_bgr = cv2.cvtColor(frame.color_data, cv2.COLOR_RGB2BGR)
    success, encoded = cv2.imencode(".jpg", image_bgr)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode debug image")

    image_b64 = base64.b64encode(encoded).decode("utf-8")

    return {
        "camera_id": camera_id,
        "image": f"data:image/jpeg;base64,{image_b64}",
        "shape": list(image_bgr.shape),
    }


@router.get("/api/calibration/detect-checkerboard")
async def check_checkerboard(
    camera_id_1: CameraId1Query,
    camera_id_2: CameraId2Query,
    checkerboard_cols: CheckerboardColsQuery,
    checkerboard_rows: CheckerboardRowsQuery,
    state: StateDep,
) -> dict:
    pattern = f"{checkerboard_cols}x{checkerboard_rows}"

    if not state.camera_service.has_camera(camera_id_1):
        return {
            "camera_1": {"detected": False, "reason": f"Camera {camera_id_1} not found"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False,
            "pattern_tested": pattern,
        }
    if not state.camera_service.has_camera(camera_id_2):
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": f"Camera {camera_id_2} not found"},
            "both_detected": False,
            "pattern_tested": pattern,
        }

    if not state.camera_service.is_running(camera_id_1):
        return {
            "camera_1": {"detected": False, "reason": "Camera not running"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False,
            "pattern_tested": pattern,
        }
    if not state.camera_service.is_running(camera_id_2):
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": "Camera not running"},
            "both_detected": False,
            "pattern_tested": pattern,
        }

    frames = state.camera_service.get_latest_frames()
    frame_1 = frames.get(camera_id_1)
    frame_2 = frames.get(camera_id_2)

    if frame_1 is None:
        return {
            "camera_1": {"detected": False, "reason": FRAME_NOT_AVAILABLE},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False,
            "pattern_tested": pattern,
        }
    if frame_2 is None:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": FRAME_NOT_AVAILABLE},
            "both_detected": False,
            "pattern_tested": pattern,
        }

    if frame_1.color_data is None:
        return {
            "camera_1": {"detected": False, "reason": COLOR_DATA_NOT_AVAILABLE},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False,
            "pattern_tested": pattern,
        }
    if frame_2.color_data is None:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": COLOR_DATA_NOT_AVAILABLE},
            "both_detected": False,
            "pattern_tested": pattern,
        }

    return {
        "camera_1": {"detected": True, "reason": None},
        "camera_2": {"detected": True, "reason": None},
        "both_detected": True,
        "pattern_tested": pattern,
    }


@router.post("/api/calibration/perform", responses={404: RESPONSE_404, 500: RESPONSE_500})
async def perform_stereo_calibration(
    camera_id_1: CameraId1Query,
    camera_id_2: CameraId2Query,
    checkerboard_cols: CheckerboardColsQuery,
    checkerboard_rows: CheckerboardRowsQuery,
    square_size: SquareSizeQuery,
    state: StateDep,
) -> dict:
    _ = checkerboard_cols
    _ = checkerboard_rows
    _ = square_size

    if not state.camera_service.has_camera(camera_id_1):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if not state.camera_service.has_camera(camera_id_2):
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")

    try:
        state.calibration_service.reload()
        stereo = state.calibration_service.get_stereo_transform(camera_id_1, camera_id_2)
        if stereo is None:
            raise RuntimeError(
                f"Stereo calibration not available in external file for {camera_id_1} and {camera_id_2}"
            )

        translation = [float(stereo.t[0, 0]), float(stereo.t[1, 0]), float(stereo.t[2, 0])]
        return {
            "success": True,
            "reprojection_error": None,
            "translation": translation,
            "images_used": state.capture_compat_service.capture_count,
        }
    except Exception as exc:
        logger.exception("External calibration load failed")
        raise HTTPException(status_code=500, detail=f"Calibration failed: {exc}") from exc
