from __future__ import annotations

import logging

from app.config import Settings
from app.integrations.orbbec_sdk import load_orbbec_runtime
from app.services.broadcast_service import FrameBroadcastService
from app.services.calibration_service import ExternalCalibrationService
from app.services.camera_service import CameraService
from app.services.capture_compat_service import CalibrationCaptureCompatService
from app.services.recording_service import RecordingService
from app.services.websocket_hub import WebSocketHub


logger = logging.getLogger(__name__)


class BackendAppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.calibration_service = ExternalCalibrationService(settings.external_calibration_path)

        runtime = load_orbbec_runtime()
        self.camera_service = CameraService(
            runtime=runtime,
            depth_res=(settings.depth_width, settings.depth_height),
            color_res=(settings.color_width, settings.color_height),
            fps=settings.fps,
            max_cameras=settings.max_cameras,
        )

        self.recording_service = RecordingService(
            recordings_path=settings.recordings_path,
            fps=settings.fps,
            pointcloud_stride=settings.pointcloud_sample_stride,
            pointcloud_max_depth_m=settings.pointcloud_max_depth_m,
        )

        self.websocket_hub = WebSocketHub()
        self.capture_compat_service = CalibrationCaptureCompatService(settings.calibration_capture_path)

        self.broadcast_service = FrameBroadcastService(
            camera_service=self.camera_service,
            recording_service=self.recording_service,
            websocket_hub=self.websocket_hub,
            interval_sec=settings.ws_broadcast_interval_sec,
            color_quality=settings.ws_jpeg_quality_color,
            depth_quality=settings.ws_jpeg_quality_depth,
        )

    def startup(self) -> None:
        logger.info("Starting backend2 services")
        self.calibration_service.load()
        camera_count = self.camera_service.startup()
        logger.info("Camera startup completed with %d active camera(s)", camera_count)
        self.broadcast_service.start()

    async def shutdown(self) -> None:
        logger.info("Stopping backend2 services")

        if self.recording_service.is_recording:
            try:
                self.recording_service.stop(self.camera_service.get_intrinsics_map())
            except Exception as exc:
                logger.warning("Failed to finalize recording on shutdown: %s", exc)

        await self.broadcast_service.stop()
        self.camera_service.shutdown()
        logger.info("backend2 services stopped")
