from __future__ import annotations

import logging
import signal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings
from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager
from app.services.triangulation import TriangulationService
from app.services.volumetric_capture import VolumetricCaptureService

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

settings = get_settings()

app = FastAPI(title="Volumetric Controller API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount(
    settings.capture_output_url_prefix,
    StaticFiles(directory=str(settings.volumetric_capture_output_dir), check_dir=False),
    name="captures",
)

def _startup_app() -> None:
    if getattr(app.state, "_startup_complete", False):
        return

    calibration_store = CalibrationStore(settings.calibration_file)
    calibration_store.load()

    camera_manager = CameraStreamManager(
        color_width=settings.color_width,
        color_height=settings.color_height,
        depth_width=settings.depth_width,
        depth_height=settings.depth_height,
        fps=settings.fps,
        use_depth=settings.use_depth,
        max_cameras=settings.max_cameras,
        camera_tuning=settings.camera_tuning,
        network_camera=settings.network_camera,
    )

    try:
        camera_manager.start()
    except Exception as exc:
        LOGGER.exception("Failed to start camera manager: %s", exc)

    app.state.calibration_store = calibration_store
    app.state.camera_manager = camera_manager
    app.state.triangulation_service = TriangulationService(camera_manager, calibration_store)
    app.state.volumetric_capture_service = VolumetricCaptureService(
        camera_manager,
        calibration_store,
        output_dir=settings.volumetric_capture_output_dir,
    )
    app.state._startup_complete = True


def _shutdown_app() -> None:
    if not getattr(app.state, "_startup_complete", False):
        return

    manager = getattr(app.state, "camera_manager", None)
    if manager is not None:
        try:
            manager.stop()
        except Exception:
            LOGGER.exception("Failed to stop camera manager cleanly")
    app.state._startup_complete = False


@app.on_event("startup")
def startup() -> None:
    _startup_app()


@app.on_event("shutdown")
def shutdown() -> None:
    _shutdown_app()


if __name__ == "__main__":
    import uvicorn

    def _request_exit(signum: int, _frame: object) -> None:
        LOGGER.info("Received signal %s, shutting down controller backend", signum)
        _shutdown_app()
        raise KeyboardInterrupt

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _request_exit)
    signal.signal(signal.SIGTERM, _request_exit)
    try:
        uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
    except KeyboardInterrupt:
        LOGGER.info("Controller backend stopped")
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        _shutdown_app()
