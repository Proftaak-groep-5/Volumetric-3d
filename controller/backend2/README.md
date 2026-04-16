# Multi-Camera 3D Backend v2 (`backend2`)

Production-oriented backend rewrite for Orbbec Femto Bolt streaming/recording, designed to preserve frontend API compatibility while modernizing architecture and runtime behavior.

## Key Goals Achieved

- Preserves legacy frontend-facing API routes and websocket payload shape.
- Replaces monolithic global-state backend with layered architecture.
- Removes runtime checkerboard calibration solving.
- Consumes external calibration output from `calib_out/final_calibration.json`.
- Supports up to 6 Orbbec Femto Bolt cameras.
- Keeps FastAPI/Uvicorn stack.

## Project Structure

```
backend2/
├── app/
│   ├── application.py            # App factory + lifespan
│   ├── config.py                 # Typed settings
│   ├── api/
│   │   ├── dependencies.py
│   │   └── routers/
│   │       ├── system.py
│   │       ├── recording.py
│   │       ├── calibration.py
│   │       ├── websocket.py
│   │       └── diagnostics.py
│   ├── domain/
│   │   ├── models.py
│   │   └── calibration_schema.py
│   ├── integrations/
│   │   └── orbbec_sdk.py
│   └── services/
│       ├── app_state.py
│       ├── camera_service.py
│       ├── calibration_service.py
│       ├── recording_service.py
│       ├── reconstruction_service.py
│       ├── capture_compat_service.py
│       ├── websocket_hub.py
│       └── broadcast_service.py
├── ARCHITECTURE.md
├── API_COMPATIBILITY.md
├── MIGRATION.md
├── requirements.txt
└── main.py
```

## Setup

1. `cd controller/backend2`
2. `python -m venv venv`
3. Activate venv:
   - Windows: `venv\Scripts\activate`
   - Linux/macOS: `source venv/bin/activate`
4. `pip install -r requirements.txt`
5. Optional: copy `.env.example` to `.env` and adjust settings

## Run

- `python main.py`
- or `uvicorn app.application:app --host 0.0.0.0 --port 8000 --reload`

## Calibration Integration

- Runtime calibration source: `../../calib_out/final_calibration.json` (configurable with `EXTERNAL_CALIBRATION_PATH`).
- This file is treated as authoritative for camera world poses and stereo relationships.
- No checkerboard calibration optimization is performed inside backend2 runtime.

## Diagnostics

- `GET /health/live`
- `GET /health/ready`
- `GET /api/diagnostics`

Use these endpoints to validate hardware/runtime/calibration readiness.

## Compatibility and Migration

- Endpoint map: see `API_COMPATIBILITY.md`.
- Architectural details: see `ARCHITECTURE.md`.
- Differences from old backend: see `MIGRATION.md`.
