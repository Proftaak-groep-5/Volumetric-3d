"""
Camera Calibration Module for Orbbec Femto Bolt
Handles intrinsic and stereo calibration for multi-camera setup
"""
import numpy as np
import cv2
import json
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import logging
from pyorbbecsdk import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CameraCalibration:
    """Stores calibration parameters for a single camera"""
    
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        # Intrinsic parameters
        self.camera_matrix: Optional[np.ndarray] = None  # 3x3 K matrix
        self.distortion_coeffs: Optional[np.ndarray] = None  # Distortion coefficients
        self.depth_intrinsics: Optional[Dict] = None  # Depth sensor intrinsics
        self.color_intrinsics: Optional[Dict] = None  # Color sensor intrinsics
        
        # Resolution
        self.depth_resolution: Optional[Tuple[int, int]] = None
        self.color_resolution: Optional[Tuple[int, int]] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            "camera_id": self.camera_id,
            "depth_resolution": self.depth_resolution,
            "color_resolution": self.color_resolution,
        }
        
        if self.camera_matrix is not None:
            result["camera_matrix"] = self.camera_matrix.tolist()
        
        if self.distortion_coeffs is not None:
            result["distortion_coeffs"] = self.distortion_coeffs.tolist()
        
        if self.depth_intrinsics:
            result["depth_intrinsics"] = self.depth_intrinsics
        
        if self.color_intrinsics:
            result["color_intrinsics"] = self.color_intrinsics
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CameraCalibration':
        """Create from dictionary"""
        calib = cls(data["camera_id"])
        
        if "camera_matrix" in data:
            calib.camera_matrix = np.array(data["camera_matrix"])
        
        if "distortion_coeffs" in data:
            calib.distortion_coeffs = np.array(data["distortion_coeffs"])
        
        if "depth_intrinsics" in data:
            calib.depth_intrinsics = data["depth_intrinsics"]
        
        if "color_intrinsics" in data:
            calib.color_intrinsics = data["color_intrinsics"]
        
        if "depth_resolution" in data:
            calib.depth_resolution = tuple(data["depth_resolution"])
        
        if "color_resolution" in data:
            calib.color_resolution = tuple(data["color_resolution"])
        
        return calib


class StereoCalibration:
    """Stores stereo calibration parameters between two cameras"""
    
    def __init__(self, camera_id_1: str, camera_id_2: str):
        self.camera_id_1 = camera_id_1
        self.camera_id_2 = camera_id_2
        
        # Rotation and translation from camera 1 to camera 2
        self.R: Optional[np.ndarray] = None  # 3x3 rotation matrix
        self.T: Optional[np.ndarray] = None  # 3x1 translation vector
        
        # Essential and fundamental matrices
        self.E: Optional[np.ndarray] = None  # Essential matrix
        self.F: Optional[np.ndarray] = None  # Fundamental matrix
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            "camera_id_1": self.camera_id_1,
            "camera_id_2": self.camera_id_2,
        }
        
        if self.R is not None:
            result["R"] = self.R.tolist()
        
        if self.T is not None:
            result["T"] = self.T.tolist()
        
        if self.E is not None:
            result["E"] = self.E.tolist()
        
        if self.F is not None:
            result["F"] = self.F.tolist()
        
        if self.reprojection_error is not None:
            result["reprojection_error"] = self.reprojection_error
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StereoCalibration':
        """Create from dictionary"""
        stereo = cls(data["camera_id_1"], data["camera_id_2"])
        
        if "R" in data:
            stereo.R = np.array(data["R"])
        
        if "T" in data:
            stereo.T = np.array(data["T"])
        
        if "E" in data:
            stereo.E = np.array(data["E"])
        
        if "F" in data:
            stereo.F = np.array(data["F"])
        
        if "reprojection_error" in data:
            stereo.reprojection_error = data["reprojection_error"]
        
        return stereo


