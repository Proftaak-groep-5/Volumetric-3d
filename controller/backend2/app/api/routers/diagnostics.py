from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_app_state
from app.services.app_state import BackendAppState


router = APIRouter()
StateDep = Annotated[BackendAppState, Depends(get_app_state)]


@router.get("/health/live")
async def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(state: StateDep) -> JSONResponse:
    camera_diag = state.camera_service.diagnostics()
    calib_state = state.calibration_service.get_state()

    ready = camera_diag["camera_count"] > 0 and calib_state.loaded

    payload = {
        "ready": ready,
        "camera": camera_diag,
        "external_calibration": {
            "loaded": calib_state.loaded,
            "source_path": calib_state.source_path,
            "camera_count": calib_state.camera_count,
            "last_error": calib_state.last_error,
            "last_loaded_timestamp_utc": calib_state.last_loaded_timestamp_utc,
            "file_mtime_unix": calib_state.file_mtime_unix,
        },
    }

    return JSONResponse(status_code=200 if ready else 503, content=payload)


@router.get("/api/diagnostics")
async def diagnostics(state: StateDep) -> dict:
    return {
        "camera": state.camera_service.diagnostics(),
        "recording": state.recording_service.status(),
        "calibration": state.calibration_service.get_state().__dict__,
        "websocket_clients": state.websocket_hub.client_count,
    }
