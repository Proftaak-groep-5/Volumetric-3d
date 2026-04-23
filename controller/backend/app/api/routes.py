from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_calibration_store,
    get_camera_manager,
    get_triangulation_service,
    get_volumetric_capture_service,
)
from app.schemas import (
    CameraInfo,
    CameraListResponse,
    CreateVolumetricCaptureRequest,
    CreateVolumetricCaptureResponse,
    CreateVolumetricPointRequest,
    CreateVolumetricPointResponse,
)
from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager
from app.services.triangulation import TriangulationService
from app.services.volumetric_capture import VolumetricCaptureService

router = APIRouter(prefix="/api", tags=["controller"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/cameras")
def list_cameras(camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)]) -> CameraListResponse:
    cameras = []
    for item in camera_manager.camera_details():
        camera_id = str(item["camera_id"])
        cameras.append(
            CameraInfo(
                camera_id=camera_id,
                serial_number=str(item.get("serial_number") or ""),
                device_name=str(item.get("device_name") or ""),
                connection_type=str(item.get("connection_type") or ""),
                width=int(item["width"]),
                height=int(item["height"]),
                fps=int(item["fps"]),
                connected=bool(item["connected"]),
                stream_url=f"/api/stream/{camera_id}.mjpg",
                snapshot_url=f"/api/frame/{camera_id}.jpg",
            )
        )

    return CameraListResponse(cameras=cameras)


@router.get("/frame/{camera_id}.jpg", responses={404: {"description": "No frame available for camera"}})
def frame(camera_id: str, camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)]) -> Response:
    snapshot = camera_manager.get_snapshot(camera_id)
    if snapshot is None or snapshot.jpeg is None:
        raise HTTPException(status_code=404, detail=f"No frame available for camera {camera_id}")

    return Response(content=snapshot.jpeg, media_type="image/jpeg")


@router.get("/stream/{camera_id}.mjpg", responses={404: {"description": "Camera was not found"}})
async def stream(camera_id: str, camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)]) -> StreamingResponse:
    if camera_id not in camera_manager.camera_ids():
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} was not found")

    boundary = "frame"

    async def frame_generator():
        while True:
            snapshot = camera_manager.get_snapshot(camera_id)
            if snapshot is not None and snapshot.jpeg is not None:
                chunk = (
                    f"--{boundary}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(snapshot.jpeg)}\r\n\r\n"
                ).encode("utf-8")
                yield chunk + snapshot.jpeg + b"\r\n"
            await asyncio.sleep(1.0 / 20.0)

    return StreamingResponse(
        frame_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
    )


@router.post("/volumetric-point", responses={400: {"description": "Invalid observations payload"}})
def create_volumetric_point(
    payload: CreateVolumetricPointRequest,
    triangulation: Annotated[TriangulationService, Depends(get_triangulation_service)],
    calibration_store: Annotated[CalibrationStore, Depends(get_calibration_store)],
) -> CreateVolumetricPointResponse:
    try:
        point_world, reprojection_error = triangulation.create_point(payload.observations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    point_unity = triangulation.to_unity(point_world)

    return CreateVolumetricPointResponse(
        point_world_xyz=[float(value) for value in point_world.tolist()],
        point_unity_xyz=[float(value) for value in point_unity.tolist()],
        cameras_used=sorted(reprojection_error.keys()),
        reprojection_error_px=reprojection_error,
        debug={
            "calibration_file": str(calibration_store.calibration_file),
        },
    )


@router.post("/volumetric-capture", responses={400: {"description": "Failed to generate stitched point cloud"}})
def create_volumetric_capture(
    payload: CreateVolumetricCaptureRequest,
    capture_service: Annotated[VolumetricCaptureService, Depends(get_volumetric_capture_service)],
    calibration_store: Annotated[CalibrationStore, Depends(get_calibration_store)],
) -> CreateVolumetricCaptureResponse:
    try:
        result = capture_service.capture_once(
            camera_ids=payload.camera_ids,
            pixel_step=payload.pixel_step,
            depth_min_m=payload.depth_min_m,
            depth_max_m=payload.depth_max_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CreateVolumetricCaptureResponse(
        capture_file_path=str(result.file_path),
        preview_image_path=str(result.preview_image_path),
        capture_file_url=f"/captures/{result.file_name}",
        preview_image_url=f"/captures/{result.preview_image_name}",
        points_total=result.points_total,
        points_per_camera=result.points_per_camera,
        cameras_used=result.cameras_used,
        debug={
            "calibration_file": str(calibration_store.calibration_file),
            "skipped_cameras": result.skipped_cameras,
        },
    )
