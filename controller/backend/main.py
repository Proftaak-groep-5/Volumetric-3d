"""
FastAPI Backend for Multi-Camera 3D Recording Interface
Provides WebSocket streaming and recording endpoints
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import logging
from typing import List, Dict, Optional
import json

from config import settings
from camera_manager import CameraManager, CameraFrame
from recorder import RecordingManager
from calibration import CalibrationManager
import cv2
import numpy as np
from pathlib import Path


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Multi-Camera 3D Recording API",
    description="Real-time depth and color streaming from Orbbec Femto Bolt cameras",
    version="1.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
camera_manager: CameraManager = None
recording_manager: RecordingManager = None
active_websockets: List[WebSocket] = []

# Calibration capture state
calibration_capture_dir: Path = Path("./calibration_images")
calibration_captured_images: List[dict] = []  # Store captured image pairs


@app.on_event("startup")
async def startup_event():
    """Initialize cameras and recording manager on startup"""
    global camera_manager, recording_manager
    
    logger.info("Starting Multi-Camera 3D Recording Backend...")
    
    # Initialize camera manager
    camera_manager = CameraManager(
        depth_res=(settings.depth_width, settings.depth_height),
        color_res=(settings.color_width, settings.color_height),
        fps=settings.fps
    )
    
    try:
        # Discover and start cameras
        camera_count = camera_manager.discover_cameras()
        if camera_count == 0:
            logger.warning("No cameras found! Server will start but streaming won't work.")
        else:
            camera_manager.start_all()
            logger.info(f"Successfully initialized {camera_count} camera(s)")
    except Exception as e:
        logger.error(f"Error initializing cameras: {e}")
        logger.warning("Server will start without cameras")
    
    # Initialize recording manager
    recording_manager = RecordingManager(settings.recordings_path)
    logger.info(f"Recording path: {settings.recordings_path}")
    
    # Start broadcast task
    asyncio.create_task(broadcast_frames())
    
    logger.info("Backend ready! 🚀")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    
    # Stop recording if active
    if recording_manager and recording_manager.is_recording:
        recording_manager.stop_recording()
    
    # Stop cameras
    if camera_manager:
        camera_manager.stop_all()
    
    logger.info("Shutdown complete")


async def broadcast_frames():
    """Continuously broadcast frames to all connected WebSocket clients"""
    while True:
        try:
            if camera_manager and active_websockets:
                # Get latest frames from all cameras
                frames = camera_manager.get_all_latest_frames()
                
                if frames:
                    # Prepare message
                    message = {
                        "type": "frames",
                        "cameras": {}
                    }
                    
                    for camera_id, frame in frames.items():
                        message["cameras"][camera_id] = frame.to_dict(encode_b64=True)
                        
                        # Also record if recording is active
                        if recording_manager and recording_manager.is_recording:
                            recording_manager.record_frame(frame)
                    
                    # Broadcast to all connected clients
                    disconnected = []
                    for websocket in active_websockets:
                        try:
                            await websocket.send_json(message)
                        except Exception as e:
                            logger.warning(f"Error sending to websocket: {e}")
                            disconnected.append(websocket)
                    
                    # Remove disconnected clients
                    for ws in disconnected:
                        active_websockets.remove(ws)
            
            # Control frame rate (approximately 30 FPS)
            await asyncio.sleep(0.033)
            
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}")
            await asyncio.sleep(1)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Multi-Camera 3D Recording API",
        "version": "1.0.0",
        "status": "online"
    }


@app.get("/api/status")
async def get_status():
    """Get system status"""
    camera_count = camera_manager.get_camera_count() if camera_manager else 0
    recording_status = recording_manager.get_status() if recording_manager else {"is_recording": False}
    
    return {
        "cameras": {
            "count": camera_count,
            "active": camera_count > 0
        },
        "recording": recording_status,
        "websocket_clients": len(active_websockets)
    }


@app.get("/api/cameras")
async def get_cameras():
    """Get list of available cameras"""
    if not camera_manager:
        return {"cameras": []}
    
    cameras = []
    for camera_id, camera in camera_manager.cameras.items():
        cameras.append({
            "id": camera_id,
            "running": camera.running,
            "depth_resolution": camera.depth_res,
            "color_resolution": camera.color_res,
            "fps": camera.fps
        })
    
    return {"cameras": cameras}


@app.post("/api/record/start")
async def start_recording():
    """Start recording"""
    if not camera_manager or camera_manager.get_camera_count() == 0:
        raise HTTPException(status_code=400, detail="No cameras available")
    
    if recording_manager.is_recording:
        raise HTTPException(status_code=400, detail="Already recording")
    
    try:
        camera_ids = list(camera_manager.cameras.keys())
        session_id = recording_manager.start_recording(camera_ids)
        
        logger.info(f"Recording started: {session_id}")
        
        return {
            "status": "recording",
            "session_id": session_id,
            "cameras": camera_ids
        }
    except Exception as e:
        logger.error(f"Error starting recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/record/stop")
async def stop_recording():
    """Stop recording"""
    if not recording_manager.is_recording:
        raise HTTPException(status_code=400, detail="Not currently recording")
    
    try:
        metadata = recording_manager.stop_recording()
        logger.info(f"Recording stopped: {metadata['session_id']}")
        
        return {
            "status": "stopped",
            "metadata": metadata
        }
    except Exception as e:
        logger.error(f"Error stopping recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live frame streaming"""
    await websocket.accept()
    active_websockets.append(websocket)
    
    logger.info(f"WebSocket client connected. Total clients: {len(active_websockets)}")
    
    try:
        # Send initial status
        status = await get_status()
        await websocket.send_json({
            "type": "status",
            "data": status
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle client messages (e.g., requests for specific camera)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"Error receiving websocket message: {e}")
                break
    
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(active_websockets)}")


