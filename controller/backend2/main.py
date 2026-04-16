from __future__ import annotations

import os

import uvicorn

from app.application import app
from app.config import settings


if __name__ == "__main__":
    reload_enabled = os.getenv("BACKEND2_RELOAD", "0").lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "app.application:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=reload_enabled,
    )
