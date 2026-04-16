from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.domain.models import CameraFrame, CameraIntrinsics
from app.integrations.orbbec_sdk import OrbbecRuntime


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CameraRuntimeInfo:
    camera_id: str
    running: bool
    depth_resolution: tuple[int, int] | None
    color_resolution: tuple[int, int] | None
    fps: int
    name: str | None
    serial: str | None


@dataclass(slots=True)
class _Profiles:
    depth_profile: Any
    color_profile: Any


class _ManagedCamera:
    def __init__(
        self,
        camera_id: str,
        device: Any,
        sdk: Any,
        target_depth: tuple[int, int],
        target_color: tuple[int, int],
        fps: int,
    ) -> None:
        self.camera_id = camera_id
        self._device = device
        self._sdk = sdk
        self._target_depth = target_depth
        self._target_color = target_color
        self._fps = fps

        self._pipeline: Any | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_frame: CameraFrame | None = None
        self._lock = threading.Lock()

        self.depth_resolution: tuple[int, int] | None = None
        self.color_resolution: tuple[int, int] | None = None
        self.depth_intrinsics: CameraIntrinsics | None = None
        self.color_intrinsics: CameraIntrinsics | None = None
        self.distortion_coeffs: list[float] | None = None

        self.device_name: str | None = None
        self.serial_number: str | None = None

        try:
            info = self._device.get_device_info()
            self.device_name = info.get_name()
            self.serial_number = info.get_serial_number()
        except Exception:
            pass

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return

        pipeline = self._sdk.Pipeline(self._device)
        config = self._sdk.Config()

        profiles = self._select_profiles(pipeline)
        config.enable_stream(profiles.depth_profile)

        if profiles.color_profile is not None:
            config.enable_stream(profiles.color_profile)

        pipeline.start(config)

        self._pipeline = pipeline
        self._running = True

        self._extract_intrinsics(profiles.depth_profile, profiles.color_profile)

        self._thread = threading.Thread(target=self._capture_loop, name=f"capture-{self.camera_id}", daemon=True)
        self._thread.start()

        logger.info("Camera %s started", self.camera_id)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            except Exception:
                pass
            self._pipeline = None

        logger.info("Camera %s stopped", self.camera_id)

    def get_latest_frame(self) -> CameraFrame | None:
        with self._lock:
            return self._latest_frame

    def _select_profiles(self, pipeline: Any) -> _Profiles:
        depth_profile = self._select_depth_profile(pipeline)
        color_profile = self._select_color_profile(pipeline)
        return _Profiles(depth_profile=depth_profile, color_profile=color_profile)

    def _select_depth_profile(self, pipeline: Any) -> Any:
        depth_profiles = pipeline.get_stream_profile_list(self._sdk.OBSensorType.DEPTH_SENSOR)
        desired = [
            (self._target_depth[0], self._target_depth[1], self._fps),
            (1024, 1024, 30),
            (1024, 1024, 15),
            (640, 576, 30),
            (640, 400, 30),
            (512, 512, 30),
            (1280, 800, 15),
        ]

        for width, height, fps in desired:
            for fmt in (self._sdk.OBFormat.Y16,):
                try:
                    profile = depth_profiles.get_video_stream_profile(width, height, fmt, fps)
                    self.depth_resolution = (profile.get_width(), profile.get_height())
                    return profile
                except Exception:
                    continue

        raise RuntimeError(f"No depth profile found for {self.camera_id}")

    def _select_color_profile(self, pipeline: Any) -> Any | None:
        try:
            color_profiles = pipeline.get_stream_profile_list(self._sdk.OBSensorType.COLOR_SENSOR)
        except Exception:
            return None

        desired = [
            (self._target_color[0], self._target_color[1], self._fps),
            (1920, 1080, 30),
            (1280, 720, 30),
            (640, 480, 30),
            (1920, 1080, 15),
        ]

        formats = [self._sdk.OBFormat.RGB, self._sdk.OBFormat.BGR, self._sdk.OBFormat.YUYV, self._sdk.OBFormat.MJPG]

        for width, height, fps in desired:
            for fmt in formats:
                try:
                    profile = color_profiles.get_video_stream_profile(width, height, fmt, fps)
                    self.color_resolution = (profile.get_width(), profile.get_height())
                    return profile
                except Exception:
                    continue

        return None

    def _to_intrinsics(self, source: Any) -> CameraIntrinsics | None:
        if source is None:
            return None
        required = ("fx", "fy", "cx", "cy", "width", "height")
        if not all(hasattr(source, item) for item in required):
            return None
        return CameraIntrinsics(
            fx=float(source.fx),
            fy=float(source.fy),
            cx=float(source.cx),
            cy=float(source.cy),
            width=int(source.width),
            height=int(source.height),
        )

    def _get_direct_intrinsics(self) -> tuple[Any | None, Any | None]:
        depth_intrinsics_obj = None
        color_intrinsics_obj = None

        try:
            if hasattr(self._device, "get_depth_intrinsics"):
                depth_intrinsics_obj = self._device.get_depth_intrinsics()
        except Exception:
            depth_intrinsics_obj = None

        try:
            if hasattr(self._device, "get_color_intrinsics"):
                color_intrinsics_obj = self._device.get_color_intrinsics()
        except Exception:
            color_intrinsics_obj = None

        return depth_intrinsics_obj, color_intrinsics_obj

    def _augment_intrinsics_from_camera_param(self, depth_obj: Any | None, color_obj: Any | None) -> tuple[Any | None, Any | None]:
        if depth_obj is not None:
            return depth_obj, color_obj

        if not hasattr(self._device, "get_camera_param"):
            return depth_obj, color_obj

        try:
            params = self._device.get_camera_param()
            if hasattr(params, "depth_intrinsics"):
                depth_obj = params.depth_intrinsics
            if hasattr(params, "rgb_intrinsics"):
                color_obj = params.rgb_intrinsics
        except Exception:
            pass

        return depth_obj, color_obj

    def _fallback_intrinsics(self, profile: Any, scale: float) -> CameraIntrinsics | None:
        if profile is None:
            return None
        width = int(profile.get_width())
        height = int(profile.get_height())
        focal = width * scale
        return CameraIntrinsics(
            fx=focal,
            fy=focal,
            cx=width / 2.0,
            cy=height / 2.0,
            width=width,
            height=height,
        )

    def _read_depth_distortion(self) -> list[float]:
        try:
            if hasattr(self._device, "get_depth_distortion"):
                distortion = self._device.get_depth_distortion()
                if distortion is not None:
                    return [
                        float(distortion.k1),
                        float(distortion.k2),
                        float(distortion.p1),
                        float(distortion.p2),
                        float(distortion.k3),
                    ]
        except Exception:
            pass

        return [0.0, 0.0, 0.0, 0.0, 0.0]

    def _extract_intrinsics(self, depth_profile: Any, color_profile: Any | None) -> None:
        depth_intrinsics_obj, color_intrinsics_obj = self._get_direct_intrinsics()
        depth_intrinsics_obj, color_intrinsics_obj = self._augment_intrinsics_from_camera_param(
            depth_intrinsics_obj,
            color_intrinsics_obj,
        )

        depth_intrinsics = self._to_intrinsics(depth_intrinsics_obj) or self._fallback_intrinsics(depth_profile, 0.65)
        color_intrinsics = self._to_intrinsics(color_intrinsics_obj) or self._fallback_intrinsics(color_profile, 0.75)

        self.depth_intrinsics = depth_intrinsics
        self.color_intrinsics = color_intrinsics
        self.distortion_coeffs = self._read_depth_distortion()

    def _capture_loop(self) -> None:
        while self._running and self._pipeline is not None:
            try:
                frames = self._pipeline.wait_for_frames(100)
                if frames is None:
                    continue

                depth_data = None
                color_data = None

                depth_frame = frames.get_depth_frame()
                if depth_frame is not None:
                    depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16).reshape(
                        (depth_frame.get_height(), depth_frame.get_width())
                    )

                color_frame = frames.get_color_frame()
                if color_frame is not None:
                    raw_color = np.frombuffer(color_frame.get_data(), dtype=np.uint8).reshape(
                        (color_frame.get_height(), color_frame.get_width(), -1)
                    )
                    color_data = self._convert_color_to_rgb(raw_color)

                if depth_data is None and color_data is None:
                    continue

                frame = CameraFrame(
                    camera_id=self.camera_id,
                    timestamp=time.time(),
                    color_data=color_data,
                    depth_data=depth_data,
                )

                with self._lock:
                    self._latest_frame = frame
            except Exception as exc:
                logger.warning("Capture error on %s: %s", self.camera_id, exc)
                time.sleep(0.05)

    def _convert_color_to_rgb(self, raw_color: np.ndarray) -> np.ndarray:
        channels = raw_color.shape[2]
        if channels == 3:
            return cv2.cvtColor(raw_color, cv2.COLOR_BGR2RGB)
        if channels == 4:
            return cv2.cvtColor(raw_color, cv2.COLOR_BGRA2RGB)
        if channels == 2:
            return cv2.cvtColor(raw_color, cv2.COLOR_YUV2RGB_YUYV)
        return raw_color[:, :, :3]


