from __future__ import annotations

import logging
import time
from typing import Any, List, Mapping, Optional, Sequence, Tuple

import cv2
import numpy as np
import numpy.typing as npt

from calibration.camera.base import CameraDevice, CameraFrame, CameraIntrinsics

LOGGER = logging.getLogger(__name__)

try:
    from pyorbbecsdk import Config, Context, OBFormat, OBPermissionType, OBPropertyID, OBSensorType, Pipeline  # type: ignore
except Exception as import_error:  # pragma: no cover - exercised only when SDK missing
    Config = None  # type: ignore
    Context = None  # type: ignore
    OBFormat = None  # type: ignore
    OBPermissionType = None  # type: ignore
    OBPropertyID = None  # type: ignore
    OBSensorType = None  # type: ignore
    Pipeline = None  # type: ignore
    _SDK_IMPORT_ERROR = import_error
else:
    _SDK_IMPORT_ERROR = None

_CONTEXT_KEEPALIVE: List[Any] = []


class FemtoBoltCamera(CameraDevice):
    """Orbbec Femto Bolt implementation behind the generic camera interface."""

    def __init__(
        self,
        device: Any,
        camera_id: str,
        color_resolution: Tuple[int, int],
        depth_resolution: Tuple[int, int],
        fps: int,
        use_depth: bool = False,
        camera_tuning: Optional[Mapping[str, Any]] = None,
        serial_number: str = "unknown",
        device_name: str = "unknown",
    ) -> None:
        self._device = device
        self._camera_id = camera_id
        self._color_resolution = color_resolution
        self._depth_resolution = depth_resolution
        self._fps = int(fps)
        self._use_depth = bool(use_depth)
        self._camera_tuning = dict(camera_tuning or {})
        self._serial_number = str(serial_number)
        self._device_name = str(device_name)

        self._pipeline: Optional[Any] = None
        self._intrinsics: Optional[CameraIntrinsics] = None
        self._depth_intrinsics: Optional[CameraIntrinsics] = None
        self._depth_to_color_transform: Optional[npt.NDArray[np.float64]] = None
        self._started = False
        self._frame_index = 0

        self._color_profile: Optional[Any] = None
        self._depth_profile: Optional[Any] = None

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def device_name(self) -> str:
        return self._device_name

    def start(self) -> None:
        if self._started:
            return
        if Pipeline is None or Config is None:
            raise RuntimeError(
                "pyorbbecsdk is not available. Install it to use real Femto Bolt cameras. "
                f"Original import error: {_SDK_IMPORT_ERROR}"
            )

        self._pipeline = Pipeline(self._device)
        config = Config()

        try:
            color_profiles = self._pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            self._color_profile = self._select_color_profile(color_profiles)
            config.enable_stream(self._color_profile)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize color stream for camera {self._camera_id} (serial={self._serial_number}): {exc}"
            ) from exc

        if self._use_depth:
            try:
                depth_profiles = self._pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
                self._depth_profile = self._select_depth_profile(depth_profiles)
                config.enable_stream(self._depth_profile)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to initialize depth stream for camera {self._camera_id} (serial={self._serial_number}): {exc}"
                ) from exc

        try:
            self._pipeline.start(config)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to start pipeline for camera {self._camera_id} (serial={self._serial_number}): {exc}"
            ) from exc

        self._apply_camera_tuning()

        self._intrinsics = self._extract_intrinsics()
        self._intrinsics.validate()
        if self._use_depth:
            self._depth_intrinsics = self._extract_depth_intrinsics()
            self._depth_intrinsics.validate()
            self._depth_to_color_transform = self._extract_depth_to_color_transform()
        self._started = True
        LOGGER.info(
            "Started Femto Bolt camera %s name=%s serial=%s",
            self._camera_id,
            self._device_name,
            self._serial_number,
        )

    def _apply_camera_tuning(self) -> None:
        if OBPropertyID is None or OBPermissionType is None:
            return
        if not self._camera_tuning:
            return

        color_auto_exposure = bool(self._camera_tuning.get("color_auto_exposure", True))
        color_exposure = self._parse_optional_int(self._camera_tuning.get("color_exposure"))
        color_gain = self._parse_optional_int(self._camera_tuning.get("color_gain"))
        color_auto_white_balance = bool(self._camera_tuning.get("color_auto_white_balance", True))
        color_white_balance = self._parse_optional_int(self._camera_tuning.get("color_white_balance"))
        color_brightness = self._parse_optional_int(self._camera_tuning.get("color_brightness"))

        self._set_bool_property(
            property_id=getattr(OBPropertyID, "OB_PROP_COLOR_AUTO_EXPOSURE_BOOL", None),
            value=color_auto_exposure,
            name="color_auto_exposure",
        )

        if not color_auto_exposure and color_exposure is not None:
            self._set_int_property(
                property_id=getattr(OBPropertyID, "OB_PROP_COLOR_EXPOSURE_INT", None),
                value=color_exposure,
                name="color_exposure",
            )

        if color_gain is not None:
            self._set_int_property(
                property_id=getattr(OBPropertyID, "OB_PROP_COLOR_GAIN_INT", None),
                value=color_gain,
                name="color_gain",
            )

        self._set_bool_property(
            property_id=getattr(OBPropertyID, "OB_PROP_COLOR_AUTO_WHITE_BALANCE_BOOL", None),
            value=color_auto_white_balance,
            name="color_auto_white_balance",
        )

        if not color_auto_white_balance and color_white_balance is not None:
            self._set_int_property(
                property_id=getattr(OBPropertyID, "OB_PROP_COLOR_WHITE_BALANCE_INT", None),
                value=color_white_balance,
                name="color_white_balance",
            )

        if color_brightness is not None:
            self._set_int_property(
                property_id=getattr(OBPropertyID, "OB_PROP_COLOR_BRIGHTNESS_INT", None),
                value=color_brightness,
                name="color_brightness",
            )

    def _set_bool_property(self, property_id: Any, value: bool, name: str) -> None:
        if property_id is None:
            return
        if not self._is_property_writable(property_id):
            LOGGER.info("Camera %s: property %s is not writable", self._camera_id, name)
            return
        try:
            self._device.set_bool_property(property_id, bool(value))
            LOGGER.info("Camera %s: set %s=%s", self._camera_id, name, bool(value))
        except Exception as exc:
            LOGGER.warning("Camera %s: failed to set %s: %s", self._camera_id, name, exc)

    def _set_int_property(self, property_id: Any, value: int, name: str) -> None:
        if property_id is None:
            return
        if not self._is_property_writable(property_id):
            LOGGER.info("Camera %s: property %s is not writable", self._camera_id, name)
            return

        target_value = int(value)
        try:
            rng = self._device.get_int_property_range(property_id)
            clamped = max(int(rng.min), min(int(rng.max), target_value))
            if clamped != target_value:
                LOGGER.warning(
                    "Camera %s: clamped %s from %s to %s (range %s..%s)",
                    self._camera_id,
                    name,
                    target_value,
                    clamped,
                    int(rng.min),
                    int(rng.max),
                )
            target_value = clamped
        except Exception:
            pass

        try:
            self._device.set_int_property(property_id, int(target_value))
            LOGGER.info("Camera %s: set %s=%s", self._camera_id, name, int(target_value))
        except Exception as exc:
            LOGGER.warning("Camera %s: failed to set %s: %s", self._camera_id, name, exc)

    def _is_property_writable(self, property_id: Any) -> bool:
        if OBPermissionType is None:
            return False
        try:
            return bool(self._device.is_property_supported(property_id, OBPermissionType.PERMISSION_WRITE))
        except Exception:
            return False

    @staticmethod
    def _parse_optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return int(value)

    def stop(self) -> None:
        if self._pipeline is not None and self._started:
            try:
                self._pipeline.stop()
            except Exception as exc:
                LOGGER.warning("Failed to stop camera %s cleanly: %s", self._camera_id, exc)
        self._started = False

    def get_intrinsics(self) -> CameraIntrinsics:
        if self._intrinsics is None:
            raise RuntimeError(f"Camera {self._camera_id} intrinsics are not available before start()")
        return self._intrinsics

    def get_depth_intrinsics(self) -> Optional[CameraIntrinsics]:
        if not self._use_depth:
            return None
        return self._depth_intrinsics

    def get_depth_to_color_transform(self) -> Optional[npt.NDArray[np.float64]]:
        if not self._use_depth:
            return None
        return None if self._depth_to_color_transform is None else self._depth_to_color_transform.copy()

    def get_frame(self, timeout_ms: int = 1000) -> Optional[CameraFrame]:
        if not self._started or self._pipeline is None:
            return None

        try:
            frames = self._pipeline.wait_for_frames(int(timeout_ms))
        except Exception as exc:
            LOGGER.warning("wait_for_frames failed for %s: %s", self._camera_id, exc)
            return None

        if frames is None:
            return None

        color: Optional[npt.NDArray[np.uint8]] = None
        depth: Optional[npt.NDArray[np.uint16]] = None

        color_frame = None
        try:
            color_frame = frames.get_color_frame()
        except Exception:
            color_frame = None

        if color_frame is not None:
            color = self._decode_color_frame(color_frame)

        depth_frame = None
        if self._use_depth:
            try:
                depth_frame = frames.get_depth_frame()
            except Exception:
                depth_frame = None

        if depth_frame is not None:
            depth = self._decode_depth_frame(depth_frame)

        frame = CameraFrame(
            camera_id=self._camera_id,
            frame_index=self._frame_index,
            timestamp_ns=time.time_ns(),
            color=color,
            depth=depth,
            simulated_marker_poses=None,
        )
        self._frame_index += 1
        return frame

    def _select_color_profile(self, profiles: Any) -> Any:
        width, height = self._color_resolution

        format_candidates = []
        if OBFormat is not None:
            format_candidates = [OBFormat.RGB, OBFormat.YUYV, OBFormat.MJPG]

        for fmt in format_candidates:
            try:
                profile = profiles.get_video_stream_profile(width, height, fmt, self._fps)
                LOGGER.info(
                    "Camera %s using color profile %sx%s @ %sfps (%s)",
                    self._camera_id,
                    width,
                    height,
                    self._fps,
                    fmt,
                )
                return profile
            except Exception:
                continue

        fallback_resolutions = [
            (1920, 1080, 30),
            (1280, 720, 30),
            (640, 480, 30),
            (1920, 1080, 15),
            (1280, 720, 15),
        ]
        for fb_width, fb_height, fb_fps in fallback_resolutions:
            for fmt in format_candidates:
                try:
                    profile = profiles.get_video_stream_profile(fb_width, fb_height, fmt, fb_fps)
                    LOGGER.info(
                        "Camera %s using fallback color profile %sx%s @ %sfps (%s)",
                        self._camera_id,
                        fb_width,
                        fb_height,
                        fb_fps,
                        fmt,
                    )
                    return profile
                except Exception:
                    continue

        raise RuntimeError(f"No compatible color profile found for camera {self._camera_id}")

    def _select_depth_profile(self, profiles: Any) -> Any:
        if OBFormat is None:
            raise RuntimeError("OBFormat enum unavailable")

        depth_width, depth_height = int(self._depth_resolution[0]), int(self._depth_resolution[1])
        candidates = [
            (depth_width, depth_height, OBFormat.Y16, 30),
            (depth_width, depth_height, OBFormat.Y16, 15),
            (640, 576, OBFormat.Y16, 30),
            (640, 576, OBFormat.Y16, 15),
            (512, 512, OBFormat.Y16, 30),
            (320, 288, OBFormat.Y16, 30),
        ]

        for width, height, fmt, fps in candidates:
            try:
                profile = profiles.get_video_stream_profile(width, height, fmt, fps)
                LOGGER.info(
                    "Camera %s using depth profile %sx%s @ %sfps",
                    self._camera_id,
                    width,
                    height,
                    fps,
                )
                return profile
            except Exception:
                continue

        raise RuntimeError(f"No compatible depth profile found for camera {self._camera_id}")

    def _extract_intrinsics(self) -> CameraIntrinsics:
        intrinsics = self._try_extract_color_intrinsics()
        if intrinsics is not None:
            return self._normalize_intrinsics_to_target(intrinsics, prefer_color=True)

        intrinsics = self._try_extract_intrinsics_from_calibration_list(prefer_color=True)
        if intrinsics is not None:
            return intrinsics

        intrinsics = self._try_extract_depth_intrinsics()
        if intrinsics is not None:
            return self._normalize_intrinsics_to_target(intrinsics, prefer_color=False)

        intrinsics = self._try_extract_intrinsics_from_calibration_list(prefer_color=False)
        if intrinsics is not None:
            return intrinsics

        return self._fallback_intrinsics_from_profile(prefer_color=True)

    def _extract_depth_intrinsics(self) -> CameraIntrinsics:
        intrinsics = self._try_extract_depth_intrinsics()
        if intrinsics is not None:
            return self._normalize_intrinsics_to_target(intrinsics, prefer_color=False)

        intrinsics = self._try_extract_intrinsics_from_calibration_list(prefer_color=False)
        if intrinsics is not None:
            return intrinsics

        intrinsics = self._try_extract_color_intrinsics()
        if intrinsics is not None:
            return self._normalize_intrinsics_to_target(intrinsics, prefer_color=False)

        intrinsics = self._try_extract_intrinsics_from_calibration_list(prefer_color=True)
        if intrinsics is not None:
            return self._scale_intrinsics_to_resolution(
                intrinsics,
                target_w=int(self._depth_resolution[0]),
                target_h=int(self._depth_resolution[1]),
            )

        return self._fallback_intrinsics_from_profile(prefer_color=False)

    def _normalize_intrinsics_to_target(self, intrinsics: CameraIntrinsics, prefer_color: bool) -> CameraIntrinsics:
        target_w, target_h = self._target_resolution_for_intrinsics(prefer_color=prefer_color)
        if intrinsics.width == target_w and intrinsics.height == target_h:
            return intrinsics

        LOGGER.info(
            "Scaling %s intrinsics for camera %s (%sx%s -> %sx%s)",
            "color" if prefer_color else "depth",
            self._camera_id,
            intrinsics.width,
            intrinsics.height,
            target_w,
            target_h,
        )
        return self._scale_intrinsics_to_resolution(intrinsics, target_w=target_w, target_h=target_h)

    def _try_extract_color_intrinsics(self) -> Optional[CameraIntrinsics]:
        intr = None
        try:
            if self._pipeline is not None and hasattr(self._pipeline, "get_camera_param"):
                params = self._pipeline.get_camera_param()
                intr = getattr(params, "rgb_intrinsic", None)
            elif hasattr(self._device, "get_color_intrinsics"):
                intr = self._device.get_color_intrinsics()
        except Exception:
            intr = None

        if intr is None:
            try:
                if hasattr(self._device, "get_camera_param"):
                    params = self._device.get_camera_param()
                    intr = getattr(params, "color_intrinsics", None)
            except Exception:
                intr = None

        if intr is None:
            return None

        return self._intrinsics_from_struct(intr)

    def _try_extract_depth_intrinsics(self) -> Optional[CameraIntrinsics]:
        intr = None
        try:
            if self._pipeline is not None and hasattr(self._pipeline, "get_camera_param"):
                params = self._pipeline.get_camera_param()
                intr = getattr(params, "depth_intrinsic", None)
            elif hasattr(self._device, "get_depth_intrinsics"):
                intr = self._device.get_depth_intrinsics()
        except Exception:
            intr = None

        if intr is None:
            try:
                if hasattr(self._device, "get_camera_param"):
                    params = self._device.get_camera_param()
                    intr = getattr(params, "depth_intrinsics", None)
            except Exception:
                intr = None

        if intr is None:
            return None

        return self._intrinsics_from_struct(intr)

    def _extract_depth_to_color_transform(self) -> Optional[npt.NDArray[np.float64]]:
        transform = self._try_extract_depth_to_color_transform_from_pipeline()
        if transform is not None:
            return transform
        return self._try_extract_depth_to_color_transform_from_calibration_list()

    def _try_extract_depth_to_color_transform_from_pipeline(self) -> Optional[npt.NDArray[np.float64]]:
        if self._pipeline is None or not hasattr(self._pipeline, "get_camera_param"):
            return None

        try:
            params = self._pipeline.get_camera_param()
            return self._transform_from_struct(getattr(params, "transform", None))
        except Exception:
            return None

    def _try_extract_depth_to_color_transform_from_calibration_list(self) -> Optional[npt.NDArray[np.float64]]:
        if not hasattr(self._device, "get_calibration_camera_param_list"):
            return None

        try:
            params = self._device.get_calibration_camera_param_list()
            count = int(params.get_count())
        except Exception:
            return None

        if count <= 0:
            return None

        target_w, target_h = self._target_resolution_for_intrinsics(prefer_color=False)
        best_transform: Optional[npt.NDArray[np.float64]] = None
        best_score = float("inf")

        for idx in range(count):
            try:
                param = params.get_camera_param(int(idx))
                depth_intr = getattr(param, "depth_intrinsic", None)
                if depth_intr is None:
                    continue

                width = int(getattr(depth_intr, "width"))
                height = int(getattr(depth_intr, "height"))
                score = abs(width - target_w) + abs(height - target_h)

                transform = self._transform_from_struct(getattr(param, "transform", None))
                if transform is None:
                    continue

                if score < best_score:
                    best_score = float(score)
                    best_transform = transform
            except Exception:
                continue

        return best_transform

    @staticmethod
    def _transform_from_struct(transform_struct: Any) -> Optional[npt.NDArray[np.float64]]:
        if transform_struct is None:
            return None

        try:
            rotation = np.asarray(getattr(transform_struct, "rot"), dtype=np.float64).reshape(3, 3)
            translation = np.asarray(getattr(transform_struct, "transform"), dtype=np.float64).reshape(3)
        except Exception:
            return None

        if not np.isfinite(rotation).all() or not np.isfinite(translation).all():
            return None
        if np.linalg.norm(rotation) < 1e-12:
            return None

        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = rotation
        # SDK translation is in millimeters; convert to meters for point-cloud math.
        transform[:3, 3] = translation * 1e-3
        return transform

    def _intrinsics_from_struct(self, intr: Any) -> CameraIntrinsics:
        fx = float(getattr(intr, "fx"))
        fy = float(getattr(intr, "fy"))
        cx = float(getattr(intr, "cx"))
        cy = float(getattr(intr, "cy"))
        width = int(getattr(intr, "width"))
        height = int(getattr(intr, "height"))

        camera_matrix = np.array(
            [
                [fx, 0.0, cx],
                [0.0, fy, cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        dist = np.zeros((5,), dtype=np.float64)
        return CameraIntrinsics(camera_matrix=camera_matrix, dist_coeffs=dist, width=width, height=height)

    def _try_extract_intrinsics_from_calibration_list(self, prefer_color: bool) -> Optional[CameraIntrinsics]:
        if not hasattr(self._device, "get_calibration_camera_param_list"):
            return None

        try:
            params = self._device.get_calibration_camera_param_list()
            count = int(params.get_count())
        except Exception:
            return None

        if count <= 0:
            return None

        target_w, target_h = self._target_resolution_for_intrinsics(prefer_color=prefer_color)
        intr_attr = "rgb_intrinsic" if prefer_color else "depth_intrinsic"
        best_intrinsics = self._select_best_calibration_intrinsics(
            params=params,
            count=count,
            intr_attr=intr_attr,
            target_w=target_w,
            target_h=target_h,
        )

        if best_intrinsics is None:
            return None

        if best_intrinsics.width == target_w and best_intrinsics.height == target_h:
            LOGGER.info(
                "Using calibration-list %s intrinsics for camera %s (%sx%s)",
                "color" if prefer_color else "depth",
                self._camera_id,
                target_w,
                target_h,
            )
            return best_intrinsics

        scaled = self._scale_intrinsics_to_resolution(best_intrinsics, target_w=target_w, target_h=target_h)
        LOGGER.info(
            "Using scaled calibration-list %s intrinsics for camera %s (%sx%s -> %sx%s)",
            "color" if prefer_color else "depth",
            self._camera_id,
            best_intrinsics.width,
            best_intrinsics.height,
            target_w,
            target_h,
        )
        return scaled

    def _select_best_calibration_intrinsics(
        self,
        params: Any,
        count: int,
        intr_attr: str,
        target_w: int,
        target_h: int,
    ) -> Optional[CameraIntrinsics]:
        best_intrinsics: Optional[CameraIntrinsics] = None
        best_score = float("inf")

        for idx in range(count):
            candidate = self._calibration_intrinsics_candidate(params=params, index=idx, intr_attr=intr_attr)
            if candidate is None:
                continue

            target_aspect = float(target_w) / float(max(target_h, 1))
            candidate_aspect = float(candidate.width) / float(max(candidate.height, 1))
            aspect_penalty = 10000.0 * abs(candidate_aspect - target_aspect)
            score = abs(candidate.width - target_w) + abs(candidate.height - target_h) + aspect_penalty
            if score < best_score:
                best_score = float(score)
                best_intrinsics = candidate

        return best_intrinsics

    def _calibration_intrinsics_candidate(self, params: Any, index: int, intr_attr: str) -> Optional[CameraIntrinsics]:
        try:
            param = params.get_camera_param(int(index))
            intr = getattr(param, intr_attr, None)
            if intr is None:
                return None
            return self._intrinsics_from_struct(intr)
        except Exception:
            return None

    def _target_resolution_for_intrinsics(self, prefer_color: bool) -> Tuple[int, int]:
        profile = self._color_profile if prefer_color else self._depth_profile
        if profile is not None:
            try:
                return int(profile.get_width()), int(profile.get_height())
            except Exception:
                pass

        if prefer_color:
            return int(self._color_resolution[0]), int(self._color_resolution[1])

        return int(self._depth_resolution[0]), int(self._depth_resolution[1])

    @staticmethod
    def _scale_intrinsics_to_resolution(intrinsics: CameraIntrinsics, target_w: int, target_h: int) -> CameraIntrinsics:
        if intrinsics.width <= 0 or intrinsics.height <= 0:
            return intrinsics

        sx = float(target_w) / float(intrinsics.width)
        sy = float(target_h) / float(intrinsics.height)

        camera_matrix = np.asarray(intrinsics.camera_matrix, dtype=np.float64).copy()
        camera_matrix[0, 0] *= sx
        camera_matrix[1, 1] *= sy
        camera_matrix[0, 2] *= sx
        camera_matrix[1, 2] *= sy

        return CameraIntrinsics(
            camera_matrix=camera_matrix,
            dist_coeffs=np.asarray(intrinsics.dist_coeffs, dtype=np.float64).copy(),
            width=int(target_w),
            height=int(target_h),
        )

    def _fallback_intrinsics_from_profile(self, prefer_color: bool) -> CameraIntrinsics:
        profile = self._color_profile if prefer_color else self._depth_profile
        if profile is None:
            profile = self._color_profile or self._depth_profile
        if profile is None:
            width, height = self._color_resolution if prefer_color else self._depth_resolution
        else:
            width = int(profile.get_width())
            height = int(profile.get_height())

        fx = fy = 0.9 * float(max(width, height))
        cx = width / 2.0
        cy = height / 2.0

        camera_matrix = np.array(
            [
                [fx, 0.0, cx],
                [0.0, fy, cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        dist = np.zeros((5,), dtype=np.float64)

        LOGGER.warning(
            "Using fallback intrinsics for camera %s (w=%s h=%s). For production, prefer device intrinsics.",
            self._camera_id,
            width,
            height,
        )
        return CameraIntrinsics(camera_matrix=camera_matrix, dist_coeffs=dist, width=width, height=height)

    def _decode_color_frame(self, frame: Any) -> Optional[npt.NDArray[np.uint8]]:
        try:
            raw = frame.get_data()
            width = int(frame.get_width())
            height = int(frame.get_height())
        except Exception:
            return None

        if width <= 0 or height <= 0:
            LOGGER.error("Unsupported frame resolution from camera %s: %sx%s", self._camera_id, width, height)
            return None

        fmt = None
        try:
            fmt = frame.get_format()
        except Exception:
            fmt = None

        if fmt is not None and OBFormat is not None and fmt == OBFormat.MJPG:
            encoded = np.frombuffer(raw, dtype=np.uint8)
            decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            return decoded

        buffer = np.frombuffer(raw, dtype=np.uint8)
        pixel_count = width * height

        if pixel_count <= 0:
            return None

        if buffer.size == pixel_count * 3:
            color = buffer.reshape(height, width, 3)
            if fmt is not None and OBFormat is not None and fmt == OBFormat.RGB:
                color = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
            return color

        if buffer.size == pixel_count * 4:
            bgra = buffer.reshape(height, width, 4)
            return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)

        if buffer.size == pixel_count * 2:
            yuyv = buffer.reshape(height, width, 2)
            return cv2.cvtColor(yuyv, cv2.COLOR_YUV2BGR_YUYV)

        if buffer.size == pixel_count:
            gray = buffer.reshape(height, width)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        LOGGER.warning(
            "Unexpected color frame buffer size for %s: %s bytes (%sx%s)",
            self._camera_id,
            buffer.size,
            width,
            height,
        )
        return None

    def _decode_depth_frame(self, frame: Any) -> Optional[npt.NDArray[np.uint16]]:
        try:
            width = int(frame.get_width())
            height = int(frame.get_height())
            depth = np.frombuffer(frame.get_data(), dtype=np.uint16)
        except Exception:
            return None

        expected_size = width * height
        if depth.size < expected_size:
            return None
        if depth.size > expected_size:
            depth = depth[:expected_size]
        return depth.reshape(height, width)


def discover_femto_bolt_cameras(
    color_resolution: Tuple[int, int],
    depth_resolution: Tuple[int, int],
    fps: int,
    max_cameras: int,
    use_depth: bool,
    allowed_camera_ids: Optional[Sequence[str]] = None,
    camera_tuning: Optional[Mapping[str, Any]] = None,
) -> List[FemtoBoltCamera]:
    if Context is None:
        raise RuntimeError(
            "pyorbbecsdk is not installed or failed to import. "
            f"Original import error: {_SDK_IMPORT_ERROR}"
        )

    try:
        context = Context()
        device_list = context.query_devices()
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize Orbbec SDK context/query devices: {exc}") from exc

    device_count = int(device_list.get_count())

    LOGGER.info("Detected %s Orbbec device(s)", device_count)

    cameras: List[FemtoBoltCamera] = []
    allowed = set(allowed_camera_ids or [])

    for index in range(min(device_count, max_cameras)):
        device = device_list.get_device_by_index(index)

        camera_id = f"cam{index}"
        serial = "unknown"
        device_name = "unknown"
        try:
            info = device.get_device_info()
            serial = str(info.get_serial_number())
            device_name = str(info.get_name())
        except Exception:
            pass

        LOGGER.info("Discovered camera index=%s id=%s name=%s serial=%s", index, camera_id, device_name, serial)

        if allowed and camera_id not in allowed and serial not in allowed:
            continue

        camera = FemtoBoltCamera(
            device=device,
            camera_id=camera_id,
            color_resolution=color_resolution,
            depth_resolution=depth_resolution,
            fps=fps,
            use_depth=use_depth,
            camera_tuning=camera_tuning,
            serial_number=serial,
            device_name=device_name,
        )
        cameras.append(camera)

    _CONTEXT_KEEPALIVE.append(context)

    if not cameras:
        LOGGER.warning("No Femto Bolt cameras selected for calibration")

    return cameras

