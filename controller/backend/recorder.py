"""
Recording Manager
Handles recording of multi-camera 3D data to disk
"""
import numpy as np
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging
from camera_manager import CameraFrame

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecordingSession:
    """Manages a single recording session"""
    
    def __init__(self, session_path: Path, camera_ids: List[str]):
        self.session_path = session_path
        self.camera_ids = camera_ids
        self.start_time = time.time()
        self.frames: Dict[str, List[Dict]] = {cam_id: [] for cam_id in camera_ids}
        self.frame_count = 0
        
        # Create session directory
        self.session_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize metadata
        self.metadata = {
            "session_id": session_path.name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "camera_ids": camera_ids,
            "camera_count": len(camera_ids),
            "fps": 30,  # Target FPS
            "status": "recording"
        }
        
        logger.info(f"Recording session started: {session_path.name}")
    
    def add_frame(self, frame: CameraFrame):
        """Add a frame to the recording"""
        frame_data = {
            "timestamp": frame.timestamp,
            "frame_index": self.frame_count,
        }
        
        # Store raw numpy arrays (will be saved to .npz)
        if frame.depth_data is not None:
            frame_data["depth"] = frame.depth_data
            frame_data["depth_shape"] = frame.depth_data.shape
        
        if frame.color_data is not None:
            frame_data["color"] = frame.color_data
            frame_data["color_shape"] = frame.color_data.shape
        
        self.frames[frame.camera_id].append(frame_data)
        self.frame_count += 1
    
    def finalize(self) -> Dict:
        """Finalize the recording and save to disk"""
        end_time = time.time()
        duration = end_time - self.start_time
        
        # Update metadata
        self.metadata.update({
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": duration,
            "total_frames": self.frame_count,
            "status": "completed"
        })
        
        # Save metadata
        meta_path = self.session_path / "meta.json"
        with open(meta_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        
        logger.info(f"Saved metadata to {meta_path}")
        
        # Save frames for each camera as separate .npz files
        for camera_id, frames in self.frames.items():
            if not frames:
                continue
            
            # Prepare arrays for saving
            save_dict = {
                "timestamps": np.array([f["timestamp"] for f in frames]),
                "frame_indices": np.array([f["frame_index"] for f in frames]),
            }
            
            # Stack depth frames
            depth_frames = [f["depth"] for f in frames if "depth" in f]
            if depth_frames:
                save_dict["depth_frames"] = np.stack(depth_frames)
                save_dict["depth_shape"] = depth_frames[0].shape
            
            # Stack color frames
            color_frames = [f["color"] for f in frames if "color" in f]
            if color_frames:
                save_dict["color_frames"] = np.stack(color_frames)
                save_dict["color_shape"] = color_frames[0].shape
            
            # Save to compressed npz
            npz_path = self.session_path / f"{camera_id}_frames.npz"
            np.savez_compressed(npz_path, **save_dict)
            
            logger.info(f"Saved {len(frames)} frames for {camera_id} to {npz_path}")
        
        # Also save a combined point cloud sample (first frame)
        self._save_sample_pointcloud()
        
        logger.info(f"Recording finalized: {self.frame_count} frames, {duration:.2f}s")
        return self.metadata
    
    def _save_sample_pointcloud(self):
        """Save a sample point cloud from the first frame"""
        try:
            # Get first frame from first camera
            for camera_id, frames in self.frames.items():
                if frames and "depth" in frames[0] and "color" in frames[0]:
                    depth = frames[0]["depth"]
                    color = frames[0]["color"]
                    
                    # Point cloud generation using calibration if available
                    h, w = depth.shape
                    
                    # Try to get calibration from camera manager (if available)
                    fx = fy = w * 0.6  # Default estimate
                    cx, cy = w / 2, h / 2
                    
                    # Note: In a full implementation, you would pass calibration_manager
                    # and get proper intrinsics here. For now, use reasonable defaults.
                    
                    # Create point cloud
                    points = []
                    colors = []
                    
                    for v in range(0, h, 2):  # Subsample for efficiency
                        for u in range(0, w, 2):
                            z = depth[v, u] / 1000.0  # Convert mm to meters
                            if z > 0 and z < 5:  # Valid depth range
                                x = (u - cx) * z / fx
                                y = (v - cy) * z / fy
                                points.append([x, y, z])
                                
                                # Get color (handle different color formats)
                                if len(color.shape) == 3 and color.shape[2] >= 3:
                                    colors.append(color[v, u, :3])
                                else:
                                    colors.append([128, 128, 128])
                    
                    # Save as .ply
                    ply_path = self.session_path / f"{camera_id}_sample.ply"
                    self._write_ply(ply_path, np.array(points), np.array(colors))
                    logger.info(f"Saved sample point cloud to {ply_path}")
                    break
        except Exception as e:
            logger.warning(f"Could not save sample point cloud: {e}")
    
    def _write_ply(self, filepath: Path, points: np.ndarray, colors: np.ndarray):
        """Write point cloud to PLY file"""
        with open(filepath, 'w') as f:
            # Header
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write(f"element vertex {len(points)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write("property uchar red\n")
            f.write("property uchar green\n")
            f.write("property uchar blue\n")
            f.write("end_header\n")
            
            # Data
            for point, color in zip(points, colors):
                f.write(f"{point[0]} {point[1]} {point[2]} ")
                f.write(f"{int(color[0])} {int(color[1])} {int(color[2])}\n")


class RecordingManager:
    """Manages recording sessions"""
    
    def __init__(self, recordings_path: Path):
        self.recordings_path = recordings_path
        self.current_session: Optional[RecordingSession] = None
        self.is_recording = False
        
        # Ensure recordings directory exists
        self.recordings_path.mkdir(parents=True, exist_ok=True)
    
    def start_recording(self, camera_ids: List[str]) -> str:
        """Start a new recording session"""
        if self.is_recording:
            raise RuntimeError("Already recording")
        
        # Create session directory with timestamp
        session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = self.recordings_path / session_name
        
        self.current_session = RecordingSession(session_path, camera_ids)
        self.is_recording = True
        
        return session_name
    
    def record_frame(self, frame: CameraFrame):
        """Record a frame"""
        if not self.is_recording or not self.current_session:
            return
        
        self.current_session.add_frame(frame)
    
    def stop_recording(self) -> Optional[Dict]:
        """Stop the current recording session"""
        if not self.is_recording or not self.current_session:
            return None
        
        metadata = self.current_session.finalize()
        self.is_recording = False
        self.current_session = None
        
        return metadata
    
    def get_status(self) -> Dict:
        """Get current recording status"""
        if self.is_recording and self.current_session:
            return {
                "is_recording": True,
                "session_id": self.current_session.session_path.name,
                "frame_count": self.current_session.frame_count,
                "duration": time.time() - self.current_session.start_time
            }
        return {
            "is_recording": False
        }

