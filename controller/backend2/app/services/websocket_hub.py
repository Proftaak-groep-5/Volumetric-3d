from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for websocket in self._clients:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("WebSocket send failed: %s", exc)
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)
