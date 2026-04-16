from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_app_state
from app.services.app_state import BackendAppState


logger = logging.getLogger(__name__)
router = APIRouter()
StateDep = Annotated[BackendAppState, Depends(get_app_state)]


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, state: StateDep) -> None:
    await state.websocket_hub.connect(websocket)

    try:
        await websocket.send_json(
            {
                "type": "status",
                "data": {
                    "cameras": {
                        "count": state.camera_service.camera_count(),
                        "active": state.camera_service.camera_count() > 0,
                    },
                    "recording": state.recording_service.status(),
                    "websocket_clients": state.websocket_hub.client_count,
                },
            }
        )

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        state.websocket_hub.disconnect(websocket)
