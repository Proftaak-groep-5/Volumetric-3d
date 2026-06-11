# Volumetric Multi-Camera Calibration Tool

Production-oriented Python calibration pipeline for **1..6 Orbbec Femto Bolt cameras**, using a rigid **ArUco cube** as the shared geometric reference.

The tool computes one rigid 4x4 transform per camera in one shared world coordinate system (world origin at cube center by default), and exports both per-frame estimates and final averaged results to JSON.

## Features

- Modular architecture for integration into larger volumetric capture platforms.
- Real camera backend (`FemtoBoltCamera`) isolated behind a common camera interface.
- Mock backend (`MockCamera`) to run and test the full pipeline without hardware.
- ArUco marker detection + pose estimation using OpenCV.
- Explicit cube geometry model with per-face transforms derived mathematically.
- Multi-frame robust averaging and outlier rejection for stable extrinsics.
- Quality metrics and warning paths for unstable/failed camera calibration.
- Optional debug visualization (detected markers, marker axes, cube axes).

## Project Layout

```
calibration/
  main.py
  config.py
  camera/
    base.py
    femto_bolt.py
    mock_camera.py
  calibration/
    aruco_cube.py
    detector.py
    pose_estimation.py
    multi_camera_calibrator.py
  math3d/
    transforms.py
  io/
    export_json.py
    visualization.py
```

## Dependencies

Install in your Python environment:

```bash
pip install numpy opencv-contrib-python
```

Optional (real hardware):

- `pyorbbecsdk` (Orbbec Python SDK)

If `pyorbbecsdk` is unavailable, run in mock mode.

## Quick Start

### 0) Real hardware smoke test (1 camera)

```bash
python -m calibration.main --config calibration/calibration_config.json --single-camera-smoke-test --smoke-test-mode full --debug
```

Alternative direct tool entrypoint:

```bash
python -m calibration.tools.smoke_test --config calibration/calibration_config.json --mode full --debug
```

Smoke test modes:

- `frame`: camera open + frame acquisition + raw frame save
- `detect`: marker detection and marker overlay save
- `pose`: marker detection + pose estimation + axis overlay save
- `full`: full one-camera validation path (same success criteria as `pose`)

### 1) Run with mock cameras

```bash
python -m calibration.main --config calibration/calibration_config.json --mock --mock-camera-count 4
```

### 2) Run with real Femto Bolt cameras

```bash
python -m calibration.main --config calibration/calibration_config.json
```

### 3) Run with debug overlays

```bash
python -m calibration.main --config calibration/calibration_config.json --debug
```

Useful CLI flags:

- `--frame-count N`
- `--output-dir PATH`
- `--max-cameras N`
- `--show-debug-windows`
- `--mock`, `--mock-camera-count`, `--mock-seed`
- `--single-camera-smoke-test`
- `--smoke-test-mode full|frame|detect|pose`
- `--smoke-test-output-dir PATH`
- `--smoke-test-max-frame-retries N`

## Config Format

The tool reads JSON config (`--config`) with this base format:

```json
{
  "output": "calib_out",
  "dict": "DICT_4X4_50",
  "cube": {
    "marker_length": 0.078,
    "cube_length": 0.09
  },
  "face_ids": {
    "front": 3,
    "top": 4,
    "left": 5,
    "right": 0,
    "back": 1,
    "bottom": 2
  },
  "color_res": "3840x2160",
  "fps": 60
}
```

Optional advanced sections:

- `quality`: thresholds for reprojection, outlier rejection, stability checks.
- `debug`: image saving / live window behavior.
- `frame_count`, `warmup_frames`, `max_cameras`, `use_depth`, `camera_ids`.

## Coordinate Systems

The pipeline uses explicit frame notation:

- `marker`: OpenCV marker local frame.
- `cube`: rigid cube frame, origin at cube center.
- `camera`: camera optical frame from OpenCV pose estimation.
- `world`: shared world frame (default: identical to `cube`).

