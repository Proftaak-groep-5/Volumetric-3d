from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_app_state
from app.services.app_state import BackendAppState


router = APIRouter()
StateDep = Annotated[BackendAppState, Depends(get_app_state)]


@router.get("/")
async def root() -> dict:
    return {
        "message": "Multi-Camera 3D Recording API",
        "version": "1.0.0",
        "status": "online",
    }


@router.get("/api/status")
async def get_status(state: StateDep) -> dict:
    camera_count = state.camera_service.camera_count()
    return {
        "cameras": {
            "count": camera_count,
            "active": camera_count > 0,
        },
        "recording": state.recording_service.status(),
        "websocket_clients": state.websocket_hub.client_count,
    }


@router.get("/api/cameras")
async def get_cameras(state: StateDep) -> dict:
    cameras = []
    for camera in state.camera_service.list_cameras():
        cameras.append(
            {
                "id": camera.camera_id,
                "running": camera.running,
                "depth_resolution": camera.depth_resolution,
                "color_resolution": camera.color_resolution,
                "fps": camera.fps,
            }
        )
    return {"cameras": cameras}


@router.get("/api/recordings")
async def list_recordings(state: StateDep) -> dict:
    recordings: list[dict] = []
    recordings_path: Path = state.recording_service.recordings_path

    if recordings_path.exists():
        for session_dir in sorted(recordings_path.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            meta_file = session_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                with meta_file.open("r", encoding="utf-8") as fh:
                    recordings.append(json.load(fh))
            except Exception:
                continue

    return {"recordings": recordings}
