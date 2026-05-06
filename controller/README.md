# Volumetric Controller

This controller includes:

- Python FastAPI backend for live Femto Bolt preview and volumetric point triangulation.
- Next.js frontend dashboard for viewing all camera streams and creating a 3D point from clicked pixels.

## Architecture

- Backend: `controller/backend`
  - Discover + start connected Femto Bolt cameras via existing `calibration.camera.femto_bolt`.
  - Stream MJPEG preview for each camera.
  - Load calibration from `calib_out/final_calibration.json`.
  - Triangulate world-space point from multi-camera 2D observations.

- Frontend: `controller/frontend`
  - Poll camera list.
  - Show live preview tiles for each connected camera.
  - Click on each stream to pick corresponding pixel coordinates.
  - Create volumetric point and display world/unity coordinates.

## Backend Run

From repository root:

```powershell
cd controller/backend
pip install -r requirements.txt
python -m app.main
```

Backend defaults:

- Host: `0.0.0.0`
- Port: `8000`
- Calibration file: `calib_out/final_calibration.json`

Optional env vars:

- `CALIBRATION_FILE`
- `CORS_ALLOWED_ORIGINS` (comma separated)
- `CAMERA_COLOR_WIDTH`
- `CAMERA_COLOR_HEIGHT`
- `CAMERA_FPS`
- `MAX_CAMERAS`
- `CAMERA_USE_DEPTH`
- `CAMERA_COLOR_AUTO_EXPOSURE`
- `CAMERA_COLOR_EXPOSURE`
- `CAMERA_COLOR_GAIN`
- `CAMERA_COLOR_AUTO_WHITE_BALANCE`
- `CAMERA_COLOR_WHITE_BALANCE`
- `CAMERA_COLOR_BRIGHTNESS`
- `VOLUMETRIC_CAPTURE_OUTPUT_DIR`
- `CAPTURE_OUTPUT_URL_PREFIX`

## Frontend Run

From repository root:

```powershell
cd controller/frontend
npm install
copy .env.local.example .env.local
npm run dev
```

Open: `http://localhost:3000`

## API Endpoints

- `GET /api/health`
- `GET /api/cameras`
- `GET /api/frame/{camera_id}.jpg`
- `GET /api/stream/{camera_id}.mjpg`
- `POST /api/volumetric-point`
- `POST /api/volumetric-capture`

Request body for point creation:

```json
{
  "observations": [
    {"camera_id": "cam0", "u": 640.0, "v": 360.0},
    {"camera_id": "cam1", "u": 612.4, "v": 355.9}
  ]
}
```

Request body for one-shot stitched point cloud capture:

```json
{
  "camera_ids": ["cam0", "cam1", "cam2"],
  "pixel_step": 4,
  "depth_min_m": 0.25,
  "depth_max_m": 4.0
}
```

The capture endpoint saves:

- A stitched world-space point cloud as `.ply` in `calib_out/captures`.
- A top-down quick preview image (`.png`) in the same folder.
- Browser-accessible URLs are returned as `capture_file_url` and `preview_image_url`.
