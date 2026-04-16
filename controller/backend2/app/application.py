from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import calibration, diagnostics, recording, system, websocket
from app.config import settings
from app.services.app_state import BackendAppState


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_state = BackendAppState(settings)
        app.state.backend_state = app_state

        app_state.startup()
        try:
            yield
        finally:
            await app_state.shutdown()

    app = FastAPI(
        title="Multi-Camera 3D Recording API",
        description="Real-time depth and color streaming from Orbbec Femto Bolt cameras",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(recording.router)
    app.include_router(calibration.router)
    app.include_router(websocket.router)
    app.include_router(diagnostics.router)

    return app


app = create_app()
