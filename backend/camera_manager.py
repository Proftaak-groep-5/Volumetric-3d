"""
Camera Manager for Orbbec Femto Bolt
Handles color and depth stream capture with multi-camera support
"""
from pyorbbecsdk import *
import numpy as np
import cv2
import base64
import time
from typing import Optional, Dict, Tuple
import threading
import logging
from calibration import CalibrationManager, CameraCalibration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CameraFrame:
    """Container for synchronized color and depth frames"""
    def __init__(self, camera_id: str, timestamp: float, 
                 color_data: Optional[np.ndarray] = None,
                 depth_data: Optional[np.ndarray] = None):
        self.camera_id = camera_id
        self.timestamp = timestamp
        self.color_data = color_data
        self.depth_data = depth_data
    
    def to_dict(self, encode_b64: bool = True) -> Dict:
        """Convert frame to dictionary for WebSocket transmission"""
        result = {
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
        }
        
        if encode_b64:
            if self.color_data is not None:
                # Encode color as JPEG for efficiency
                _, buffer = cv2.imencode('.jpg', self.color_data, [cv2.IMWRITE_JPEG_QUALITY, 85])
                result["color_b64"] = base64.b64encode(buffer).decode('utf-8')
                result["color_shape"] = self.color_data.shape
            
            if self.depth_data is not None:
                # Normalize depth for display (same as working code)
                if np.max(self.depth_data) > 0:
                    depth_display = cv2.convertScaleAbs(
                        self.depth_data, 
                        alpha=255.0 / np.max(self.depth_data)
                    )
                else:
                    depth_display = np.zeros_like(self.depth_data, dtype=np.uint8)
                
                # Encode normalized depth as JPEG
                _, buffer = cv2.imencode('.jpg', depth_display, [cv2.IMWRITE_JPEG_QUALITY, 90])
                result["depth_b64"] = base64.b64encode(buffer).decode('utf-8')
                result["depth_shape"] = self.depth_data.shape
        else:
            if self.color_data is not None:
                result["color"] = self.color_data.tolist()
            if self.depth_data is not None:
                result["depth"] = self.depth_data.tolist()
        
        return result


class OrbbecCamera:
    """Manages a single Orbbec Femto Bolt camera"""
    
    def __init__(self, device, camera_id: str, depth_res: Tuple[int, int], 
                 color_res: Tuple[int, int], fps: int = 30,
                 calibration_manager: Optional[CalibrationManager] = None):
        self.device = device
        self.camera_id = camera_id
        self.depth_res = depth_res
        self.color_res = color_res
        self.fps = fps
        self.pipeline = None
        self.running = False
        self.latest_frame: Optional[CameraFrame] = None
        self._lock = threading.Lock()
        self.calibration_manager = calibration_manager
        self.calibration: Optional[CameraCalibration] = None
        self.depth_profile = None
        self.color_profile = None
        
        info = device.get_device_info()
        logger.info(f"Initialized camera {camera_id}: {info.get_name()} (SN: {info.get_serial_number()})")
    
    def _get_best_depth_profile(self, profiles):
        """Select the best available depth profile - based on working code"""
        # Use same approach as working code
        resolutions = [
            (1024, 1024, OBFormat.Y16, 30),
            (1024, 1024, OBFormat.Y16, 15),
            (640, 400, OBFormat.Y16, 30),
            (640, 400, OBFormat.Y16, 15),
            (512, 512, OBFormat.Y16, 30),
            (512, 512, OBFormat.Y16, 15),
            (1280, 800, OBFormat.Y16, 30),
            (1280, 800, OBFormat.Y16, 15),
        ]
        
        for width, height, fmt, fps in resolutions:
            try:
                profile = profiles.get_video_stream_profile(width, height, fmt, fps)
                logger.info(f"  ✓ Found depth profile: {width}x{height} @ {fps}fps")
                return profile
            except:
                continue
        
        raise RuntimeError(f"No compatible depth profile found for camera {self.camera_id}")
    
    def _get_best_color_profile(self, profiles):
        """Select the best available color profile"""
        target_width, target_height = self.color_res
        
        # Try different formats
        formats = [OBFormat.RGB, OBFormat.YUYV, OBFormat.MJPG]
        
        for fmt in formats:
            try:
                profile = profiles.get_video_stream_profile(
                    target_width, target_height, fmt, self.fps
                )
                logger.info(f"  ✓ Found color profile: {target_width}x{target_height} @ {self.fps}fps ({fmt})")
                return profile
            except:
                continue
        
        # Fallback resolutions
        fallback_resolutions = [
            (1920, 1080, 30),
            (1280, 720, 30),
            (640, 480, 30),
            (1920, 1080, 15),
            (1280, 720, 15),
        ]
        
        for width, height, fps in fallback_resolutions:
            for fmt in formats:
                try:
                    profile = profiles.get_video_stream_profile(width, height, fmt, fps)
                    logger.info(f"  ✓ Found fallback color profile: {width}x{height} @ {fps}fps ({fmt})")
                    return profile
                except:
                    continue
        
        logger.warning(f"No color profile found for camera {self.camera_id}, will use depth only")
        return None
    
    def start(self):
        """Start the camera pipeline"""
        if self.running:
            logger.warning(f"Camera {self.camera_id} already running")
            return
        
        self.pipeline = Pipeline(self.device)
        config = Config()
        
        # Enable depth stream
        depth_profiles = self.pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
        self.depth_profile = self._get_best_depth_profile(depth_profiles)
        config.enable_stream(self.depth_profile)
        
        # Enable color stream if available
        try:
            color_profiles = self.pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            self.color_profile = self._get_best_color_profile(color_profiles)
            if self.color_profile:
                config.enable_stream(self.color_profile)
        except Exception as e:
            logger.warning(f"Could not enable color stream for {self.camera_id}: {e}")
            self.color_profile = None
        
        self.pipeline.start(config)
        self.running = True
        
        # Extract calibration after pipeline starts
        if self.calibration_manager:
            try:
                # Try to load existing calibration
                try:
                    self.calibration = self.calibration_manager.load_calibration(self.camera_id)
                    logger.info(f"Loaded existing calibration for {self.camera_id}")
                except FileNotFoundError:
                    # Extract intrinsics from device
                    self.calibration = self.calibration_manager.extract_intrinsics_from_device(
                        self.device, self.camera_id, self.depth_profile, self.color_profile
                    )
                    # Save calibration
                    self.calibration_manager.save_calibration(self.camera_id)
                    logger.info(f"Extracted and saved calibration for {self.camera_id}")
            except Exception as e:
                logger.warning(f"Could not extract calibration for {self.camera_id}: {e}")
        
        logger.info(f"Camera {self.camera_id} started")
    
    def capture_frame(self) -> Optional[CameraFrame]:
        """Capture a single frame from the camera"""
        if not self.running:
            return None
        
        try:
            frames = self.pipeline.wait_for_frames(100)
            if frames is None:
                return None
            
            timestamp = time.time()
            color_data = None
            depth_data = None
            
            # Get depth frame
            depth_frame = frames.get_depth_frame()
            if depth_frame:
                depth_data = np.frombuffer(
                    depth_frame.get_data(), 
                    dtype=np.uint16
                ).reshape((depth_frame.get_height(), depth_frame.get_width()))
            
            # Get color frame
            color_frame = frames.get_color_frame()
            if color_frame:
                # Convert to RGB format
                color_data = np.frombuffer(
                    color_frame.get_data(),
                    dtype=np.uint8
                ).reshape((color_frame.get_height(), color_frame.get_width(), -1))
                
                # Convert to RGB if needed
                if color_data.shape[2] == 2:  # YUYV
                    color_data = cv2.cvtColor(color_data, cv2.COLOR_YUV2RGB_YUYV)
                elif color_data.shape[2] == 3:
                    # Assuming BGR, convert to RGB
                    color_data = cv2.cvtColor(color_data, cv2.COLOR_BGR2RGB)
            
            frame = CameraFrame(self.camera_id, timestamp, color_data, depth_data)
            
            with self._lock:
                self.latest_frame = frame
            
            return frame
            
        except Exception as e:
            logger.error(f"Error capturing frame from {self.camera_id}: {e}")
            return None
    
    def get_latest_frame(self) -> Optional[CameraFrame]:
        """Get the latest captured frame"""
        with self._lock:
            return self.latest_frame
    
    def get_calibration(self) -> Optional[CameraCalibration]:
        """Get camera calibration parameters"""
        return self.calibration
    
    def stop(self):
        """Stop the camera pipeline"""
        if self.pipeline and self.running:
            self.pipeline.stop()
            self.running = False
            logger.info(f"Camera {self.camera_id} stopped")


