from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

from calibration.camera.network_api import NetworkCameraDiscoveryConfig

REQUIRED_FACES: Tuple[str, ...] = ("front", "top", "left", "right", "back", "bottom")


@dataclass
class CubeConfig:
    marker_length: float
    cube_length: float

    def validate(self) -> None:
        if self.marker_length <= 0:
            raise ValueError("cube.marker_length must be > 0")
        if self.cube_length <= 0:
            raise ValueError("cube.cube_length must be > 0")
        if self.marker_length > self.cube_length:
            raise ValueError("cube.marker_length should not be larger than cube.cube_length")


@dataclass
class QualityConfig:
    min_markers_per_frame: int = 1
    min_valid_frames_per_camera: int = 10
    max_reprojection_error_px: float = 6.0
    marker_outlier_translation_m: float = 0.06
    marker_outlier_rotation_deg: float = 8.0
    frame_outlier_translation_m: float = 0.08
    frame_outlier_rotation_deg: float = 10.0
    max_translation_std_m: float = 0.03
    max_rotation_std_deg: float = 3.5
    depth_distance_tolerance_m: float = 0.08
    depth_distance_tolerance_pct: float = 12.0

    def validate(self) -> None:
        if self.min_markers_per_frame < 1:
            raise ValueError("quality.min_markers_per_frame must be >= 1")
        if self.min_valid_frames_per_camera < 1:
            raise ValueError("quality.min_valid_frames_per_camera must be >= 1")
        if self.max_reprojection_error_px <= 0:
            raise ValueError("quality.max_reprojection_error_px must be > 0")
        if self.marker_outlier_translation_m <= 0:
            raise ValueError("quality.marker_outlier_translation_m must be > 0")
        if self.marker_outlier_rotation_deg <= 0:
            raise ValueError("quality.marker_outlier_rotation_deg must be > 0")
        if self.frame_outlier_translation_m <= 0:
            raise ValueError("quality.frame_outlier_translation_m must be > 0")
        if self.frame_outlier_rotation_deg <= 0:
            raise ValueError("quality.frame_outlier_rotation_deg must be > 0")
        if self.max_translation_std_m <= 0:
            raise ValueError("quality.max_translation_std_m must be > 0")
        if self.max_rotation_std_deg <= 0:
            raise ValueError("quality.max_rotation_std_deg must be > 0")
        if self.depth_distance_tolerance_m <= 0:
            raise ValueError("quality.depth_distance_tolerance_m must be > 0")
        if self.depth_distance_tolerance_pct <= 0:
            raise ValueError("quality.depth_distance_tolerance_pct must be > 0")


@dataclass
class DebugConfig:
    enabled: bool = False
    show_windows: bool = False
    save_images: bool = True
    image_format: str = "jpg"


@dataclass
class CameraTuningConfig:
    color_auto_exposure: bool = True
    color_exposure: Optional[int] = None
    color_gain: Optional[int] = None
    color_auto_white_balance: bool = True
    color_white_balance: Optional[int] = None
    color_brightness: Optional[int] = None

    def validate(self) -> None:
        if self.color_exposure is not None and self.color_exposure < 1:
            raise ValueError("camera.color_exposure must be >= 1")
        if self.color_gain is not None and self.color_gain < 0:
            raise ValueError("camera.color_gain must be >= 0")
        if self.color_white_balance is not None and self.color_white_balance < 1:
            raise ValueError("camera.color_white_balance must be >= 1")
        if self.color_brightness is not None and self.color_brightness < 1:
            raise ValueError("camera.color_brightness must be >= 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "color_auto_exposure": self.color_auto_exposure,
            "color_exposure": self.color_exposure,
            "color_gain": self.color_gain,
            "color_auto_white_balance": self.color_auto_white_balance,
            "color_white_balance": self.color_white_balance,
            "color_brightness": self.color_brightness,
        }


