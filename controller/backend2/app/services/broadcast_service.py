from __future__ import annotations

import asyncio
import logging

from app.services.camera_service import CameraService
from app.services.recording_service import RecordingService
from app.services.websocket_hub import WebSocketHub


logger = logging.getLogger(__name__)


class FrameBroadcastService:
    def __init__(
        self,
        camera_service: CameraService,
        recording_service: RecordingService,
        websocket_hub: WebSocketHub,
        interval_sec: float,
        color_quality: int,
        depth_quality: int,
    ) -> None:
        self._camera_service = camera_service
        self._recording_service = recording_service
        self._websocket_hub = websocket_hub
        self._interval_sec = interval_sec
        self._color_quality = color_quality
        self._depth_quality = depth_quality

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="frame-broadcast-loop")

    async def stop(self) -> None:
        if self._task is None:
            return

        self._stop_event.set()
        task = self._task
        self._task = None

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._websocket_hub.client_count > 0 or self._recording_service.is_recording:
                    frames = self._camera_service.get_latest_frames()
                    if frames:
                        payload = {
                            "type": "frames",
                            "cameras": {
                                camera_id: frame.to_ws_payload(self._color_quality, self._depth_quality)
                                for camera_id, frame in frames.items()
                            },
                        }

                        if self._websocket_hub.client_count > 0:
                            await self._websocket_hub.broadcast_json(payload)

                        if self._recording_service.is_recording:
                            for frame in frames.values():
                                self._recording_service.record_frame(frame)

                await asyncio.sleep(self._interval_sec)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Broadcast loop error: %s", exc)
                await asyncio.sleep(1.0)
