from __future__ import annotations

import uvicorn

from app.application import app
from app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.application:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )
