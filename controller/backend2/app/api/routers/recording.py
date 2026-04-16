from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_app_state
from app.services.app_state import BackendAppState


logger = logging.getLogger(__name__)
router = APIRouter()
StateDep = Annotated[BackendAppState, Depends(get_app_state)]

RESPONSE_400 = {"description": "Bad Request"}
RESPONSE_500 = {"description": "Internal Server Error"}


@router.post("/api/record/start", responses={400: RESPONSE_400, 500: RESPONSE_500})
async def start_recording(state: StateDep) -> dict:
    if state.camera_service.camera_count() == 0:
        raise HTTPException(status_code=400, detail="No cameras available")

    if state.recording_service.is_recording:
        raise HTTPException(status_code=400, detail="Already recording")

    try:
        camera_ids = [camera.camera_id for camera in state.camera_service.list_cameras()]
        session_id = state.recording_service.start(camera_ids)
        return {
            "status": "recording",
            "session_id": session_id,
            "cameras": camera_ids,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error starting recording")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/record/stop", responses={400: RESPONSE_400, 500: RESPONSE_500})
async def stop_recording(state: StateDep) -> dict:
    if not state.recording_service.is_recording:
        raise HTTPException(status_code=400, detail="Not currently recording")

    try:
        metadata = state.recording_service.stop(state.camera_service.get_intrinsics_map())
        return {"status": "stopped", "metadata": metadata}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error stopping recording")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
