from __future__ import annotations

from fastapi import Request

from app.services.app_state import BackendAppState


def get_app_state(request: Request) -> BackendAppState:
    state = getattr(request.app.state, "backend_state", None)
    if state is None:
        raise RuntimeError("Backend state is not initialized")
    return state