@app.get("/api/recordings")
async def list_recordings():
    """List all recordings"""
    if not recording_manager:
        return {"recordings": []}
    
    recordings = []
    recordings_path = recording_manager.recordings_path
    
    if recordings_path.exists():
        for session_dir in sorted(recordings_path.iterdir(), reverse=True):
            if session_dir.is_dir():
                meta_file = session_dir / "meta.json"
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        metadata = json.load(f)
                    recordings.append(metadata)
    
    return {"recordings": recordings}


@app.get("/api/calibration/status")
async def get_calibration_status():
    """Get calibration status for all cameras"""
    if not camera_manager:
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    calib_manager = camera_manager.get_calibration_manager()
    
    status = {
        "cameras": {},
        "stereo": {}
    }
    
    # Get calibration for each camera
    for camera_id, camera in camera_manager.cameras.items():
        calib = camera.get_calibration()
        if calib:
            status["cameras"][camera_id] = {
                "calibrated": True,
                "has_intrinsics": calib.camera_matrix is not None,
                "depth_resolution": calib.depth_resolution,
                "color_resolution": calib.color_resolution,
                "intrinsics": calib.depth_intrinsics if calib.depth_intrinsics else None
            }
        else:
            status["cameras"][camera_id] = {
                "calibrated": False
            }
    
    # Get stereo calibrations
    camera_ids = list(camera_manager.cameras.keys())
    if len(camera_ids) >= 2:
        for i in range(len(camera_ids)):
            for j in range(i + 1, len(camera_ids)):
                cam1, cam2 = camera_ids[i], camera_ids[j]
                stereo = calib_manager.get_stereo_calibration(cam1, cam2)
                if stereo:
                    key = f"{cam1}_{cam2}"
                    # Convert 3x1 matrix to flat array [x, y, z]
                    translation = None
                    if stereo.T is not None:
                        translation = [stereo.T[0, 0], stereo.T[1, 0], stereo.T[2, 0]]
                    status["stereo"][key] = {
                        "calibrated": True,
                        "translation": translation
                    }
                else:
                    key = f"{cam1}_{cam2}"
                    status["stereo"][key] = {
                        "calibrated": False
                    }
    
    return status


@app.get("/api/calibration/{camera_id}")
async def get_camera_calibration(camera_id: str):
    """Get calibration parameters for a specific camera"""
    if not camera_manager:
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    if camera_id not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    camera = camera_manager.cameras[camera_id]
    calib = camera.get_calibration()
    
    if not calib:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not calibrated")
    
    return calib.to_dict()