class CameraService:
    """Femto Bolt camera orchestration service."""

    def __init__(
        self,
        runtime: OrbbecRuntime,
        depth_res: tuple[int, int],
        color_res: tuple[int, int],
        fps: int,
        max_cameras: int,
    ) -> None:
        self._runtime = runtime
        self._depth_res = depth_res
        self._color_res = color_res
        self._fps = fps
        self._max_cameras = max_cameras

        self._lock = threading.RLock()
        self._cameras: dict[str, _ManagedCamera] = {}
        self._sdk_error: str | None = None

    def startup(self) -> int:
        with self._lock:
            self._cameras = {}
            self._sdk_error = None

            if not self._runtime.available or self._runtime.module is None:
                self._sdk_error = self._runtime.error or "Orbbec SDK unavailable"
                logger.warning("Camera runtime unavailable: %s", self._sdk_error)
                return 0

            sdk = self._runtime.module

            try:
                context = sdk.Context()
                device_list = context.query_devices()
                count = int(device_list.get_count())
            except Exception as exc:
                self._sdk_error = str(exc)
                logger.exception("Failed to discover Orbbec cameras")
                return 0

            selected_count = min(count, self._max_cameras)
            for index in range(selected_count):
                device = device_list.get_device_by_index(index)
                camera_id = f"cam{index}"
                camera = _ManagedCamera(
                    camera_id=camera_id,
                    device=device,
                    sdk=sdk,
                    target_depth=self._depth_res,
                    target_color=self._color_res,
                    fps=self._fps,
                )
                try:
                    camera.start()
                    self._cameras[camera_id] = camera
                except Exception as exc:
                    logger.exception("Failed to start camera %s: %s", camera_id, exc)

            logger.info("Camera startup complete with %d active camera(s)", len(self._cameras))
            return len(self._cameras)

    def shutdown(self) -> None:
        with self._lock:
            cameras = list(self._cameras.values())
            self._cameras = {}

        for camera in cameras:
            camera.stop()

    def camera_count(self) -> int:
        with self._lock:
            return len(self._cameras)

    def list_cameras(self) -> list[CameraRuntimeInfo]:
        with self._lock:
            result: list[CameraRuntimeInfo] = []
            for camera_id, camera in self._cameras.items():
                result.append(
                    CameraRuntimeInfo(
                        camera_id=camera_id,
                        running=camera.running,
                        depth_resolution=camera.depth_resolution,
                        color_resolution=camera.color_resolution,
                        fps=self._fps,
                        name=camera.device_name,
                        serial=camera.serial_number,
                    )
                )
            return result

    def get_latest_frames(self) -> dict[str, CameraFrame]:
        with self._lock:
            cameras = list(self._cameras.items())

        frames: dict[str, CameraFrame] = {}
        for camera_id, camera in cameras:
            frame = camera.get_latest_frame()
            if frame is not None:
                frames[camera_id] = frame
        return frames

    def is_running(self, camera_id: str) -> bool:
        with self._lock:
            camera = self._cameras.get(camera_id)
            return bool(camera and camera.running)

    def has_camera(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._cameras

    def get_depth_intrinsics(self, camera_id: str) -> CameraIntrinsics | None:
        with self._lock:
            camera = self._cameras.get(camera_id)
            return camera.depth_intrinsics if camera else None

    def get_color_intrinsics(self, camera_id: str) -> CameraIntrinsics | None:
        with self._lock:
            camera = self._cameras.get(camera_id)
            return camera.color_intrinsics if camera else None

    def get_distortion_coeffs(self, camera_id: str) -> list[float] | None:
        with self._lock:
            camera = self._cameras.get(camera_id)
            return camera.distortion_coeffs if camera else None

    def get_intrinsics_map(self) -> dict[str, CameraIntrinsics]:
        with self._lock:
            mapping: dict[str, CameraIntrinsics] = {}
            for camera_id, camera in self._cameras.items():
                if camera.depth_intrinsics is not None:
                    mapping[camera_id] = camera.depth_intrinsics
            return mapping

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sdk_available": self._runtime.available,
                "sdk_error": self._sdk_error,
                "camera_count": len(self._cameras),
                "cameras": [
                    {
                        "id": cam_id,
                        "running": cam.running,
                        "depth_resolution": cam.depth_resolution,
                        "color_resolution": cam.color_resolution,
                        "name": cam.device_name,
                        "serial": cam.serial_number,
                    }
                    for cam_id, cam in self._cameras.items()
                ],
            }
