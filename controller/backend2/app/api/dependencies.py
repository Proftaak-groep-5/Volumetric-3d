from __future__ import annotations

from starlette.requests import HTTPConnection

from app.services.app_state import BackendAppState


def get_app_state(connection: HTTPConnection) -> BackendAppState:
    state = getattr(connection.app.state, "backend_state", None)
    if state is None:
        raise RuntimeError("Backend state is not initialized")
    return state
