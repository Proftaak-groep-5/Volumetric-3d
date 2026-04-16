from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from app.domain.models import CameraFrame, CameraIntrinsics, RecordingSession
from app.services.reconstruction_service import depth_color_to_pointcloud, write_ply_ascii


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _QueuedFrame:
    camera_id: str
    timestamp: float
    depth_data: np.ndarray | None
    color_data: np.ndarray | None


class RecordingService:
    """Asynchronous recording pipeline with a dedicated frame writer thread."""

    def __init__(
        self,
        recordings_path: Path,
        fps: int,
        pointcloud_stride: int,
        pointcloud_max_depth_m: float,
    ) -> None:
        self._recordings_path = recordings_path
        self._recordings_path.mkdir(parents=True, exist_ok=True)

        self._fps = fps
        self._pointcloud_stride = pointcloud_stride
        self._pointcloud_max_depth_m = pointcloud_max_depth_m

        self._lock = threading.RLock()
        self._session: RecordingSession | None = None
        self._queue: queue.Queue[_QueuedFrame | None] | None = None
        self._writer_thread: threading.Thread | None = None

        self._timestamps: dict[str, list[float]] = {}
        self._depth_frames: dict[str, list[np.ndarray]] = {}
        self._color_frames: dict[str, list[np.ndarray]] = {}
        self._total_frames = 0

    @property
    def recordings_path(self) -> Path:
        return self._recordings_path

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._session is not None

    def start(self, camera_ids: list[str]) -> str:
        with self._lock:
            if self._session is not None:
                raise RuntimeError("Already recording")

            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_path = self._recordings_path / session_id
            session_path.mkdir(parents=True, exist_ok=True)

            started_at = time.time()
            self._session = RecordingSession.create(
                session_path=session_path,
                camera_ids=list(camera_ids),
                fps=self._fps,
                started_at_epoch=started_at,
            )

            self._timestamps = {camera_id: [] for camera_id in camera_ids}
            self._depth_frames = {camera_id: [] for camera_id in camera_ids}
            self._color_frames = {camera_id: [] for camera_id in camera_ids}
            self._total_frames = 0

            self._queue = queue.Queue(maxsize=500)
            self._writer_thread = threading.Thread(target=self._writer_loop, name="recording-writer", daemon=True)
            self._writer_thread.start()

            logger.info("Recording session started: %s", session_id)
            return session_id

    def record_frame(self, frame: CameraFrame) -> None:
        with self._lock:
            if self._session is None or self._queue is None:
                return

            frame_payload = _QueuedFrame(
                camera_id=frame.camera_id,
                timestamp=frame.timestamp,
                depth_data=frame.depth_data,
                color_data=frame.color_data,
            )

            try:
                self._queue.put_nowait(frame_payload)
            except queue.Full:
                logger.warning("Recording queue full; dropping frame from %s", frame.camera_id)

    def stop(self, intrinsics_by_camera: dict[str, CameraIntrinsics]) -> dict:
        with self._lock:
            if self._session is None:
                raise RuntimeError("Not currently recording")

            queue_ref = self._queue
            writer_ref = self._writer_thread
            session = self._session

            self._session = None
            self._queue = None
            self._writer_thread = None

        if queue_ref is not None:
            queue_ref.put(None)
        if writer_ref is not None:
            writer_ref.join(timeout=10.0)

        metadata = self._finalize_session(session, intrinsics_by_camera)
        logger.info("Recording session stopped: %s", session.session_id)
        return metadata

    def status(self) -> dict:
        with self._lock:
            if self._session is None:
                return {"is_recording": False}

            return {
                "is_recording": True,
                "session_id": self._session.session_id,
                "frame_count": self._total_frames,
                "duration": time.time() - self._session.started_at_epoch,
            }

    def _writer_loop(self) -> None:
        queue_ref = self._queue
        if queue_ref is None:
            return

        while True:
            item = queue_ref.get()
            if item is None:
                queue_ref.task_done()
                break

            with self._lock:
                camera_id = item.camera_id
                if camera_id not in self._timestamps:
                    queue_ref.task_done()
                    continue

                self._timestamps[camera_id].append(item.timestamp)
                if item.depth_data is not None:
                    self._depth_frames[camera_id].append(item.depth_data)
                if item.color_data is not None:
                    self._color_frames[camera_id].append(item.color_data)

                self._total_frames += 1
                if self._session is not None:
                    self._session.frame_counts_by_camera[camera_id] += 1

            queue_ref.task_done()

    def _update_session_metadata(self, session: RecordingSession) -> None:
        end_time = time.time()
        duration = end_time - session.started_at_epoch

        session.metadata.end_time = datetime.fromtimestamp(end_time).isoformat()
        session.metadata.duration_seconds = duration
        session.metadata.status = "completed"
        session.metadata.total_frames = self._total_frames

    def _build_save_dict(self, camera_id: str) -> tuple[dict[str, np.ndarray], list[np.ndarray], list[np.ndarray]]:
        save_dict: dict[str, np.ndarray] = {
            "timestamps": np.asarray(self._timestamps.get(camera_id, []), dtype=np.float64),
        }

        depth_frames = self._depth_frames.get(camera_id, [])
        color_frames = self._color_frames.get(camera_id, [])

        if depth_frames:
            save_dict["depth_frames"] = np.stack(depth_frames, axis=0)
            save_dict["depth_shape"] = np.asarray(depth_frames[0].shape, dtype=np.int32)
        if color_frames:
            save_dict["color_frames"] = np.stack(color_frames, axis=0)
            save_dict["color_shape"] = np.asarray(color_frames[0].shape, dtype=np.int32)

        return save_dict, depth_frames, color_frames

    def _export_sample_pointcloud(
        self,
        session: RecordingSession,
        camera_id: str,
        depth_frames: list[np.ndarray],
        color_frames: list[np.ndarray],
        intrinsics: CameraIntrinsics | None,
    ) -> None:
        if not depth_frames or not color_frames or intrinsics is None:
            return

        try:
            points, colors = depth_color_to_pointcloud(
                depth_frames[0],
                color_frames[0],
                intrinsics,
                stride=self._pointcloud_stride,
                max_depth_m=self._pointcloud_max_depth_m,
            )
            if len(points) > 0:
                ply_path = session.session_path / f"{camera_id}_sample.ply"
                write_ply_ascii(ply_path, points, colors)
        except Exception as exc:
            logger.warning("Failed to export sample point cloud for %s: %s", camera_id, exc)

    def _clear_recording_buffers(self) -> None:
        with self._lock:
            self._timestamps = {}
            self._depth_frames = {}
            self._color_frames = {}
            self._total_frames = 0

    def _finalize_session(self, session: RecordingSession, intrinsics_by_camera: dict[str, CameraIntrinsics]) -> dict:
        self._update_session_metadata(session)

        meta_path = session.session_path / "meta.json"
        with meta_path.open("w", encoding="utf-8") as fh:
            json.dump(session.metadata.as_dict(), fh, indent=2)

        for camera_id in session.camera_ids:
            save_dict, depth_frames, color_frames = self._build_save_dict(camera_id)

            npz_path = session.session_path / f"{camera_id}_frames.npz"
            np.savez_compressed(npz_path, **save_dict)

            self._export_sample_pointcloud(
                session,
                camera_id,
                depth_frames,
                color_frames,
                intrinsics_by_camera.get(camera_id),
            )

        metadata = session.metadata.as_dict()
        self._clear_recording_buffers()

        return metadata
