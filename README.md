# Volumetric-3d

End-to-end volumetric capture stack for Orbbec Femto Bolt cameras.

This repo combines:

- Calibration tools to compute camera extrinsics.
- A Windows NUC C++ service for Femto Bolt capture and streaming.
- A controller backend + frontend for live preview and triangulation.
- Blender and Unity projects for validating the output.

## What lives where

- calibration/ - Python calibration pipeline for 1-6 Femto Bolt cameras.
- nuc/ - Windows x64 C++ service (FemtoBoltNuc) for capture and streaming.
- controller/ - FastAPI backend + Next.js frontend dashboard.
- calib_out/ - Default output for calibration and captures.
- blender/ - Blender project for output validation.
- unity/ - Unity project for output validation.

## Typical workflow

1) Build and run the NUC service (FemtoBoltNuc).
2) Start the controller backend and frontend.
3) Validate outputs in Blender or Unity.

## Quick start (commands people use most)

### Calibration

```powershell
python -m calibration.main --config calibration/calibration_config.json
```

### Controller backend

From repo root:

```powershell
cd controller/backend
python -m app.main
```

### Controller frontend

From repo root:

```powershell
cd controller/frontend
npm run dev
```

### NUC (FemtoBoltNuc) build and run

Configure (generate the CMake files):

```powershell
cmake -S nuc -B nuc/build-vs -G "Visual Studio 17 2022" -A x64 `
  -DNUC_REQUIRE_ORBBEC=ON `
  -DNUC_REQUIRE_GSTREAMER=ON `
  -DNUC_FETCH_DEPS=ON `
  -DOrbbecSDK_DIR="C:\Program Files\OrbbecSDK 2.7.6\lib" `
  -DGSTREAMER_ROOT_DIR="C:\gstreamer\1.0\msvc_x86_64"
```

Build:

```powershell
cmake --build nuc/build-vs --config Release --target FemtoBoltNuc
```

Run:

```powershell
nuc\build-vs\Release\FemtoBoltNuc.exe --config nuc\config\example.json
```

## Calibration (Python)

- Entry point: calibration/main.py
- Output: calib_out/final_calibration.json
- Supports mock mode for testing without hardware.

See calibration/README.md for full CLI flags and config format.

## Controller (backend + frontend)

Backend:

- FastAPI service for camera discovery, preview streams, and triangulation.
- Reads calib_out/final_calibration.json by default.
- Entry: controller/backend/app/main.py (run via python -m app.main).

Frontend:

- Next.js dashboard for live streams and point picking.
- Entry: controller/frontend (run via npm run dev).

See controller/README.md for API endpoints and environment variables.

## NUC service (C++)

- Windows x64 service for Femto Bolt capture and streaming.
- REST and WebSocket endpoints for preview, depth, and control.
- Uses Orbbec SDK v2 and GStreamer.

See nuc/README.md for build and runtime requirements.

## Blender and Unity validation

- blender/ contains a Blender project used to validate captures and calibration output.
- unity/ contains a Unity project used to validate captures and calibration output.

These projects are intended for quick visual verification of alignment and scale before using the data in downstream pipelines.

## Setup script

Run the setup script to check for Python 3.13, Node.js 20+, CMake, Orbbec SDK, and GStreamer, then install Python and Node dependencies:

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

macOS:

```bash
./scripts/setup-macos.sh
```

Linux:

```bash
./scripts/setup-linux.sh
```

The script is safe to re-run. It will create .venv at the repo root if it does not exist and installs both calibration and controller backend Python requirements.
