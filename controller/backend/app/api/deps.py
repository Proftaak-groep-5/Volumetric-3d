from __future__ import annotations

from fastapi import HTTPException, Request

from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager
from app.services.calibration_runner import CalibrationRunnerService
from app.services.triangulation import TriangulationService
from app.services.volumetric_capture import VolumetricCaptureService


def get_camera_manager(request: Request) -> CameraStreamManager:
    manager = getattr(request.app.state, "camera_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Camera manager is not available")
    return manager


def get_calibration_store(request: Request) -> CalibrationStore:
    store = getattr(request.app.state, "calibration_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Calibration is not available")
    return store


def get_triangulation_service(request: Request) -> TriangulationService:
    service = getattr(request.app.state, "triangulation_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Triangulation service is not available")
    return service


def get_volumetric_capture_service(request: Request) -> VolumetricCaptureService:
    service = getattr(request.app.state, "volumetric_capture_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Volumetric capture service is not available")
    return service


def get_calibration_runner_service(request: Request) -> CalibrationRunnerService:
    service = getattr(request.app.state, "calibration_runner_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Calibration runner service is not available")
    return service
