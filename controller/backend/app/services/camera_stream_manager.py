from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from calibration.camera.femto_bolt import FemtoBoltCamera, discover_femto_bolt_cameras


@dataclass
class CameraSnapshot:
    jpeg: bytes | None
    frame_index: int
    timestamp_s: float
    width: int
    height: int


@dataclass
class RawFrameSnapshot:
    camera_id: str
    frame_index: int
    timestamp_s: float
    color: np.ndarray | None
    depth: np.ndarray | None


class CameraStreamManager:
    def __init__(
        self,
        *,
        color_width: int,
        color_height: int,
        depth_width: int,
        depth_height: int,
        fps: int,
        use_depth: bool,
        max_cameras: int,
        camera_tuning: dict[str, int | bool] | None,
    ) -> None:
        self._color_width = color_width
        self._color_height = color_height
        self._depth_width = depth_width
        self._depth_height = depth_height
        self._fps = fps
        self._use_depth = use_depth
        self._max_cameras = max_cameras
        self._camera_tuning = dict(camera_tuning or {})

        self._cameras: list[FemtoBoltCamera] = []
        self._snapshots: dict[str, CameraSnapshot] = {}
        self._raw_snapshots: dict[str, RawFrameSnapshot] = {}
        self._intrinsics: dict[str, np.ndarray] = {}
        self._depth_intrinsics: dict[str, np.ndarray] = {}
        self._depth_to_color: dict[str, np.ndarray] = {}

        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return

        self._cameras = discover_femto_bolt_cameras(
            color_resolution=(self._color_width, self._color_height),
            depth_resolution=(self._depth_width, self._depth_height),
            fps=self._fps,
            max_cameras=self._max_cameras,
            use_depth=self._use_depth,
            allowed_camera_ids=None,
            camera_tuning=self._camera_tuning,
        )

        for camera in self._cameras:
            camera.start()
            intrinsics = camera.get_intrinsics()
            self._intrinsics[camera.camera_id] = np.asarray(intrinsics.camera_matrix, dtype=np.float64)
            depth_intrinsics = camera.get_depth_intrinsics()
            if depth_intrinsics is not None:
                self._depth_intrinsics[camera.camera_id] = np.asarray(depth_intrinsics.camera_matrix, dtype=np.float64)
            depth_to_color = camera.get_depth_to_color_transform()
            if depth_to_color is not None:
                self._depth_to_color[camera.camera_id] = np.asarray(depth_to_color, dtype=np.float64)
            self._snapshots[camera.camera_id] = CameraSnapshot(
                jpeg=None,
                frame_index=0,
                timestamp_s=time.time(),
                width=intrinsics.width,
                height=intrinsics.height,
            )
            self._raw_snapshots[camera.camera_id] = RawFrameSnapshot(
                camera_id=camera.camera_id,
                frame_index=0,
                timestamp_s=time.time(),
                color=None,
                depth=None,
            )

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name="femto-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        for camera in self._cameras:
            camera.stop()
        self._cameras = []

    def _capture_loop(self) -> None:
        sleep_s = max(0.001, 1.0 / max(1, self._fps))
        while self._running:
            for camera in self._cameras:
                with self._capture_lock:
                    frame = camera.get_frame(timeout_ms=200)
                if frame is None:
                    continue
                self._update_raw_snapshot(camera.camera_id, frame)
                if frame.color is None:
                    continue
                self._update_jpeg_snapshot(camera.camera_id, frame.color, frame.frame_index)

            time.sleep(sleep_s)

    def _update_raw_snapshot(self, camera_id: str, frame: object) -> None:
        color = getattr(frame, "color", None)
        depth = getattr(frame, "depth", None)
        frame_index = int(getattr(frame, "frame_index", 0))
        with self._lock:
            self._raw_snapshots[camera_id] = RawFrameSnapshot(
                camera_id=camera_id,
                frame_index=frame_index,
                timestamp_s=time.time(),
                color=None if color is None else color.copy(),
                depth=None if depth is None else depth.copy(),
            )

    def _update_jpeg_snapshot(self, camera_id: str, color_frame: np.ndarray, frame_index: int) -> None:
        success, encoded = cv2.imencode(".jpg", color_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not success:
            return

        height, width = color_frame.shape[:2]
        snapshot = CameraSnapshot(
            jpeg=encoded.tobytes(),
            frame_index=frame_index,
            timestamp_s=time.time(),
            width=int(width),
            height=int(height),
        )
        with self._lock:
            self._snapshots[camera_id] = snapshot

    def camera_ids(self) -> list[str]:
        return [camera.camera_id for camera in self._cameras]

    def capture_raw_frame(
        self,
        camera_id: str,
        timeout_ms: int = 500,
        require_depth: bool = False,
        max_attempts: int = 8,
    ) -> RawFrameSnapshot | None:
        target = next((camera for camera in self._cameras if camera.camera_id == camera_id), None)
        if target is None:
            return None

        attempts = max(1, int(max_attempts))
        for _ in range(attempts):
            with self._capture_lock:
                frame = target.get_frame(timeout_ms=timeout_ms)
            if frame is None:
                continue

            color = None if frame.color is None else frame.color.copy()
            depth = None if frame.depth is None else frame.depth.copy()
            if require_depth and depth is None:
                continue

            return RawFrameSnapshot(
                camera_id=target.camera_id,
                frame_index=frame.frame_index,
                timestamp_s=time.time(),
                color=color,
                depth=depth,
            )

        return None

    def intrinsics(self, camera_id: str) -> np.ndarray | None:
        return self._intrinsics.get(camera_id)

    def depth_intrinsics(self, camera_id: str) -> np.ndarray | None:
        return self._depth_intrinsics.get(camera_id)

    def depth_to_color_transform(self, camera_id: str) -> np.ndarray | None:
        transform = self._depth_to_color.get(camera_id)
        return None if transform is None else transform.copy()

    def get_snapshot(self, camera_id: str) -> CameraSnapshot | None:
        with self._lock:
            return self._snapshots.get(camera_id)

    def get_latest_raw_snapshot(self, camera_id: str, *, require_depth: bool = False) -> RawFrameSnapshot | None:
        with self._lock:
            snapshot = self._raw_snapshots.get(camera_id)
        if snapshot is None:
            return None
        if require_depth and snapshot.depth is None:
            return None
        return snapshot

    def camera_details(self) -> list[dict[str, str | int | bool]]:
        details: list[dict[str, str | int | bool]] = []
        for camera in self._cameras:
            snapshot = self.get_snapshot(camera.camera_id)
            details.append(
                {
                    "camera_id": camera.camera_id,
                    "serial_number": camera.serial_number,
                    "device_name": camera.device_name,
                    "width": snapshot.width if snapshot else self._color_width,
                    "height": snapshot.height if snapshot else self._color_height,
                    "fps": self._fps,
                    "connected": True,
                }
            )
        return details
