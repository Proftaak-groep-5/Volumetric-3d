# Backend2 Architecture Overview

`controller/backend2` is a full rewrite that preserves the frontend API contract while replacing the backend internals with explicit service boundaries.

## Layers

- `app/application.py`: FastAPI app factory, middleware, router registration, deterministic startup/shutdown lifecycle.
- `app/api/`: Thin HTTP/WebSocket layer that translates requests into service calls.
- `app/services/`: Runtime business logic and orchestration.
- `app/domain/`: Typed domain data models and calibration schema validation.
- `app/integrations/`: SDK integration boundaries (Orbbec runtime loading).

## Runtime Design

- Camera I/O (`CameraService`):
  - Per-camera worker threads capture frames continuously.
  - Latest frame cache is lock-protected and read by websocket/recording pipelines.
  - Intrinsics are extracted from the device at runtime with fallbacks.

- External calibration (`ExternalCalibrationService`):
  - Runtime reads `calib_out/final_calibration.json`.
  - Camera world poses are treated as authoritative.
  - Pairwise stereo transforms are computed from world transforms on demand.

- Frame streaming (`FrameBroadcastService` + `WebSocketHub`):
  - Async broadcast loop controls wire-level frame cadence.
  - Frames are encoded once per frame object and reused during the broadcast tick.

- Recording (`RecordingService`):
  - Recording ingestion is queue-based with a dedicated writer thread.
  - Recording stop finalizes metadata and persists camera frame archives (`.npz`).
  - A sample point cloud export is generated via vectorized reconstruction logic.

- Legacy calibration capture compatibility (`CalibrationCaptureCompatService`):
  - Keeps old endpoint contracts operational for frontend UI flow.
  - No checkerboard calibration math is executed in runtime.

## Concurrency Model

- Camera capture: native threads (I/O-bound device capture).
- Recording write path: dedicated writer thread (disk-bound).
- API + websocket + broadcast orchestration: asyncio event loop.

## Failure Handling

- SDK unavailable -> backend still starts with diagnostics showing unavailable camera runtime.
- Missing/invalid external calibration -> backend starts, readiness endpoint reports not ready.
- Camera startup failure per-device does not kill process; it is logged and isolated.