@dataclass
class CalibrationConfig:
    output: Path
    aruco_dict: str
    cube: CubeConfig
    face_ids: Dict[str, int]
    color_resolution: Tuple[int, int]
    depth_resolution: Tuple[int, int]
    fps: int
    frame_count: int = 60
    warmup_frames: int = 5
    max_cameras: int = 6
    world_origin: str = "cube_center"
    use_depth: bool = False
    camera_ids: Optional[List[str]] = None
    camera: CameraTuningConfig = field(default_factory=CameraTuningConfig)
    network_camera: NetworkCameraDiscoveryConfig = field(default_factory=NetworkCameraDiscoveryConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)

    @staticmethod
    def _parse_resolution(value: Any) -> Tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            width, height = int(value[0]), int(value[1])
            if width <= 0 or height <= 0:
                raise ValueError("color_res values must be positive")
            return width, height

        if isinstance(value, str):
            match = re.match(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$", value)
            if not match:
                raise ValueError("color_res must be in format 'WIDTHxHEIGHT'")
            width, height = int(match.group(1)), int(match.group(2))
            if width <= 0 or height <= 0:
                raise ValueError("color_res values must be positive")
            return width, height

        raise ValueError("color_res must be either string 'WIDTHxHEIGHT' or [width, height]")

    @staticmethod
    def _parse_optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return int(value)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationConfig":
        cube_payload = payload.get("cube")
        if not isinstance(cube_payload, Mapping):
            if "marker_length" in payload and "cube_length" in payload:
                cube_payload = {
                    "marker_length": payload["marker_length"],
                    "cube_length": payload["cube_length"],
                }
            else:
                raise ValueError(
                    "Missing cube definition. Provide either 'cube' with marker_length/cube_length "
                    "or top-level 'marker_length' and 'cube_length'."
                )

        face_payload = payload.get("face_ids")
        if not isinstance(face_payload, Mapping):
            raise ValueError("Missing or invalid 'face_ids' section")

        quality_payload = payload.get("quality", {})
        if not isinstance(quality_payload, Mapping):
            quality_payload = {}

        camera_payload = payload.get("camera", {})
        if not isinstance(camera_payload, Mapping):
            camera_payload = {}

        network_camera_payload = payload.get("network_camera", {})
        if not isinstance(network_camera_payload, Mapping):
            network_camera_payload = {}

        debug_payload = payload.get("debug", {})
        if isinstance(debug_payload, bool):
            debug_payload = {"enabled": debug_payload}
        if not isinstance(debug_payload, Mapping):
            debug_payload = {}

        quality = QualityConfig(
            min_markers_per_frame=int(quality_payload.get("min_markers_per_frame", payload.get("min_markers_per_frame", 1))),
            min_valid_frames_per_camera=int(
                quality_payload.get("min_valid_frames_per_camera", payload.get("min_valid_frames_per_camera", 10))
            ),
            max_reprojection_error_px=float(
                quality_payload.get("max_reprojection_error_px", payload.get("max_reprojection_error_px", 6.0))
            ),
            marker_outlier_translation_m=float(
                quality_payload.get("marker_outlier_translation_m", payload.get("marker_outlier_translation_m", 0.06))
            ),
            marker_outlier_rotation_deg=float(
                quality_payload.get("marker_outlier_rotation_deg", payload.get("marker_outlier_rotation_deg", 8.0))
            ),
            frame_outlier_translation_m=float(
                quality_payload.get("frame_outlier_translation_m", payload.get("frame_outlier_translation_m", 0.08))
            ),
            frame_outlier_rotation_deg=float(
                quality_payload.get("frame_outlier_rotation_deg", payload.get("frame_outlier_rotation_deg", 10.0))
            ),
            max_translation_std_m=float(
                quality_payload.get("max_translation_std_m", payload.get("max_translation_std_m", 0.03))
            ),
            max_rotation_std_deg=float(
                quality_payload.get("max_rotation_std_deg", payload.get("max_rotation_std_deg", 3.5))
            ),
            depth_distance_tolerance_m=float(
                quality_payload.get("depth_distance_tolerance_m", payload.get("depth_distance_tolerance_m", 0.08))
            ),
            depth_distance_tolerance_pct=float(
                quality_payload.get("depth_distance_tolerance_pct", payload.get("depth_distance_tolerance_pct", 12.0))
            ),
        )

        debug = DebugConfig(
            enabled=bool(debug_payload.get("enabled", payload.get("debug", False))),
            show_windows=bool(debug_payload.get("show_windows", False)),
            save_images=bool(debug_payload.get("save_images", True)),
            image_format=str(debug_payload.get("image_format", "jpg")),
        )

        camera = CameraTuningConfig(
            color_auto_exposure=bool(camera_payload.get("color_auto_exposure", True)),
            color_exposure=cls._parse_optional_int(camera_payload.get("color_exposure")),
            color_gain=cls._parse_optional_int(camera_payload.get("color_gain")),
            color_auto_white_balance=bool(camera_payload.get("color_auto_white_balance", True)),
            color_white_balance=cls._parse_optional_int(camera_payload.get("color_white_balance")),
            color_brightness=cls._parse_optional_int(camera_payload.get("color_brightness")),
        )

        config = cls(
            output=Path(str(payload.get("output", "calib_out"))),
            aruco_dict=str(payload.get("dict", "DICT_4X4_50")),
            cube=CubeConfig(
                marker_length=float(cube_payload["marker_length"]),
                cube_length=float(cube_payload["cube_length"]),
            ),
            face_ids={str(k): int(v) for k, v in face_payload.items()},
            color_resolution=cls._parse_resolution(payload.get("color_res", "3840x2160")),
            depth_resolution=cls._parse_resolution(payload.get("depth_res", "640x576")),
            fps=int(payload.get("fps", 30)),
            frame_count=int(payload.get("frame_count", 60)),
            warmup_frames=int(payload.get("warmup_frames", 5)),
            max_cameras=int(payload.get("max_cameras", 6)),
            world_origin=str(payload.get("world_origin", "cube_center")),
            use_depth=bool(payload.get("use_depth", False)),
            camera_ids=[str(x) for x in payload.get("camera_ids", [])] or None,
            camera=camera,
            network_camera=NetworkCameraDiscoveryConfig.from_mapping(network_camera_payload),
            quality=quality,
            debug=debug,
        )
        config.validate()
        return config

    def validate(self) -> None:
        self.cube.validate()
        self.camera.validate()
        self.network_camera.validate()
        self.quality.validate()

        if self.fps <= 0:
            raise ValueError("fps must be > 0")
        if self.frame_count <= 0:
            raise ValueError("frame_count must be > 0")
        if self.warmup_frames < 0:
            raise ValueError("warmup_frames must be >= 0")
        if self.max_cameras < 1:
            raise ValueError("max_cameras must be >= 1")
        if self.world_origin != "cube_center":
            raise ValueError("Only world_origin='cube_center' is currently supported")

        missing_faces = [face for face in REQUIRED_FACES if face not in self.face_ids]
        if missing_faces:
            raise ValueError(f"Missing face IDs for faces: {missing_faces}")

        face_ids = [self.face_ids[face] for face in REQUIRED_FACES]
        if len(set(face_ids)) != len(face_ids):
            raise ValueError("face_ids values must be unique")

        if not all(marker_id >= 0 for marker_id in face_ids):
            raise ValueError("face_ids must be non-negative integers")

        if not hasattr(cv2, "aruco"):
            raise RuntimeError("OpenCV ArUco module is not available (install opencv-contrib-python)")

        if not hasattr(cv2.aruco, self.aruco_dict):
            raise ValueError(f"Unsupported ArUco dictionary name: {self.aruco_dict}")

    def aruco_dictionary_id(self) -> int:
        return int(getattr(cv2.aruco, self.aruco_dict))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": str(self.output),
            "dict": self.aruco_dict,
            "cube": {
                "marker_length": self.cube.marker_length,
                "cube_length": self.cube.cube_length,
            },
            "face_ids": self.face_ids,
            "color_res": f"{self.color_resolution[0]}x{self.color_resolution[1]}",
            "depth_res": f"{self.depth_resolution[0]}x{self.depth_resolution[1]}",
            "fps": self.fps,
            "frame_count": self.frame_count,
            "warmup_frames": self.warmup_frames,
            "max_cameras": self.max_cameras,
            "world_origin": self.world_origin,
            "use_depth": self.use_depth,
            "camera_ids": self.camera_ids,
            "camera": self.camera.to_dict(),
            "network_camera": self.network_camera.to_dict(),
            "quality": {
                "min_markers_per_frame": self.quality.min_markers_per_frame,
                "min_valid_frames_per_camera": self.quality.min_valid_frames_per_camera,
                "max_reprojection_error_px": self.quality.max_reprojection_error_px,
                "marker_outlier_translation_m": self.quality.marker_outlier_translation_m,
                "marker_outlier_rotation_deg": self.quality.marker_outlier_rotation_deg,
                "frame_outlier_translation_m": self.quality.frame_outlier_translation_m,
                "frame_outlier_rotation_deg": self.quality.frame_outlier_rotation_deg,
                "max_translation_std_m": self.quality.max_translation_std_m,
                "max_rotation_std_deg": self.quality.max_rotation_std_deg,
                "depth_distance_tolerance_m": self.quality.depth_distance_tolerance_m,
                "depth_distance_tolerance_pct": self.quality.depth_distance_tolerance_pct,
            },
            "debug": {
                "enabled": self.debug.enabled,
                "show_windows": self.debug.show_windows,
                "save_images": self.debug.save_images,
                "image_format": self.debug.image_format,
            },
        }


def load_config(path: Path) -> CalibrationConfig:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return CalibrationConfig.from_dict(payload)
