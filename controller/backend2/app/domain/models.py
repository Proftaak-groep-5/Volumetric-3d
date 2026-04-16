from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import base64
import cv2
import numpy as np


@dataclass(slots=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "fx": self.fx,
            "fy": self.fy,
            "cx": self.cx,
            "cy": self.cy,
            "width": self.width,
            "height": self.height,
        }


@dataclass(slots=True)
class CameraFrame:
    camera_id: str
    timestamp: float
    color_data: np.ndarray | None = None
    depth_data: np.ndarray | None = None
    _ws_cache: dict[str, Any] = field(default_factory=dict)

    def to_ws_payload(self, color_quality: int, depth_quality: int) -> dict[str, Any]:
        """Serialize frame to frontend-compatible websocket payload."""
        if self._ws_cache:
            return self._ws_cache

        payload: dict[str, Any] = {
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
        }

        if self.color_data is not None:
            success, color_buf = cv2.imencode(
                ".jpg",
                self.color_data,
                [cv2.IMWRITE_JPEG_QUALITY, color_quality],
            )
            if success:
                payload["color_b64"] = base64.b64encode(color_buf).decode("utf-8")
                payload["color_shape"] = list(self.color_data.shape)

        if self.depth_data is not None:
            depth_max = float(np.max(self.depth_data))
            if depth_max > 0:
                depth_display = cv2.convertScaleAbs(self.depth_data, alpha=255.0 / depth_max)
            else:
                depth_display = np.zeros_like(self.depth_data, dtype=np.uint8)
            success, depth_buf = cv2.imencode(
                ".jpg",
                depth_display,
                [cv2.IMWRITE_JPEG_QUALITY, depth_quality],
            )
            if success:
                payload["depth_b64"] = base64.b64encode(depth_buf).decode("utf-8")
                payload["depth_shape"] = list(self.depth_data.shape)

        self._ws_cache = payload
        return payload


@dataclass(slots=True)
class CameraPose:
    camera_id: str
    t_world_camera: np.ndarray
    t_camera_world: np.ndarray


@dataclass(slots=True)
class StereoTransform:
    camera_id_1: str
    camera_id_2: str
    r: np.ndarray
    t: np.ndarray

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "camera_id_1": self.camera_id_1,
            "camera_id_2": self.camera_id_2,
            "R": self.r.tolist(),
            "T": self.t.tolist(),
        }


@dataclass(slots=True)
class RecordingMetadata:
    session_id: str
    start_time: str
    camera_ids: list[str]
    camera_count: int
    fps: int
    status: str
    total_frames: int = 0
    end_time: str | None = None
    duration_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "camera_ids": self.camera_ids,
            "camera_count": self.camera_count,
            "fps": self.fps,
            "status": self.status,
            "total_frames": self.total_frames,
        }
        if self.end_time is not None:
            payload["end_time"] = self.end_time
        if self.duration_seconds is not None:
            payload["duration_seconds"] = self.duration_seconds
        return payload


@dataclass(slots=True)
class RecordingSession:
    session_id: str
    session_path: Path
    camera_ids: list[str]
    fps: int
    started_at_epoch: float
    metadata: RecordingMetadata
    frame_counts_by_camera: dict[str, int]

    @classmethod
    def create(cls, session_path: Path, camera_ids: list[str], fps: int, started_at_epoch: float) -> "RecordingSession":
        session_id = session_path.name
        metadata = RecordingMetadata(
            session_id=session_id,
            start_time=datetime.fromtimestamp(started_at_epoch).isoformat(),
            camera_ids=camera_ids,
            camera_count=len(camera_ids),
            fps=fps,
            status="recording",
        )
        return cls(
            session_id=session_id,
            session_path=session_path,
            camera_ids=camera_ids,
            fps=fps,
            started_at_epoch=started_at_epoch,
            metadata=metadata,
            frame_counts_by_camera=dict.fromkeys(camera_ids, 0),
        )