@app.get("/api/calibration/stereo/{camera_id_1}/{camera_id_2}")
async def get_stereo_calibration(camera_id_1: str, camera_id_2: str):
    """Get stereo calibration between two cameras"""
    if not camera_manager:
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    if camera_id_1 not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if camera_id_2 not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")
    
    calib_manager = camera_manager.get_calibration_manager()
    stereo = calib_manager.get_stereo_calibration(camera_id_1, camera_id_2)
    
    if not stereo:
        raise HTTPException(
            status_code=404, 
            detail=f"Stereo calibration not found for {camera_id_1} and {camera_id_2}"
        )
    
    return stereo.to_dict()


@app.post("/api/calibration/capture")
async def capture_calibration_image(
    camera_id_1: str = Query(..., description="First camera ID"),
    camera_id_2: str = Query(..., description="Second camera ID"),
    checkerboard_cols: int = Query(8, description="Number of inner corners (columns)"),
    checkerboard_rows: int = Query(5, description="Number of inner corners (rows)")
):
    """Capture a synchronized image pair for calibration"""
    global calibration_captured_images
    
    logger.info(f"Capture request: cameras {camera_id_1} and {camera_id_2}")
    
    if not camera_manager:
        logger.error("Camera manager not initialized")
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    if camera_id_1 not in camera_manager.cameras:
        logger.error(f"Camera {camera_id_1} not found")
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if camera_id_2 not in camera_manager.cameras:
        logger.error(f"Camera {camera_id_2} not found")
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")
    
    # Check if cameras are running
    cam1 = camera_manager.cameras[camera_id_1]
    cam2 = camera_manager.cameras[camera_id_2]
    
    if not hasattr(cam1, 'running') or not cam1.running:
        logger.error(f"Camera {camera_id_1} is not running. Cameras must be started first.")
        raise HTTPException(
            status_code=400, 
            detail=f"Camera {camera_id_1} is not running. Please start the cameras first."
        )
    if not hasattr(cam2, 'running') or not cam2.running:
        logger.error(f"Camera {camera_id_2} is not running. Cameras must be started first.")
        raise HTTPException(
            status_code=400, 
            detail=f"Camera {camera_id_2} is not running. Please start the cameras first."
        )
    
    logger.info("Cameras are running, attempting to get frames...")
    
    # Get latest frames
    frames = camera_manager.get_all_latest_frames()
    logger.info(f"Retrieved frames from {len(frames)} cameras")
    
    if camera_id_1 not in frames:
        logger.error(f"No frame available for camera {camera_id_1}")
        raise HTTPException(
            status_code=400, 
            detail=f"Frame not available for camera {camera_id_1}. Make sure cameras are streaming."
        )
    if camera_id_2 not in frames:
        logger.error(f"No frame available for camera {camera_id_2}")
        raise HTTPException(
            status_code=400, 
            detail=f"Frame not available for camera {camera_id_2}. Make sure cameras are streaming."
        )
    
    frame1 = frames[camera_id_1]
    frame2 = frames[camera_id_2]
    
    if frame1.color_data is None:
        logger.error(f"Color data not available for camera {camera_id_1}")
        raise HTTPException(
            status_code=400, 
            detail=f"Color data not available for camera {camera_id_1}. Make sure color stream is enabled."
        )
    if frame2.color_data is None:
        logger.error(f"Color data not available for camera {camera_id_2}")
        raise HTTPException(
            status_code=400, 
            detail=f"Color data not available for camera {camera_id_2}. Make sure color stream is enabled."
        )
    
    logger.info(f"Frames retrieved: {frame1.color_data.shape} and {frame2.color_data.shape}")
    
    # Convert to BGR for OpenCV
    img1 = cv2.cvtColor(frame1.color_data, cv2.COLOR_RGB2BGR)
    img2 = cv2.cvtColor(frame2.color_data, cv2.COLOR_RGB2BGR)
    
    # STEP 1: Test Camera 1 ONLY with 8x5 pattern
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    checkerboard_size = (checkerboard_cols, checkerboard_rows)  # 8x5
    
    logger.info(f"=== CAPTURE: Testing pattern {checkerboard_size} (cols x rows = {checkerboard_cols}x{checkerboard_rows}) ===")
    logger.info(f"Step 1: Testing Camera {camera_id_1}...")
    logger.info(f"Camera 1 image: {gray1.shape}, range=[{gray1.min()}-{gray1.max()}], mean={gray1.mean():.1f}")
    
    ret1 = False
    corners1 = None
    
    # Try different preprocessing methods for Camera 1
    methods_to_try = [
        ("Original", gray1),
        ("CLAHE", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray1)),
        ("Adaptive Threshold", cv2.adaptiveThreshold(gray1, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
    ]
    
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
    
    # Try with flags first
    for method_name, processed_img in methods_to_try:
        r1, c1 = cv2.findChessboardCorners(processed_img, checkerboard_size, flags)
        if r1:
            ret1 = True
            corners1 = c1
            logger.info(f"✓ Camera 1: FOUND with {method_name} (with flags)")
            break
    
    # If not found, try without flags
    if not ret1:
        for method_name, processed_img in methods_to_try:
            r1, c1 = cv2.findChessboardCorners(processed_img, checkerboard_size, None)
            if r1:
                ret1 = True
                corners1 = c1
                logger.info(f"✓ Camera 1: FOUND with {method_name} (no flags)")
                break
    
    if not ret1:
        logger.error(f"✗ Camera 1: NOT FOUND with pattern {checkerboard_cols}x{checkerboard_rows}")
        raise HTTPException(
            status_code=400,
            detail=f"Camera {camera_id_1}: Checkerboard pattern {checkerboard_cols}x{checkerboard_rows} not found. Check if checkerboard is fully visible, well-lit, and pattern size is correct (8 inner corners horizontally, 5 vertically)."
        )
    
    # STEP 2: Test Camera 2 ONLY (now that Camera 1 works)
    logger.info(f"Step 2: Testing Camera {camera_id_2}...")
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    logger.info(f"Camera 2 image: {gray2.shape}, range=[{gray2.min()}-{gray2.max()}], mean={gray2.mean():.1f}")
    
    ret2 = False
    corners2 = None
    
    # Try different preprocessing methods for Camera 2
    methods_to_try_2 = [
        ("Original", gray2),
        ("CLAHE", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray2)),
        ("Adaptive Threshold", cv2.adaptiveThreshold(gray2, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
    ]
    
    # Try with flags first
    for method_name, processed_img in methods_to_try_2:
        r2, c2 = cv2.findChessboardCorners(processed_img, checkerboard_size, flags)
        if r2:
            ret2 = True
            corners2 = c2
            logger.info(f"✓ Camera 2: FOUND with {method_name} (with flags)")
            break
    
    # If not found, try without flags
    if not ret2:
        for method_name, processed_img in methods_to_try_2:
            r2, c2 = cv2.findChessboardCorners(processed_img, checkerboard_size, None)
            if r2:
                ret2 = True
                corners2 = c2
                logger.info(f"✓ Camera 2: FOUND with {method_name} (no flags)")
                break
    
    if not ret2:
        logger.error(f"✗ Camera 2: NOT FOUND with pattern {checkerboard_cols}x{checkerboard_rows}")
        raise HTTPException(
            status_code=400,
            detail=f"Camera {camera_id_2}: Checkerboard pattern {checkerboard_cols}x{checkerboard_rows} not found. Check if checkerboard is fully visible, well-lit, and pattern size is correct (8 inner corners horizontally, 5 vertically)."
        )
    
    # STEP 3: Both cameras found - refine corners
    logger.info(f"✓✓✓ SUCCESS: Both cameras found pattern {checkerboard_cols}x{checkerboard_rows}!")
    
    # Refine corners for better accuracy
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners1 = cv2.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)
    corners2 = cv2.cornerSubPix(gray2, corners2, (11, 11), (-1, -1), criteria)
    logger.info(f"Refined corners: Camera 1: {len(corners1)}, Camera 2: {len(corners2)}")
    
    # Save images
    calibration_capture_dir.mkdir(parents=True, exist_ok=True)
    image_index = len(calibration_captured_images)
    
    img1_path = calibration_capture_dir / f"{camera_id_1}_{image_index:03d}.png"
    img2_path = calibration_capture_dir / f"{camera_id_2}_{image_index:03d}.png"
    
    cv2.imwrite(str(img1_path), img1)
    cv2.imwrite(str(img2_path), img2)
    
    # Store metadata
    calibration_captured_images.append({
        "index": image_index,
        "camera_id_1": camera_id_1,
        "camera_id_2": camera_id_2,
        "timestamp": frame1.timestamp,
        "checkerboard_found": True
    })
    
    logger.info(f"Captured calibration image pair {image_index + 1}")
    
    return {
        "success": True,
        "image_index": image_index,
        "total_captured": len(calibration_captured_images),
        "checkerboard_found": True
    }


@app.get("/api/calibration/capture/status")
async def get_calibration_capture_status():
    """Get status of captured calibration images"""
    return {
        "total_captured": len(calibration_captured_images),
        "images": calibration_captured_images
    }


@app.get("/api/calibration/debug-image/{camera_id}")
async def get_debug_image(camera_id: str):
    """Get a debug image from camera to test checkerboard detection"""
    if not camera_manager:
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    if camera_id not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    frames = camera_manager.get_all_latest_frames()
    if camera_id not in frames:
        raise HTTPException(status_code=400, detail="Frame not available")
    
    frame = frames[camera_id]
    if frame.color_data is None:
        raise HTTPException(status_code=400, detail="Color data not available")
    
    # Convert to BGR and save as JPEG
    img = cv2.cvtColor(frame.color_data, cv2.COLOR_RGB2BGR)
    
    # Encode as JPEG
    import base64
    _, buffer = cv2.imencode('.jpg', img)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    
    return {
        "camera_id": camera_id,
        "image": f"data:image/jpeg;base64,{img_base64}",
        "shape": list(img.shape)
    }


@app.get("/api/calibration/detect-checkerboard")
async def check_checkerboard(
    camera_id_1: str = Query(..., description="First camera ID"),
    camera_id_2: str = Query(..., description="Second camera ID"),
    checkerboard_cols: int = Query(8, description="Number of inner corners (columns)"),
    checkerboard_rows: int = Query(5, description="Number of inner corners (rows)")
):
    """Check if checkerboard is visible in both camera views - STEP BY STEP: Camera 1 first, then Camera 2"""
    logger.info(f"=== CHECKERBOARD DETECTION: {checkerboard_cols}x{checkerboard_rows} ===")
    logger.info(f"Step 1: Testing Camera {camera_id_1}...")
    if not camera_manager:
        return {
            "camera_1": {"detected": False, "reason": "Camera manager not initialized"},
            "camera_2": {"detected": False, "reason": "Camera manager not initialized"},
            "both_detected": False
        }
    
    if camera_id_1 not in camera_manager.cameras:
        return {
            "camera_1": {"detected": False, "reason": f"Camera {camera_id_1} not found"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False
        }
    if camera_id_2 not in camera_manager.cameras:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": f"Camera {camera_id_2} not found"},
            "both_detected": False
        }
    
    # Check if cameras are running
    cam1 = camera_manager.cameras[camera_id_1]
    cam2 = camera_manager.cameras[camera_id_2]
    
    if not hasattr(cam1, 'running') or not cam1.running:
        return {
            "camera_1": {"detected": False, "reason": "Camera not running"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False
        }
    if not hasattr(cam2, 'running') or not cam2.running:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": "Camera not running"},
            "both_detected": False
        }
    
    # Get latest frames
    frames = camera_manager.get_all_latest_frames()
    
    if camera_id_1 not in frames:
        return {
            "camera_1": {"detected": False, "reason": "Frame not available"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False
        }
    if camera_id_2 not in frames:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": "Frame not available"},
            "both_detected": False
        }
    
    frame1 = frames[camera_id_1]
    frame2 = frames[camera_id_2]
    
    if frame1.color_data is None:
        return {
            "camera_1": {"detected": False, "reason": "Color data not available"},
            "camera_2": {"detected": False, "reason": ""},
            "both_detected": False
        }
    if frame2.color_data is None:
        return {
            "camera_1": {"detected": False, "reason": ""},
            "camera_2": {"detected": False, "reason": "Color data not available"},
            "both_detected": False
        }
    
    # Convert to BGR for OpenCV
    img1 = cv2.cvtColor(frame1.color_data, cv2.COLOR_RGB2BGR)
    img2 = cv2.cvtColor(frame2.color_data, cv2.COLOR_RGB2BGR)
    
    # STEP 1: Test Camera 1 ONLY with 8x5 pattern
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    checkerboard_size = (checkerboard_cols, checkerboard_rows)  # 8x5
    
    logger.info(f"Camera 1 image: {gray1.shape}, range=[{gray1.min()}-{gray1.max()}], mean={gray1.mean():.1f}")
    logger.info(f"Testing pattern: {checkerboard_size} (cols x rows = {checkerboard_cols}x{checkerboard_rows})")
    
    ret1 = False
    corners1 = None
    method_used_1 = None
    
    # Try different preprocessing methods for Camera 1
    methods_to_try = [
        ("Original", gray1),
        ("CLAHE", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray1)),
        ("Adaptive Threshold", cv2.adaptiveThreshold(gray1, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
    ]
    
    # Try with flags first
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
    for method_name, processed_img in methods_to_try:
        r1, c1 = cv2.findChessboardCorners(processed_img, checkerboard_size, flags)
        if r1:
            ret1 = True
            corners1 = c1
            method_used_1 = method_name
            logger.info(f"✓ Camera 1: FOUND with {method_name} (with flags)")
            break
    
    # If not found, try without flags
    if not ret1:
        for method_name, processed_img in methods_to_try:
            r1, c1 = cv2.findChessboardCorners(processed_img, checkerboard_size, None)
            if r1:
                ret1 = True
                corners1 = c1
                method_used_1 = method_name
                logger.info(f"✓ Camera 1: FOUND with {method_name} (no flags)")
                break
    
    if not ret1:
        logger.error(f"✗ Camera 1: NOT FOUND with pattern {checkerboard_cols}x{checkerboard_rows}")
        return {
            "camera_1": {"detected": False, "reason": f"Pattern {checkerboard_cols}x{checkerboard_rows} not found. Check if checkerboard is fully visible, well-lit, and pattern size is correct (8 inner corners horizontally, 5 vertically)."},
            "camera_2": {"detected": False, "reason": "Not tested - Camera 1 failed"},
            "both_detected": False,
            "pattern_tested": f"{checkerboard_cols}x{checkerboard_rows}"
        }
    
    # Refine corners for Camera 1
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners1 = cv2.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)
    logger.info(f"Camera 1: Refined {len(corners1)} corners")
    
    # STEP 2: Test Camera 2 ONLY (now that Camera 1 works)
    logger.info(f"Step 2: Testing Camera {camera_id_2}...")
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    logger.info(f"Camera 2 image: {gray2.shape}, range=[{gray2.min()}-{gray2.max()}], mean={gray2.mean():.1f}")
    
    ret2 = False
    corners2 = None
    method_used_2 = None
    
    # Try different preprocessing methods for Camera 2
    methods_to_try_2 = [
        ("Original", gray2),
        ("CLAHE", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray2)),
        ("Adaptive Threshold", cv2.adaptiveThreshold(gray2, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
    ]
    
    # Try with flags first
    for method_name, processed_img in methods_to_try_2:
        r2, c2 = cv2.findChessboardCorners(processed_img, checkerboard_size, flags)
        if r2:
            ret2 = True
            corners2 = c2
            method_used_2 = method_name
            logger.info(f"✓ Camera 2: FOUND with {method_name} (with flags)")
            break
    
    # If not found, try without flags
    if not ret2:
        for method_name, processed_img in methods_to_try_2:
            r2, c2 = cv2.findChessboardCorners(processed_img, checkerboard_size, None)
            if r2:
                ret2 = True
                corners2 = c2
                method_used_2 = method_name
                logger.info(f"✓ Camera 2: FOUND with {method_name} (no flags)")
                break
    
    if not ret2:
        logger.error(f"✗ Camera 2: NOT FOUND with pattern {checkerboard_cols}x{checkerboard_rows}")
        return {
            "camera_1": {"detected": True, "reason": None},
            "camera_2": {"detected": False, "reason": f"Pattern {checkerboard_cols}x{checkerboard_rows} not found. Check if checkerboard is fully visible, well-lit, and pattern size is correct (8 inner corners horizontally, 5 vertically)."},
            "both_detected": False,
            "pattern_tested": f"{checkerboard_cols}x{checkerboard_rows}"
        }
    
    # Refine corners for Camera 2
    corners2 = cv2.cornerSubPix(gray2, corners2, (11, 11), (-1, -1), criteria)
    logger.info(f"Camera 2: Refined {len(corners2)} corners")
    
    # STEP 3: Both cameras found!
    logger.info(f"✓✓✓ SUCCESS: Both cameras found pattern {checkerboard_cols}x{checkerboard_rows}!")
    logger.info(f"   Camera 1: {method_used_1}, {len(corners1)} corners")
    logger.info(f"   Camera 2: {method_used_2}, {len(corners2)} corners")
    
    return {
        "camera_1": {"detected": True, "reason": None},
        "camera_2": {"detected": True, "reason": None},
        "both_detected": True,
        "pattern_tested": f"{checkerboard_cols}x{checkerboard_rows}"
    }


@app.post("/api/calibration/capture/clear")
async def clear_calibration_captures():
    """Clear all captured calibration images"""
    global calibration_captured_images
    
    # Delete image files
    if calibration_capture_dir.exists():
        for img_file in calibration_capture_dir.glob("*.png"):
            try:
                img_file.unlink()
            except:
                pass
    
    calibration_captured_images = []
    
    return {"success": True, "message": "Calibration captures cleared"}


@app.post("/api/calibration/perform")
async def perform_stereo_calibration(
    camera_id_1: str = Query(..., description="First camera ID"),
    camera_id_2: str = Query(..., description="Second camera ID"),
    checkerboard_cols: int = Query(8, description="Number of inner corners (columns)"),
    checkerboard_rows: int = Query(5, description="Number of inner corners (rows)"),
    square_size: float = Query(0.025, description="Square size in meters")
):
    """Perform stereo calibration from captured images"""
    if not camera_manager:
        raise HTTPException(status_code=400, detail="Camera manager not initialized")
    
    if camera_id_1 not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_1} not found")
    if camera_id_2 not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id_2} not found")
    
    if len(calibration_captured_images) < 10:
        raise HTTPException(
            status_code=400, 
            detail=f"Need at least 10 captured image pairs, found {len(calibration_captured_images)}"
        )
    
    # Load images
    images_1 = []
    images_2 = []
    
    img_files_1 = sorted(calibration_capture_dir.glob(f"{camera_id_1}_*.png"))
    img_files_2 = sorted(calibration_capture_dir.glob(f"{camera_id_2}_*.png"))
    
    if len(img_files_1) != len(img_files_2):
        raise HTTPException(
            status_code=400,
            detail=f"Mismatched number of images ({len(img_files_1)} vs {len(img_files_2)})"
        )
    
    for img1_path, img2_path in zip(img_files_1, img_files_2):
        img1 = cv2.imread(str(img1_path))
        img2 = cv2.imread(str(img2_path))
        
        if img1 is None or img2 is None:
            continue
        
        images_1.append(img1)
        images_2.append(img2)
    
    if len(images_1) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 10 valid image pairs, found {len(images_1)}"
        )
    
    # Perform calibration
    try:
        calib_manager = camera_manager.get_calibration_manager()
        checkerboard_size = (checkerboard_cols, checkerboard_rows)
        
        stereo = calib_manager.calibrate_stereo_from_checkerboard(
            camera_id_1, camera_id_2,
            images_1, images_2,
            checkerboard_size, square_size
        )
        
        # Save calibration
        calib_manager.save_stereo_calibration(camera_id_1, camera_id_2)
        
        logger.info(f"Stereo calibration completed for {camera_id_1} and {camera_id_2}")
        
        return {
            "success": True,
            "reprojection_error": float(stereo.reprojection_error) if stereo.reprojection_error is not None else None,
            "translation": [float(stereo.T[0, 0]), float(stereo.T[1, 0]), float(stereo.T[2, 0])] if stereo.T is not None else None,
            "images_used": len(images_1)
        }
    except Exception as e:
        logger.error(f"Stereo calibration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True
    )