class CameraManager:
    """Manages multiple Orbbec cameras"""
    
    def __init__(self, depth_res: Tuple[int, int] = (1024, 1024),
                 color_res: Tuple[int, int] = (1920, 1080),
                 fps: int = 30,
                 calibration_manager: Optional[CalibrationManager] = None):
        self.depth_res = depth_res
        self.color_res = color_res
        self.fps = fps
        self.cameras: Dict[str, OrbbecCamera] = {}
        self.ctx = None
        self._running = False
        self._capture_thread = None
        self.calibration_manager = calibration_manager or CalibrationManager()
    
    def discover_cameras(self) -> int:
        """Discover and initialize all connected cameras"""
        self.ctx = Context()
        device_list = self.ctx.query_devices()
        device_count = device_list.get_count()
        
        logger.info(f"Found {device_count} Orbbec camera(s)")
        
        for i in range(device_count):
            device = device_list.get_device_by_index(i)
            info = device.get_device_info()
            camera_id = f"cam{i}"
            
            camera = OrbbecCamera(
                device, camera_id, 
                self.depth_res, self.color_res, self.fps,
                calibration_manager=self.calibration_manager
            )
            self.cameras[camera_id] = camera
        
        return device_count
    
    def start_all(self):
        """Start all cameras"""
        for camera in self.cameras.values():
            camera.start()
        
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        logger.info("All cameras started")
    
    def _capture_loop(self):
        """Continuous capture loop for all cameras"""
        while self._running:
            for camera in self.cameras.values():
                camera.capture_frame()
            time.sleep(0.001)  # Small sleep to prevent busy-waiting
    
    def get_all_latest_frames(self) -> Dict[str, CameraFrame]:
        """Get latest frames from all cameras"""
        frames = {}
        for camera_id, camera in self.cameras.items():
            frame = camera.get_latest_frame()
            if frame:
                frames[camera_id] = frame
        return frames
    
    def stop_all(self):
        """Stop all cameras"""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        
        for camera in self.cameras.values():
            camera.stop()
        
        logger.info("All cameras stopped")
    
    def get_camera_count(self) -> int:
        """Get number of active cameras"""
        return len(self.cameras)
    
    def get_calibration_manager(self) -> CalibrationManager:
        """Get the calibration manager"""
        return self.calibration_manager