Transform naming convention:

- `T_dst_src` maps points from `src` to `dst`.
- Homogeneous form: `x_dst = T_dst_src * x_src`.

## Cube Face Transform Derivation

Let `h = cube_length / 2`.

Face centers in cube frame:

- front: `(0, 0, +h)`
- back: `(0, 0, -h)`
- right: `(+h, 0, 0)`
- left: `(-h, 0, 0)`
- top: `(0, +h, 0)`
- bottom: `(0, -h, 0)`

Outward normals (marker `+Z` axis):

- front: `+Z`
- back: `-Z`
- right: `+X`
- left: `-X`
- top: `+Y`
- bottom: `-Y`

For each face, the tool constructs fixed rigid transform `T_cube_marker(face)` from:

1. Translation = face center.
2. Rotation = marker axes mapped into cube axes so marker `+Z` matches face outward normal.

These transforms are computed analytically in `calibration/aruco_cube.py`; they are not hand-measured.

## Pose Computation and Composition

From OpenCV ArUco pose estimation, each detection yields `T_camera_marker`.

From cube model, the corresponding face gives `T_cube_marker`.

Therefore:

```text
T_camera_cube = T_camera_marker * inverse(T_cube_marker)
```

If world origin is cube center (`world == cube`):

```text
T_camera_world = T_camera_cube
T_world_camera = inverse(T_camera_world)
```

The exported camera extrinsic matrix is `T_world_camera`.

## Multi-Camera Calibration Strategy

For each camera:

1. Acquire many frames.
2. Detect visible markers (possibly different subsets per camera).
3. Convert marker poses to per-marker cube pose hypotheses (`T_camera_cube`).
4. Reject per-frame marker outliers using translation/rotation consistency.
5. Fuse remaining hypotheses into one per-frame cube pose estimate.
6. Across frames, reject outlier frame poses.
7. Average inlier poses (rotation-aware averaging + translation averaging).
8. Compute final `T_world_camera` and quality metrics.

This allows cameras to calibrate even when they do not all see the same face at the same time.

## Output JSON

Written to config/output directory:

- `final_calibration.json`
  - one entry per camera
  - success/failure
  - final transform matrices (`T_world_camera`, `T_camera_world`)
  - rotation + translation breakdown
  - markers used
  - quality metrics
  - timestamp

- `per_frame_estimates.json`
  - per-camera, per-frame records
  - frame-level success/failure
  - marker IDs used
  - frame transforms
  - spread/error metrics
  - reject reasons for invalid frames

## Tuning and Customization

Change marker IDs, marker size, and cube size in config:

- `face_ids`: remap marker IDs to faces.
- `cube.marker_length`: physical marker side in meters.
- `cube.cube_length`: physical cube edge length in meters.

Use `quality` thresholds to adjust strictness for noisy setups.

## Limitations

- Current world origin option implemented: `cube_center`.
- Accuracy still depends on camera intrinsics quality and marker visibility.
- Real-time synchronization across cameras is not enforced; frame-level fusion is robust but not hardware-time-locked.

## Extension Points

- Add temporal filtering (e.g., SE(3) smoothing) before final averaging.
- Incorporate depth-assisted marker refinement.
- Add global bundle-adjustment over all cameras and all observations.
- Persist intrinsics/extrinsics into a shared calibration database service.

## How this calibration fits into a volumetric capture / FBX pipeline

This calibration stage produces **extrinsic transforms per camera** in one shared world coordinate system.

Those transforms are used to bring each camera's depth/color data into common 3D space. That alignment is a prerequisite for:

- multi-view point cloud fusion
- surface reconstruction
- mesh generation and cleanup
- retopology
- export to FBX for downstream usage in Unreal Engine or Unity

Without this shared extrinsic calibration, downstream fusion and meshing cannot produce coherent multi-camera geometry.