class CalibrationManager:
    """Manages calibration for multiple cameras"""
    
    def __init__(self, calibration_path: Path = Path("./calibrations")):
        self.calibration_path = calibration_path
        self.calibration_path.mkdir(parents=True, exist_ok=True)
        
        self.camera_calibrations: Dict[str, CameraCalibration] = {}
        self.stereo_calibrations: Dict[Tuple[str, str], StereoCalibration] = {}
    
    def extract_intrinsics_from_device(self, device, camera_id: str, 
                                       depth_profile, color_profile=None) -> CameraCalibration:
        """Extract camera intrinsics from Orbbec device"""
        calib = CameraCalibration(camera_id)
        
        # Try multiple methods to get intrinsics from Orbbec SDK
        intrinsics_extracted = False
        
        # Method 1: Try get_depth_intrinsics() (common method)
        try:
            if hasattr(device, 'get_depth_intrinsics'):
                depth_intrinsics = device.get_depth_intrinsics()
                if depth_intrinsics:
                    calib.depth_intrinsics = {
                        "fx": depth_intrinsics.fx,
                        "fy": depth_intrinsics.fy,
                        "cx": depth_intrinsics.cx,
                        "cy": depth_intrinsics.cy,
                        "width": depth_intrinsics.width,
                        "height": depth_intrinsics.height,
                    }
                    
                    calib.camera_matrix = np.array([
                        [depth_intrinsics.fx, 0, depth_intrinsics.cx],
                        [0, depth_intrinsics.fy, depth_intrinsics.cy],
                        [0, 0, 1]
                    ], dtype=np.float64)
                    
                    calib.depth_resolution = (depth_intrinsics.width, depth_intrinsics.height)
                    intrinsics_extracted = True
                    logger.info(f"Extracted depth intrinsics for {camera_id}: "
                              f"fx={depth_intrinsics.fx:.2f}, fy={depth_intrinsics.fy:.2f}, "
                              f"cx={depth_intrinsics.cx:.2f}, cy={depth_intrinsics.cy:.2f}")
        except Exception as e:
            logger.debug(f"Method 1 failed for {camera_id}: {e}")
        
        # Method 2: Try get_camera_param() (alternative method)
        if not intrinsics_extracted:
            try:
                if hasattr(device, 'get_camera_param'):
                    params = device.get_camera_param()
                    if params and hasattr(params, 'depth_intrinsics'):
                        di = params.depth_intrinsics
                        calib.depth_intrinsics = {
                            "fx": di.fx, "fy": di.fy,
                            "cx": di.cx, "cy": di.cy,
                            "width": di.width, "height": di.height,
                        }
                        calib.camera_matrix = np.array([
                            [di.fx, 0, di.cx],
                            [0, di.fy, di.cy],
                            [0, 0, 1]
                        ], dtype=np.float64)
                        calib.depth_resolution = (di.width, di.height)
                        intrinsics_extracted = True
                        logger.info(f"Extracted depth intrinsics (method 2) for {camera_id}")
            except Exception as e:
                logger.debug(f"Method 2 failed for {camera_id}: {e}")
        
        # Method 3: Try OBCameraParam (if available)
        if not intrinsics_extracted:
            try:
                from pyorbbecsdk import OBCameraParam
                if hasattr(device, 'get_camera_param_list'):
                    param_list = device.get_camera_param_list()
                    if param_list and len(param_list) > 0:
                        # Use first available param
                        param = param_list[0]
                        if hasattr(param, 'depth_intrinsics'):
                            di = param.depth_intrinsics
                            calib.depth_intrinsics = {
                                "fx": di.fx, "fy": di.fy,
                                "cx": di.cx, "cy": di.cy,
                                "width": di.width, "height": di.height,
                            }
                            calib.camera_matrix = np.array([
                                [di.fx, 0, di.cx],
                                [0, di.fy, di.cy],
                                [0, 0, 1]
                            ], dtype=np.float64)
                            calib.depth_resolution = (di.width, di.height)
                            intrinsics_extracted = True
                            logger.info(f"Extracted depth intrinsics (method 3) for {camera_id}")
            except Exception as e:
                logger.debug(f"Method 3 failed for {camera_id}: {e}")
        
        # Get color intrinsics if available
        if color_profile:
            try:
                if hasattr(device, 'get_color_intrinsics'):
                    color_intrinsics = device.get_color_intrinsics()
                    if color_intrinsics:
                        calib.color_intrinsics = {
                            "fx": color_intrinsics.fx, "fy": color_intrinsics.fy,
                            "cx": color_intrinsics.cx, "cy": color_intrinsics.cy,
                            "width": color_intrinsics.width, "height": color_intrinsics.height,
                        }
                        calib.color_resolution = (color_intrinsics.width, color_intrinsics.height)
            except:
                pass
        
        # Try to get distortion coefficients
        try:
            if hasattr(device, 'get_depth_distortion'):
                depth_distortion = device.get_depth_distortion()
                if depth_distortion:
                    calib.distortion_coeffs = np.array([
                        depth_distortion.k1, depth_distortion.k2,
                        depth_distortion.p1, depth_distortion.p2,
                        depth_distortion.k3
                    ], dtype=np.float64)
        except:
            pass
        
        # Fallback: estimate intrinsics based on resolution
        if not intrinsics_extracted:
            logger.info(f"Could not extract intrinsics from device for {camera_id}, using estimates")
            if depth_profile:
                width = depth_profile.get_width()
                height = depth_profile.get_height()
                calib.depth_resolution = (width, height)
                
                # Estimate focal length (typical for Femto Bolt: ~600-700 for 1024x1024)
                # Using a more accurate estimate based on typical depth camera specs
                fx = fy = width * 0.65  # Better estimate for Femto Bolt
                cx, cy = width / 2, height / 2
                
                calib.camera_matrix = np.array([
                    [fx, 0, cx],
                    [0, fy, cy],
                    [0, 0, 1]
                ], dtype=np.float64)
                
                calib.depth_intrinsics = {
                    "fx": fx, "fy": fy, "cx": cx, "cy": cy,
                    "width": width, "height": height
                }
        
        # Set default distortion if not set
        if calib.distortion_coeffs is None and calib.camera_matrix is not None:
            calib.distortion_coeffs = np.zeros(5, dtype=np.float64)
        
        self.camera_calibrations[camera_id] = calib
        return calib
    
    def calibrate_stereo_from_checkerboard(self, 
                                           camera_id_1: str, camera_id_2: str,
                                           images_1: List[np.ndarray], images_2: List[np.ndarray],
                                           checkerboard_size: Tuple[int, int] = (9, 6),
                                           square_size: float = 0.025) -> StereoCalibration:
        """
        Perform stereo calibration using checkerboard pattern
        
        Args:
            camera_id_1: ID of first camera
            camera_id_2: ID of second camera
            images_1: List of grayscale images from camera 1
            images_2: List of grayscale images from camera 2 (synchronized)
            checkerboard_size: (cols, rows) of inner corners
            square_size: Size of checkerboard square in meters
        """
        if camera_id_1 not in self.camera_calibrations:
            raise ValueError(f"Camera {camera_id_1} not calibrated")
        if camera_id_2 not in self.camera_calibrations:
            raise ValueError(f"Camera {camera_id_2} not calibrated")
        
        calib_1 = self.camera_calibrations[camera_id_1]
        calib_2 = self.camera_calibrations[camera_id_2]
        
        # Prepare object points
        objp = np.zeros((checkerboard_size[0] * checkerboard_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:checkerboard_size[0], 0:checkerboard_size[1]].T.reshape(-1, 2)
        objp *= square_size
        
        # Find corners in both image sets
        objpoints = []
        imgpoints_1 = []
        imgpoints_2 = []
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        
        valid_pairs = 0
        for img1, img2 in zip(images_1, images_2):
            if len(img1.shape) == 3:
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            else:
                gray1 = img1
            
            if len(img2.shape) == 3:
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            else:
                gray2 = img2
            
            ret1, corners1 = cv2.findChessboardCorners(gray1, checkerboard_size, None)
            ret2, corners2 = cv2.findChessboardCorners(gray2, checkerboard_size, None)
            
            if ret1 and ret2:
                corners1 = cv2.cornerSubPix(gray1, corners1, (11, 11), (-1, -1), criteria)
                corners2 = cv2.cornerSubPix(gray2, corners2, (11, 11), (-1, -1), criteria)
                
                objpoints.append(objp)
                imgpoints_1.append(corners1)
                imgpoints_2.append(corners2)
                valid_pairs += 1
        
        if valid_pairs < 10:
            raise ValueError(f"Need at least 10 valid image pairs, found {valid_pairs}")
        
        logger.info(f"Found {valid_pairs} valid checkerboard pairs")
        
        # Perform stereo calibration
        reprojection_error, K1, D1, K2, D2, R, T, E, F = cv2.stereoCalibrate(
            objpoints, imgpoints_1, imgpoints_2,
            calib_1.camera_matrix, calib_1.distortion_coeffs,
            calib_2.camera_matrix, calib_2.distortion_coeffs,
            images_1[0].shape[::-1][:2],
            flags=cv2.CALIB_FIX_INTRINSIC,
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
        )
        
        if reprojection_error is None or reprojection_error < 0:
            raise RuntimeError("Stereo calibration failed")
        
        # Update camera calibrations with refined parameters
        calib_1.camera_matrix = K1
        calib_1.distortion_coeffs = D1
        calib_2.camera_matrix = K2
        calib_2.distortion_coeffs = D2
        
        # Create stereo calibration
        stereo = StereoCalibration(camera_id_1, camera_id_2)
        stereo.R = R
        stereo.T = T
        stereo.E = E
        stereo.F = F
        stereo.reprojection_error = float(reprojection_error)
        
        key = (camera_id_1, camera_id_2)
        self.stereo_calibrations[key] = stereo
        
        logger.info(f"Stereo calibration successful! Reprojection error: {reprojection_error:.4f}")
        logger.info(f"Translation: [{T[0,0]:.4f}, {T[1,0]:.4f}, {T[2,0]:.4f}]")
        
        return stereo
    
    def save_calibration(self, camera_id: str):
        """Save camera calibration to file"""
        if camera_id not in self.camera_calibrations:
            raise ValueError(f"Camera {camera_id} not calibrated")
        
        calib = self.camera_calibrations[camera_id]
        filepath = self.calibration_path / f"{camera_id}_calibration.json"
        
        with open(filepath, 'w') as f:
            json.dump(calib.to_dict(), f, indent=2)
        
        logger.info(f"Saved calibration for {camera_id} to {filepath}")
    
    def load_calibration(self, camera_id: str) -> CameraCalibration:
        """Load camera calibration from file"""
        filepath = self.calibration_path / f"{camera_id}_calibration.json"
        
        if not filepath.exists():
            raise FileNotFoundError(f"Calibration file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        calib = CameraCalibration.from_dict(data)
        self.camera_calibrations[camera_id] = calib
        
        logger.info(f"Loaded calibration for {camera_id} from {filepath}")
        return calib
    
    def save_stereo_calibration(self, camera_id_1: str, camera_id_2: str):
        """Save stereo calibration to file"""
        key = (camera_id_1, camera_id_2)
        if key not in self.stereo_calibrations:
            raise ValueError(f"Stereo calibration not found for {camera_id_1} and {camera_id_2}")
        
        stereo = self.stereo_calibrations[key]
        filepath = self.calibration_path / f"stereo_{camera_id_1}_{camera_id_2}.json"
        
        with open(filepath, 'w') as f:
            json.dump(stereo.to_dict(), f, indent=2)
        
        logger.info(f"Saved stereo calibration to {filepath}")
    
    def load_stereo_calibration(self, camera_id_1: str, camera_id_2: str) -> StereoCalibration:
        """Load stereo calibration from file"""
        filepath = self.calibration_path / f"stereo_{camera_id_1}_{camera_id_2}.json"
        
        if not filepath.exists():
            raise FileNotFoundError(f"Stereo calibration file not found: {filepath}")
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        stereo = StereoCalibration.from_dict(data)
        key = (camera_id_1, camera_id_2)
        self.stereo_calibrations[key] = stereo
        
        logger.info(f"Loaded stereo calibration from {filepath}")
        return stereo
    
    def get_calibration(self, camera_id: str) -> Optional[CameraCalibration]:
        """Get calibration for a camera"""
        return self.camera_calibrations.get(camera_id)
    
    def get_stereo_calibration(self, camera_id_1: str, camera_id_2: str) -> Optional[StereoCalibration]:
        """Get stereo calibration between two cameras"""
        key = (camera_id_1, camera_id_2)
        return self.stereo_calibrations.get(key)
    
    def transform_point_cloud(self, points: np.ndarray, from_camera: str, to_camera: str) -> np.ndarray:
        """
        Transform point cloud from one camera coordinate system to another
        
        Args:
            points: Nx3 array of 3D points
            from_camera: Source camera ID
            to_camera: Target camera ID
        
        Returns:
            Transformed Nx3 array of 3D points
        """
        if from_camera == to_camera:
            return points
        
        # Get stereo calibration
        stereo = self.get_stereo_calibration(from_camera, to_camera)
        if stereo is None:
            # Try reverse
            stereo = self.get_stereo_calibration(to_camera, from_camera)
            if stereo is None:
                raise ValueError(f"No stereo calibration found between {from_camera} and {to_camera}")
            # Reverse transformation
            R = stereo.R.T
            T = -R @ stereo.T
        else:
            R = stereo.R
            T = stereo.T
        
        # Transform points: P2 = R @ P1 + T
        points_transformed = (R @ points.T).T + T.T
        
        return points_transformed

