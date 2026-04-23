from __future__ import annotations

import logging

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


@app.on_event("startup")
def startup() -> None:
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


@app.on_event("shutdown")
def shutdown() -> None:
    manager = getattr(app.state, "camera_manager", None)
    if manager is not None:
        manager.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
