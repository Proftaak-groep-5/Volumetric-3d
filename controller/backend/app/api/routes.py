from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_calibration_store,
    get_calibration_runner_service,
    get_camera_manager,
    get_recording_service,
    get_triangulation_service,
    get_volumetric_capture_service,
)
from app.schemas import (
    CalibrationRunStatusResponse,
    CameraInfo,
    CameraListResponse,
    ConfigureNetworkCamerasRequest,
    ConfigureNetworkCamerasResponse,
    CreateVolumetricCaptureRequest,
    CreateVolumetricCaptureResponse,
    CreateVolumetricPointRequest,
    CreateVolumetricPointResponse,
    PickRecordingOutputDirectoryResponse,
    RecordingStatusResponse,
    StartRecordingRequest,
    StartRecordingResponse,
    StartCalibrationResponse,
    StopRecordingResponse,
)
from app.services.calibration_runner import CalibrationRunnerService
from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager
from app.services.recording import RecordingService
from app.services.triangulation import TriangulationService
from app.services.volumetric_capture import VolumetricCaptureService

router = APIRouter(prefix="/api", tags=["controller"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/calibration/status")
def calibration_status(
    calibration_runner: Annotated[CalibrationRunnerService, Depends(get_calibration_runner_service)],
) -> CalibrationRunStatusResponse:
    snapshot = calibration_runner.status()
    return CalibrationRunStatusResponse(**snapshot.__dict__)


@router.post("/calibration/run", responses={409: {"description": "Calibration is already running"}})
def run_calibration(
    calibration_runner: Annotated[CalibrationRunnerService, Depends(get_calibration_runner_service)],
) -> StartCalibrationResponse:
    try:
        snapshot = calibration_runner.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return StartCalibrationResponse(
        accepted=True,
        status=CalibrationRunStatusResponse(**snapshot.__dict__),
    )


@router.get("/recording/status")
def recording_status(
    recording_service: Annotated[RecordingService, Depends(get_recording_service)],
    output_dir: str | None = Query(default=None),
) -> RecordingStatusResponse:
    snapshot = recording_service.status(selected_output_dir=output_dir)
    return RecordingStatusResponse(**snapshot.__dict__)


@router.get("/recording/pick-output-dir")
def pick_recording_output_dir(
    initial_dir: str | None = Query(default=None),
) -> PickRecordingOutputDirectoryResponse:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Native folder picker is unavailable in this backend environment.",
        ) from exc

    root: object | None = None
    selected: str = ""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        normalized_initial_dir = initial_dir.strip() if initial_dir is not None else ""
        initial_dir_for_dialog: str | None = None
        if normalized_initial_dir:
            requested_path = Path(normalized_initial_dir).expanduser()
            if requested_path.is_dir():
                initial_dir_for_dialog = str(requested_path)
            else:
                for parent in requested_path.parents:
                    if parent.is_dir():
                        initial_dir_for_dialog = str(parent)
                        break
        selected = filedialog.askdirectory(
            parent=root,
            title="Select recording output folder",
            initialdir=initial_dir_for_dialog,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open folder picker: {exc}") from exc
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

    if not selected:
        return PickRecordingOutputDirectoryResponse(selected_output_dir=None, cancelled=True)
    return PickRecordingOutputDirectoryResponse(selected_output_dir=selected, cancelled=False)


@router.post("/recording/start", responses={400: {"description": "Recording cannot be started"}, 409: {"description": "Recording is already running"}})
def start_recording(
    payload: StartRecordingRequest,
    recording_service: Annotated[RecordingService, Depends(get_recording_service)],
) -> StartRecordingResponse:
    try:
        snapshot = recording_service.start(
            output_dir=payload.output_dir,
            camera_ids=payload.camera_ids,
            depth_min_m=payload.depth_min_m,
            depth_max_m=payload.depth_max_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return StartRecordingResponse(
        accepted=True,
        status=RecordingStatusResponse(**snapshot.__dict__),
    )


@router.post("/recording/stop", responses={409: {"description": "Recording is not running"}})
def stop_recording(
    recording_service: Annotated[RecordingService, Depends(get_recording_service)],
) -> StopRecordingResponse:
    try:
        snapshot = recording_service.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return StopRecordingResponse(
        accepted=True,
        status=RecordingStatusResponse(**snapshot.__dict__),
    )


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


@router.post("/cameras/configure-network", responses={400: {"description": "Failed to configure one or more network cameras"}})
def configure_network_cameras(
    payload: ConfigureNetworkCamerasRequest,
    camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)],
) -> ConfigureNetworkCamerasResponse:
    results = camera_manager.configure_network_camera_streams(payload.camera_ids)
    return ConfigureNetworkCamerasResponse(results=results)


@router.get("/frame/{camera_id}.jpg", responses={404: {"description": "No frame available for camera"}})
def frame(camera_id: str, camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)]) -> Response:
    snapshot = camera_manager.get_snapshot(camera_id)
    if snapshot is None or snapshot.jpeg is None:
        raise HTTPException(status_code=404, detail=f"No frame available for camera {camera_id}")

    return Response(content=snapshot.jpeg, media_type="image/jpeg")


@router.get("/stream/{camera_id}.mjpg", responses={404: {"description": "Camera was not found"}})
async def stream(
    camera_id: str,
    request: Request,
    camera_manager: Annotated[CameraStreamManager, Depends(get_camera_manager)],
) -> StreamingResponse:
    if camera_id not in camera_manager.camera_ids():
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} was not found")

    boundary = "frame"
    frame_interval_s = 1.0 / max(1, camera_manager.target_fps())

    async def frame_generator():
        last_frame_index = -1
        while True:
            if await request.is_disconnected():
                break
            snapshot = camera_manager.get_snapshot(camera_id)
            if snapshot is not None and snapshot.jpeg is not None and snapshot.frame_index != last_frame_index:
                chunk = (
                    f"--{boundary}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(snapshot.jpeg)}\r\n\r\n"
                ).encode("utf-8")
                yield chunk + snapshot.jpeg + b"\r\n"
                last_frame_index = snapshot.frame_index
            await asyncio.sleep(frame_interval_s)

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

    if result.preview_image_path is None or result.preview_image_name is None:
        raise HTTPException(status_code=500, detail="Capture preview image was not generated")

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
