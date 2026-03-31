# Multi-Camera 3D Recording Backend

Backend service for streaming and recording depth + color data from Orbbec Femto Bolt cameras.

## Setup

### Prerequisites

- Python 3.8+
- Orbbec SDK installed
- pyorbbecsdk Python package
- Orbbec Femto Bolt camera(s) connected

### Installation

```bash
cd backend
pip install -r requirements.txt
```

### Configuration

Create or edit `.env` file with your settings:

```env
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
RECORDINGS_PATH=./recordings
DEPTH_WIDTH=1024
DEPTH_HEIGHT=1024
COLOR_WIDTH=1920
COLOR_HEIGHT=1080
FPS=30
```

## Running

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Camera Calibration

For accurate 3D reconstruction with multiple cameras, you need to calibrate your cameras. The system automatically extracts camera intrinsics when cameras start, but you need to perform stereo calibration to align the two cameras.

### Generate Checkerboard Pattern

First, generate a printable checkerboard pattern:

```bash
python generate_checkerboard.py --cols 9 --rows 6 --square-size 25 --output checkerboard_9x6.png
```

**Options:**
- `--cols`: Number of inner corners (columns), default: 9
- `--rows`: Number of inner corners (rows), default: 6
- `--square-size`: Square size in millimeters, default: 25.0
- `--margin`: Margin in millimeters, default: 20.0
- `--dpi`: Print resolution (300 is standard), default: 300
- `--output`: Output filename, default: checkerboard.png
- `--pdf`: Also generate PDF version (requires Pillow)

**Printing Instructions:**
1. Print the generated image at 300 DPI (or "Actual Size" in printer settings)
2. Measure a square to verify it's exactly the specified size (e.g., 25mm)
3. Mount on a flat, rigid surface (cardboard, foam board, or acrylic)
4. Ensure the surface is flat and not warped

A pre-generated `checkerboard_9x6.png` (25mm squares) is included in the backend directory.

### Quick Calibration

1. **Capture calibration images:**
   ```bash
   python calibrate_stereo.py --capture
   ```
   - Place the printed checkerboard in view of both cameras
   - Press SPACE to capture synchronized image pairs
   - Capture at least 10-20 images with the checkerboard in different positions and orientations
   - Press ESC when done

2. **Perform calibration:**
   ```bash
   python calibrate_stereo.py --calibrate
   ```
   Or combine both steps:
   ```bash
   python calibrate_stereo.py --capture --calibrate
   ```

### Calibration Parameters

- `--checkerboard-cols`: Number of inner corners (columns), default: 9
- `--checkerboard-rows`: Number of inner corners (rows), default: 6
- `--square-size`: Size of checkerboard square in meters, default: 0.025 (25mm)
- `--num-images`: Number of images to capture, default: 20
- `--images-dir`: Directory to save/load images, default: ./calibration_images

### Calibration Files

Calibration data is saved in `./calibrations/`:
- `cam0_calibration.json` - Intrinsic parameters for camera 0
- `cam1_calibration.json` - Intrinsic parameters for camera 1
- `stereo_cam0_cam1.json` - Stereo calibration (rotation, translation)

The system automatically loads these calibrations on startup.

## API Endpoints

### REST API

- `GET /` - API info
- `GET /api/status` - System status
- `GET /api/cameras` - List connected cameras
- `POST /api/record/start` - Start recording
- `POST /api/record/stop` - Stop recording
- `GET /api/recordings` - List all recordings
- `GET /api/calibration/status` - Get calibration status for all cameras
- `GET /api/calibration/{camera_id}` - Get calibration parameters for a camera
- `GET /api/calibration/stereo/{camera_id_1}/{camera_id_2}` - Get stereo calibration between two cameras

### WebSocket

- `WS /ws` - Live frame streaming

WebSocket message format:
```json
{
  "type": "frames",
  "cameras": {
    "cam0": {
      "camera_id": "cam0",
      "timestamp": 1730900000.123,
      "color_b64": "...",
      "depth_b64": "...",
      "color_shape": [1080, 1920, 3],
      "depth_shape": [1024, 1024]
    }
  }
}
```

## Recording Format

Each recording session creates a directory: `recordings/{timestamp}/`

Contents:
- `meta.json` - Session metadata
- `cam0_frames.npz` - Compressed numpy arrays with color and depth frames
- `cam0_sample.ply` - Sample point cloud from first frame

## Development

### Project Structure

```
backend/
├── main.py                  # FastAPI application
├── camera_manager.py        # Orbbec camera interface
├── recorder.py              # Recording management
├── calibration.py           # Camera calibration module
├── calibrate_stereo.py      # Stereo calibration tool
├── generate_checkerboard.py # Checkerboard pattern generator
├── checkerboard_9x6.png     # Pre-generated checkerboard (25mm squares)
├── config.py                # Configuration
├── requirements.txt          # Dependencies
├── calibrations/             # Saved calibration files
└── recordings/               # Saved recordings
```

