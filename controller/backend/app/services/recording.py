from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager, RawFrameSnapshot
from app.services.volumetric_capture import VolumetricCaptureService

LOGGER = logging.getLogger(__name__)

DEFAULT_RECORDING_DEPTH_MIN_M = 0.15
DEFAULT_RECORDING_DEPTH_MAX_M = 5.0
DEFAULT_RECORDING_SINGLE_CAMERA_WORKERS = 1
DEFAULT_RECORDING_SINGLE_CAMERA_MAX_PENDING = 1


@dataclass
class RecordingStatusSnapshot:
    running: bool
    can_start: bool
    disable_reasons: list[str]
    calibration_file: str
    calibration_file_exists: bool
    selected_output_dir: str | None
    output_dir_empty: bool | None
    active_output_dir: str | None
    start_unix_seconds: int | None
    started_at_utc: str | None
    stopped_at_utc: str | None
    target_fps: int | None
    frames_written: int
    failed_frames: int
    last_error: str | None
    camera_ids: list[str]


class RecordingService:
    def __init__(
        self,
        capture_service: VolumetricCaptureService,
        camera_manager: CameraStreamManager,
        calibration_store: CalibrationStore,
    ) -> None:
        self._capture_service = capture_service
        self._camera_manager = camera_manager
        self._calibration_store = calibration_store
        self._lock = threading.Lock()
        self._single_camera_workers = min(
            32,
            max(1, int(os.getenv("RECORDING_SINGLE_CAMERA_WORKERS", str(DEFAULT_RECORDING_SINGLE_CAMERA_WORKERS)))),
        )
        self._single_camera_max_pending = min(
            32,
            max(1, int(os.getenv("RECORDING_SINGLE_CAMERA_MAX_PENDING", str(DEFAULT_RECORDING_SINGLE_CAMERA_MAX_PENDING)))),
        )
        self._multi_camera_workers = min(16, max(1, int(os.getenv("RECORDING_MULTI_CAMERA_WORKERS", "8"))))

        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._producer_threads: dict[str, threading.Thread] = {}
        self._latest_frames: dict[str, RawFrameSnapshot] = {}
        self._frame_store_lock = threading.Lock()
        self._all_frames_ready_event = threading.Event()

        self._active_output_dir: Path | None = None
        self._start_unix_seconds: int | None = None
        self._start_monotonic_seconds: float | None = None
        self._started_at_utc: str | None = None
        self._stopped_at_utc: str | None = None
        self._target_fps: int | None = None
        self._camera_ids: list[str] = []
        self._frames_written = 0
        self._failed_frames = 0
        self._frame_index = 0
        self._last_error: str | None = None

    def status(self, selected_output_dir: str | None = None) -> RecordingStatusSnapshot:
        with self._lock:
            running = self._running
            active_output_dir = str(self._active_output_dir) if self._active_output_dir is not None else None
            start_unix_seconds = self._start_unix_seconds
            started_at_utc = self._started_at_utc
            stopped_at_utc = self._stopped_at_utc
            target_fps = self._target_fps
            frames_written = self._frames_written
            failed_frames = self._failed_frames
            last_error = self._last_error
            camera_ids = list(self._camera_ids)

        selected_output_dir_for_check = selected_output_dir
        if selected_output_dir_for_check is None and active_output_dir is not None:
            selected_output_dir_for_check = active_output_dir

        can_start, disable_reasons, calibration_file_exists, output_dir_empty, selected_output_dir_resolved = (
            self._evaluate_start_requirements(selected_output_dir_for_check, include_running_check=True)
        )

        return RecordingStatusSnapshot(
            running=running,
            can_start=can_start and not running,
            disable_reasons=disable_reasons,
            calibration_file=str(self._calibration_store.calibration_file),
            calibration_file_exists=calibration_file_exists,
            selected_output_dir=selected_output_dir_resolved,
            output_dir_empty=output_dir_empty,
            active_output_dir=active_output_dir,
            start_unix_seconds=start_unix_seconds,
            started_at_utc=started_at_utc,
            stopped_at_utc=stopped_at_utc,
            target_fps=target_fps,
            frames_written=frames_written,
            failed_frames=failed_frames,
            last_error=last_error,
            camera_ids=camera_ids,
        )

    def start(
        self,
        *,
        output_dir: str,
        camera_ids: list[str] | None = None,
        depth_min_m: float | None = None,
        depth_max_m: float | None = None,
    ) -> RecordingStatusSnapshot:
        with self._lock:
            if self._running:
                raise RuntimeError("Recording is already running")

        can_start, disable_reasons, _, _, selected_output_dir = self._evaluate_start_requirements(
            output_dir,
            include_running_check=False,
            camera_ids=camera_ids,
        )
        if not can_start:
            raise ValueError("; ".join(disable_reasons))
        if selected_output_dir is None:
            raise ValueError("Output folder is required")
        resolved_depth_min_m = (
            DEFAULT_RECORDING_DEPTH_MIN_M
            if depth_min_m is None
            else float(depth_min_m)
        )
        resolved_depth_max_m = (
            DEFAULT_RECORDING_DEPTH_MAX_M
            if depth_max_m is None
            else float(depth_max_m)
        )
        if resolved_depth_min_m <= 0.0:
            raise ValueError("depth_min_m must be > 0")
        if resolved_depth_max_m <= resolved_depth_min_m:
            raise ValueError("depth_max_m must be greater than depth_min_m")

        output_path = Path(selected_output_dir)
        selected_camera_ids = camera_ids or self._camera_manager.camera_ids()
        selected_camera_ids = sorted(set(selected_camera_ids))
        self._run_preflight_depth_check(camera_ids=selected_camera_ids)
        base_target_fps = max(1, min(int(self._camera_manager.target_fps()), int(os.getenv("RECORDING_TARGET_FPS", "30"))))
        if len(selected_camera_ids) >= 5:
            target_fps = min(base_target_fps, max(1, int(os.getenv("RECORDING_TARGET_FPS_FIVE_PLUS", "15"))))
        else:
            target_fps = base_target_fps
        start_unix_seconds = int(time.time())
        started_at_utc = datetime.now(tz=timezone.utc).isoformat()
        stop_event = threading.Event()

        with self._lock:
            if self._running:
                raise RuntimeError("Recording is already running")

            self._camera_manager.set_network_preview_enabled(False)
            self._running = True
            self._thread = threading.Thread(
                target=self._record_loop,
                kwargs={
                    "stop_event": stop_event,
                    "output_dir": output_path,
                    "camera_ids": selected_camera_ids,
                    "depth_min_m": resolved_depth_min_m,
                    "depth_max_m": resolved_depth_max_m,
                    "target_fps": target_fps,
                },
                daemon=True,
                name="recording-loop",
            )
            self._stop_event = stop_event
            self._active_output_dir = output_path
            self._start_unix_seconds = start_unix_seconds
            self._start_monotonic_seconds = time.monotonic()
            self._started_at_utc = started_at_utc
            self._stopped_at_utc = None
            self._target_fps = target_fps
            self._camera_ids = selected_camera_ids
            self._frames_written = 0
            self._failed_frames = 0
            self._frame_index = 0
            self._last_error = None
            self._latest_frames = {}
            self._all_frames_ready_event.clear()
            worker = self._thread

        try:
            self._start_frame_producers(
                camera_ids=selected_camera_ids,
                stop_event=stop_event,
                target_fps=target_fps,
            )
            worker.start()
        except Exception:
            self._stop_frame_producers(stop_event)
            with self._lock:
                self._camera_manager.set_network_preview_enabled(True)
                self._running = False
                self._thread = None
                self._stop_event = None
                self._active_output_dir = None
                self._start_unix_seconds = None
                self._start_monotonic_seconds = None
                self._started_at_utc = None
                self._stopped_at_utc = datetime.now(tz=timezone.utc).isoformat()
                self._target_fps = None
                self._camera_ids = []
                self._producer_threads = {}
                self._latest_frames = {}
                self._all_frames_ready_event.clear()
            raise

        return self.status(selected_output_dir=selected_output_dir)

    def stop(self, timeout_seconds: float = 10.0) -> RecordingStatusSnapshot:
        with self._lock:
            if not self._running or self._stop_event is None:
                raise RuntimeError("Recording is not running")
            stop_event = self._stop_event
            worker = self._thread
            selected_output_dir = str(self._active_output_dir) if self._active_output_dir is not None else None

        stop_event.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout=max(0.5, float(timeout_seconds)))

        if worker is not None and worker.is_alive():
            raise RuntimeError("Timed out while stopping recording")

        return self.status(selected_output_dir=selected_output_dir)

    def shutdown(self) -> None:
        with self._lock:
            running = self._running and self._stop_event is not None
        if running:
            try:
                self.stop(timeout_seconds=3.0)
            except Exception:
                LOGGER.exception("Failed to stop recording service cleanly")

    def _record_loop(
        self,
        *,
        stop_event: threading.Event,
        output_dir: Path,
        camera_ids: list[str],
        depth_min_m: float,
        depth_max_m: float,
        target_fps: int,
    ) -> None:
        frame_interval_seconds = 1.0 / max(1, int(target_fps))
        next_capture_monotonic = time.monotonic()
        single_camera_mode = len(camera_ids) <= 1
        worker_count = (
            self._single_camera_workers
            if single_camera_mode
            else max(2, min(self._multi_camera_workers, len(camera_ids) + 2))
        )
        if single_camera_mode:
            default_single_camera_pending = max(4, worker_count * 2)
            max_pending = min(
                24,
                max(1, min(self._single_camera_max_pending, default_single_camera_pending)),
            )
        else:
            max_pending = min(24, max(4, worker_count * 2))
        pending: set[Future[tuple[bool, str | None]]] = set()

        # Wait briefly for first full-frame set so early captures do not fail.
        self._all_frames_ready_event.wait(timeout=3.0)

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="recording-frame") as executor:
            while not stop_event.is_set():
                self._collect_completed_futures(pending)
                now_monotonic = time.monotonic()

                if now_monotonic < next_capture_monotonic:
                    wait_seconds = min(0.01, max(0.0, next_capture_monotonic - now_monotonic))
                    stop_event.wait(wait_seconds)
                    continue

                if len(pending) >= max_pending:
                    stop_event.wait(0.001)
                    continue

                with self._lock:
                    start_unix_seconds = self._start_unix_seconds
                    start_monotonic_seconds = self._start_monotonic_seconds
                    frame_index = self._frame_index
                    self._frame_index += 1

                if start_unix_seconds is None or start_monotonic_seconds is None:
                    break

                elapsed_seconds = max(0, int(now_monotonic - start_monotonic_seconds))
                second_dir = output_dir / f"{start_unix_seconds}_{elapsed_seconds}"
                file_stem = f"frame_{frame_index:06d}"
                frames_by_camera = self._snapshot_latest_frames(camera_ids)
                if len(frames_by_camera) < len(camera_ids):
                    stop_event.wait(0.001)
                    continue
                pending.add(
                    executor.submit(
                        self._capture_and_write_frame,
                        camera_ids=camera_ids,
                        frames_by_camera=frames_by_camera,
                        depth_min_m=depth_min_m,
                        depth_max_m=depth_max_m,
                        output_dir=second_dir,
                        file_stem=file_stem,
                    )
                )

                next_capture_monotonic += frame_interval_seconds
                if next_capture_monotonic < now_monotonic - frame_interval_seconds:
                    next_capture_monotonic = now_monotonic + frame_interval_seconds

            while pending:
                self._collect_completed_futures(pending, wait_for_one=True)

        self._stop_frame_producers(stop_event)
        self._prune_empty_subdirs(output_dir)
        with self._lock:
            self._running = False
            self._thread = None
            self._stop_event = None
            self._start_monotonic_seconds = None
            self._stopped_at_utc = datetime.now(tz=timezone.utc).isoformat()
            self._target_fps = None
            self._camera_ids = []
            self._active_output_dir = None
            self._start_unix_seconds = None
            self._producer_threads = {}
            self._latest_frames = {}
            self._all_frames_ready_event.clear()
            self._camera_manager.set_network_preview_enabled(True)

    def _capture_and_write_frame(
        self,
        *,
        camera_ids: list[str],
        frames_by_camera: dict[str, RawFrameSnapshot],
        depth_min_m: float,
        depth_max_m: float,
        output_dir: Path,
        file_stem: str,
    ) -> tuple[bool, str | None]:
        try:
            self._capture_service.capture_once(
                camera_ids=camera_ids,
                frames_by_camera=frames_by_camera,
                pixel_step=1,
                depth_min_m=depth_min_m,
                depth_max_m=depth_max_m,
                output_dir=output_dir,
                file_stem=file_stem,
                write_preview=False,
                ply_binary=True,
                use_synchronized_snapshots=False,
                allow_direct_capture_fallback=False,
                apply_brightness_balance=False,
                voxel_size_m=None,
                parallel_camera_processing=True,
                sample_projected_color=True,
                direct_capture_prefer_depth_only=False,
                write_color=True,
                min_required_cameras=len(camera_ids),
            )
            return True, None
        except Exception as exc:
            return False, str(exc)

    def _collect_completed_futures(
        self,
        pending: set[Future[tuple[bool, str | None]]],
        *,
        wait_for_one: bool = False,
    ) -> None:
        if not pending:
            return
        done: list[Future[tuple[bool, str | None]]] = [future for future in pending if future.done()]
        if not done and wait_for_one:
            done = [next(iter(pending))]
            done[0].result()

        for future in done:
            pending.discard(future)
            success, error = future.result()
            with self._lock:
                if success:
                    self._frames_written += 1
                else:
                    self._failed_frames += 1
                    self._last_error = error

    def _start_frame_producers(
        self,
        *,
        camera_ids: list[str],
        stop_event: threading.Event,
        target_fps: int,
    ) -> None:
        capture_timeout_ms = max(20, int((1000.0 / max(1, int(target_fps))) * 1.2))
        producer_threads: dict[str, threading.Thread] = {}

        for camera_id in camera_ids:
            producer = threading.Thread(
                target=self._frame_producer_loop,
                kwargs={
                    "camera_id": camera_id,
                    "stop_event": stop_event,
                    "capture_timeout_ms": capture_timeout_ms,
                    "camera_count": len(camera_ids),
                },
                daemon=True,
                name=f"recording-producer-{camera_id}",
            )
            producer.start()
            producer_threads[camera_id] = producer

        self._producer_threads = producer_threads

    def _stop_frame_producers(self, stop_event: threading.Event) -> None:
        stop_event.set()
        for producer in list(self._producer_threads.values()):
            if producer.is_alive():
                producer.join(timeout=1.0)

    def _frame_producer_loop(
        self,
        *,
        camera_id: str,
        stop_event: threading.Event,
        capture_timeout_ms: int,
        camera_count: int,
    ) -> None:
        while not stop_event.is_set():
            try:
                frame = self._camera_manager.capture_raw_frame(
                    camera_id,
                    require_depth=True,
                    timeout_ms=max(20, int(capture_timeout_ms)),
                    max_attempts=1,
                    prefer_depth_only=False,
                )
            except Exception as exc:
                with self._lock:
                    self._last_error = f"{camera_id}: producer capture failed: {exc}"
                stop_event.wait(0.001)
                continue

            if frame is None or frame.depth is None or frame.color is None:
                stop_event.wait(0.001)
                continue

            with self._frame_store_lock:
                self._latest_frames[camera_id] = frame
                if len(self._latest_frames) >= camera_count:
                    self._all_frames_ready_event.set()

    def _snapshot_latest_frames(self, camera_ids: list[str]) -> dict[str, RawFrameSnapshot]:
        with self._frame_store_lock:
            return {
                camera_id: frame
                for camera_id in camera_ids
                if (frame := self._latest_frames.get(camera_id)) is not None
            }

    def _evaluate_start_requirements(
        self,
        selected_output_dir: str | None,
        *,
        include_running_check: bool,
        camera_ids: list[str] | None = None,
    ) -> tuple[bool, list[str], bool, bool | None, str | None]:
        disable_reasons: list[str] = []

        with self._lock:
            running = self._running
        if include_running_check and running:
            disable_reasons.append("Recording is already running.")

        calibration_file = self._calibration_store.calibration_file
        calibration_file_exists = calibration_file.is_file()
        if not calibration_file_exists:
            disable_reasons.append(f"Calibration file not found: {calibration_file}")
        calibration_camera_ids = set(self._calibration_store.all_camera_ids())
        if calibration_file_exists and len(calibration_camera_ids) < 1:
            disable_reasons.append("Calibration file has no successful camera entries.")

        selected_output_dir_resolved: str | None = None
        output_dir_empty: bool | None = None
        if selected_output_dir is None or not selected_output_dir.strip():
            disable_reasons.append("Select an output folder path.")
        else:
            output_path = Path(selected_output_dir).expanduser().resolve()
            selected_output_dir_resolved = str(output_path)
            if not output_path.exists():
                disable_reasons.append("Selected output folder does not exist.")
            elif not output_path.is_dir():
                disable_reasons.append("Selected output path is not a directory.")
            else:
                output_dir_empty = self._is_directory_empty(output_path)
                if output_dir_empty is False:
                    disable_reasons.append("Selected output folder must be empty.")

        selected_camera_ids = sorted(set(camera_ids or self._camera_manager.camera_ids()))
        if len(selected_camera_ids) < 1:
            disable_reasons.append("No connected cameras available for recording.")
        elif calibration_file_exists and calibration_camera_ids:
            missing_calibration = [camera_id for camera_id in selected_camera_ids if camera_id not in calibration_camera_ids]
            if missing_calibration:
                disable_reasons.append(
                    "Selected camera(s) missing calibration entries: " + ", ".join(missing_calibration)
                )

        can_start = len(disable_reasons) == 0
        return can_start, disable_reasons, calibration_file_exists, output_dir_empty, selected_output_dir_resolved

    @staticmethod
    def _is_directory_empty(path: Path) -> bool:
        try:
            next(path.iterdir())
        except StopIteration:
            return True
        except Exception:
            return False
        return False

    @staticmethod
    def _prune_empty_subdirs(root_path: Path) -> None:
        if not root_path.is_dir():
            return
        for child in sorted(root_path.rglob("*"), key=lambda path: len(path.parts), reverse=True):
            if not child.is_dir():
                continue
            try:
                child.rmdir()
            except OSError:
                continue

    def _run_preflight_depth_check(self, *, camera_ids: list[str]) -> None:
        missing_depth: list[str] = []
        for camera_id in camera_ids:
            frame = self._camera_manager.get_latest_raw_snapshot(camera_id, require_depth=True)
            if frame is None:
                frame = self._camera_manager.capture_raw_frame(
                    camera_id,
                    require_depth=True,
                    timeout_ms=700,
                    max_attempts=10,
                    prefer_depth_only=False,
                )
            if frame is None or frame.depth is None:
                missing_depth.append(camera_id)

        if missing_depth:
            raise ValueError(
                "Recording preflight failed. Depth capture is unavailable for selected camera(s): "
                + ", ".join(missing_depth)
            )
