from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging

import cv2
import numpy as np

from calibration.camera.base import CameraDevice
from calibration.camera.femto_bolt import discover_femto_bolt_cameras
from calibration.camera.network_api import NetworkApiCamera, NetworkCameraDiscoveryConfig, discover_network_api_cameras

LOGGER = logging.getLogger(__name__)


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
    depth_scale_m: float | None


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
        network_camera: NetworkCameraDiscoveryConfig,
    ) -> None:
        self._color_width = color_width
        self._color_height = color_height
        self._depth_width = depth_width
        self._depth_height = depth_height
        self._fps = fps
        self._use_depth = use_depth
        self._max_cameras = max_cameras
        self._camera_tuning = dict(camera_tuning or {})
        self._network_camera = network_camera

        self._cameras: list[CameraDevice] = []
        self._camera_by_id: dict[str, CameraDevice] = {}
        self._snapshots: dict[str, CameraSnapshot] = {}
        self._raw_snapshots: dict[str, RawFrameSnapshot] = {}
        self._intrinsics: dict[str, np.ndarray] = {}
        self._depth_intrinsics: dict[str, np.ndarray] = {}
        self._depth_to_color: dict[str, np.ndarray] = {}

        self._running = False
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._camera_locks: dict[str, threading.Lock] = {}
        self._failed_camera_ids: set[str] = set()

    def start(self) -> None:
        if self._running:
            return

        self._snapshots.clear()
        self._raw_snapshots.clear()
        self._intrinsics.clear()
        self._depth_intrinsics.clear()
        self._depth_to_color.clear()
        self._failed_camera_ids.clear()
        self._camera_by_id.clear()
        self._camera_locks.clear()

        usb_cameras = discover_femto_bolt_cameras(
            color_resolution=(self._color_width, self._color_height),
            depth_resolution=(self._depth_width, self._depth_height),
            fps=self._fps,
            max_cameras=self._max_cameras,
            use_depth=self._use_depth,
            allowed_camera_ids=None,
            camera_tuning=self._camera_tuning,
        )
        network_cameras = discover_network_api_cameras(
            use_depth=self._use_depth,
            allowed_camera_ids=None,
            discovery_config=self._network_camera,
        )
        self._configure_network_cameras(network_cameras)
        self._cameras = [*usb_cameras, *network_cameras]
        self._camera_by_id = {camera.camera_id: camera for camera in self._cameras}
        self._camera_locks = {camera.camera_id: threading.Lock() for camera in self._cameras}

        started_cameras: list[CameraDevice] = []
        for camera in self._cameras:
            if not self._start_camera_with_retries(camera):
                self._failed_camera_ids.add(camera.camera_id)
                continue
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
                depth_scale_m=None,
            )
            started_cameras.append(camera)

        self._cameras = started_cameras
        self._camera_by_id = {camera.camera_id: camera for camera in self._cameras}
        self._camera_locks = {camera.camera_id: self._camera_locks.get(camera.camera_id, threading.Lock()) for camera in self._cameras}

        self._running = True
        self._threads = {}
        for camera in self._cameras:
            thread = threading.Thread(
                target=self._capture_loop,
                args=(camera,),
                name=f"capture-{camera.camera_id}",
                daemon=True,
            )
            thread.start()
            self._threads[camera.camera_id] = thread

    def stop(self) -> None:
        self._running = False
        for thread in self._threads.values():
            thread.join(timeout=2.0)
        self._threads.clear()

        for camera in self._cameras:
            camera.stop()
        self._cameras = []
        self._camera_by_id.clear()
        self._snapshots.clear()
        self._raw_snapshots.clear()
        self._intrinsics.clear()
        self._depth_intrinsics.clear()
        self._depth_to_color.clear()
        self._failed_camera_ids.clear()
        self._camera_locks.clear()

    def _configure_network_cameras(self, cameras: list[NetworkApiCamera]) -> None:
        for camera in cameras:
            try:
                response = camera.apply_stream_configuration(
                    color_width=self._color_width,
                    color_height=self._color_height,
                    depth_width=self._depth_width,
                    depth_height=self._depth_height,
                    fps=self._fps,
                    align_to_color=False,
                )
                LOGGER.info(
                    "Configured network camera id=%s color=%sx%s depth=%sx%s fps=%s restart_required=%s",
                    camera.camera_id,
                    self._color_width,
                    self._color_height,
                    self._depth_width,
                    self._depth_height,
                    self._fps,
                    bool(response.get("restart_required", False)),
                )
            except Exception as exc:
                LOGGER.warning("Failed to configure network camera %s via HTTP settings: %s", camera.camera_id, exc)

    def configure_network_camera_streams(self, camera_ids: list[str] | None = None) -> dict[str, dict[str, str | bool | int]]:
        selected_ids = set(camera_ids or [])
        results: dict[str, dict[str, str | bool | int]] = {}
        for camera in self._cameras:
            if not isinstance(camera, NetworkApiCamera):
                continue
            if selected_ids and camera.camera_id not in selected_ids:
                continue
            try:
                response = camera.apply_stream_configuration(
                    color_width=self._color_width,
                    color_height=self._color_height,
                    depth_width=self._depth_width,
                    depth_height=self._depth_height,
                    fps=self._fps,
                    align_to_color=False,
                )
                intrinsics = camera.get_intrinsics()
                self._intrinsics[camera.camera_id] = np.asarray(intrinsics.camera_matrix, dtype=np.float64)
                depth_intrinsics = camera.get_depth_intrinsics()
                if depth_intrinsics is not None:
                    self._depth_intrinsics[camera.camera_id] = np.asarray(depth_intrinsics.camera_matrix, dtype=np.float64)
                depth_to_color = camera.get_depth_to_color_transform()
                if depth_to_color is not None:
                    self._depth_to_color[camera.camera_id] = np.asarray(depth_to_color, dtype=np.float64)
                results[camera.camera_id] = {
                    "ok": True,
                    "restart_required": bool(response.get("restart_required", False)),
                    "color_width": int(intrinsics.width),
                    "color_height": int(intrinsics.height),
                    "depth_width": int(depth_intrinsics.width) if depth_intrinsics is not None else self._depth_width,
                    "depth_height": int(depth_intrinsics.height) if depth_intrinsics is not None else self._depth_height,
                    "fps": int(self._fps),
                }
            except Exception as exc:
                results[camera.camera_id] = {
                    "ok": False,
                    "error": str(exc),
                }
        return results

    def _start_camera_with_retries(self, camera: CameraDevice, attempts: int = 3, delay_s: float = 1.0) -> bool:
        for attempt in range(1, max(1, attempts) + 1):
            try:
                camera.start()
                return True
            except Exception as exc:
                LOGGER.warning(
                    "Camera start failed camera=%s attempt=%s/%s error=%s",
                    camera.camera_id,
                    attempt,
                    attempts,
                    exc,
                )
                try:
                    camera.stop()
                except Exception:
                    pass
                if attempt < attempts:
                    time.sleep(delay_s)
        return False

    def _capture_loop(self, camera: CameraDevice) -> None:
        sleep_s = max(0.001, 1.0 / max(1, self._fps))
        while self._running:
            loop_started = time.perf_counter()
            try:
                with self._camera_locks[camera.camera_id]:
                    frame = camera.get_frame(timeout_ms=200)
            except Exception:
                LOGGER.exception("Camera capture loop failed camera=%s", camera.camera_id)
                time.sleep(sleep_s)
                continue

            if frame is not None:
                self._update_raw_snapshot(camera.camera_id, frame)
                if frame.color is not None:
                    self._update_jpeg_snapshot(camera.camera_id, frame.color, frame.frame_index)

            elapsed_s = time.perf_counter() - loop_started
            if elapsed_s < sleep_s:
                time.sleep(sleep_s - elapsed_s)

    def _update_raw_snapshot(self, camera_id: str, frame: object) -> None:
        color = getattr(frame, "color", None)
        depth = getattr(frame, "depth", None)
        depth_scale_m = getattr(frame, "depth_scale_m", None)
        frame_index = int(getattr(frame, "frame_index", 0))
        with self._lock:
            self._raw_snapshots[camera_id] = RawFrameSnapshot(
                camera_id=camera_id,
                frame_index=frame_index,
                timestamp_s=time.time(),
                color=None if color is None else color.copy(),
                depth=None if depth is None else depth.copy(),
                depth_scale_m=None if depth_scale_m is None else float(depth_scale_m),
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
        target = self._camera_by_id.get(camera_id)
        if target is None:
            return None

        attempts = max(1, int(max_attempts))
        for _ in range(attempts):
            with self._camera_locks[camera_id]:
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
                depth_scale_m=None if getattr(frame, "depth_scale_m", None) is None else float(frame.depth_scale_m),
            )

        return None

    def synchronized_raw_snapshots(
        self,
        camera_ids: list[str],
        *,
        require_depth: bool = False,
        max_skew_ms: float = 75.0,
        timeout_ms: int = 1200,
    ) -> dict[str, RawFrameSnapshot]:
        selected = [camera_id for camera_id in camera_ids if camera_id in self._camera_by_id]
        if not selected:
            return {}

        deadline = time.perf_counter() + max(0.05, float(timeout_ms) / 1000.0)
        target_skew_s = max(0.0, float(max_skew_ms) / 1000.0)
        best_batch: dict[str, RawFrameSnapshot] = {}
        best_skew_s = float("inf")

        while time.perf_counter() < deadline:
            with self._lock:
                batch = {
                    camera_id: self._clone_raw_snapshot(self._raw_snapshots.get(camera_id))
                    for camera_id in selected
                }

            if any(snapshot is None for snapshot in batch.values()):
                time.sleep(0.01)
                continue

            snapshots = {camera_id: snapshot for camera_id, snapshot in batch.items() if snapshot is not None}
            if require_depth and any(snapshot.depth is None for snapshot in snapshots.values()):
                time.sleep(0.01)
                continue

            timestamps = [snapshot.timestamp_s for snapshot in snapshots.values()]
            skew_s = max(timestamps) - min(timestamps)
            if skew_s < best_skew_s:
                best_skew_s = skew_s
                best_batch = snapshots
            if skew_s <= target_skew_s:
                return snapshots
            time.sleep(0.01)

        if best_batch:
            return best_batch

        direct_captures: dict[str, RawFrameSnapshot] = {}
        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = {
                executor.submit(
                    self.capture_raw_frame,
                    camera_id,
                    max(100, min(400, timeout_ms // 2)),
                    require_depth,
                    3,
                ): camera_id
                for camera_id in selected
            }
            for future in as_completed(futures):
                camera_id = futures[future]
                snapshot = future.result()
                if snapshot is not None and (not require_depth or snapshot.depth is not None):
                    direct_captures[camera_id] = snapshot

        return direct_captures

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
            snapshot = self._clone_raw_snapshot(self._raw_snapshots.get(camera_id))
        if snapshot is None:
            return None
        if require_depth and snapshot.depth is None:
            return None
        return snapshot

    @staticmethod
    def _clone_raw_snapshot(snapshot: RawFrameSnapshot | None) -> RawFrameSnapshot | None:
        if snapshot is None:
            return None
        return RawFrameSnapshot(
            camera_id=snapshot.camera_id,
            frame_index=int(snapshot.frame_index),
            timestamp_s=float(snapshot.timestamp_s),
            color=None if snapshot.color is None else snapshot.color.copy(),
            depth=None if snapshot.depth is None else snapshot.depth.copy(),
            depth_scale_m=None if snapshot.depth_scale_m is None else float(snapshot.depth_scale_m),
        )

    def camera_details(self) -> list[dict[str, str | int | bool]]:
        details: list[dict[str, str | int | bool]] = []
        for camera in self._cameras:
            snapshot = self.get_snapshot(camera.camera_id)
            details.append(
                {
                    "camera_id": camera.camera_id,
                    "serial_number": camera.serial_number,
                    "device_name": camera.device_name,
                    "connection_type": camera.connection_type,
                    "width": snapshot.width if snapshot else self._color_width,
                    "height": snapshot.height if snapshot else self._color_height,
                    "fps": self._fps,
                    "connected": True,
                }
            )
        return details
