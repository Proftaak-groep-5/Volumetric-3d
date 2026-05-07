from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from pathlib import Path

from app.core.path_setup import ensure_repo_root_on_path

if TYPE_CHECKING:
    from calibration.camera.network_api import NetworkCameraDiscoveryConfig


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    cors_allowed_origins: list[str]
    calibration_file: Path
    color_width: int
    color_height: int
    depth_width: int
    depth_height: int
    fps: int
    use_depth: bool
    max_cameras: int
    volumetric_capture_output_dir: Path
    capture_output_url_prefix: str
    camera_tuning: dict[str, int | bool]
    network_camera: "NetworkCameraDiscoveryConfig"



def _parse_origins(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",")]
    return [value for value in values if value]


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return int(value)



def get_settings() -> Settings:
    repo_root = ensure_repo_root_on_path()
    from calibration.camera.network_api import NetworkCameraDiscoveryConfig

    calibration_default = repo_root / "calib_out" / "final_calibration.json"
    origins_default = "http://localhost:3000,http://127.0.0.1:3000"

    color_auto_exposure = os.getenv("CAMERA_COLOR_AUTO_EXPOSURE", "true").lower() in {"1", "true", "yes", "on"}
    color_auto_white_balance = os.getenv("CAMERA_COLOR_AUTO_WHITE_BALANCE", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    camera_tuning: dict[str, int | bool] = {
        "color_auto_exposure": color_auto_exposure,
        "color_auto_white_balance": color_auto_white_balance,
    }

    color_exposure = _parse_optional_int(os.getenv("CAMERA_COLOR_EXPOSURE", "120"))
    if color_exposure is not None:
        camera_tuning["color_exposure"] = color_exposure

    color_gain = _parse_optional_int(os.getenv("CAMERA_COLOR_GAIN", "0"))
    if color_gain is not None:
        camera_tuning["color_gain"] = color_gain

    color_brightness = _parse_optional_int(os.getenv("CAMERA_COLOR_BRIGHTNESS", "10"))
    if color_brightness is not None:
        camera_tuning["color_brightness"] = color_brightness

    color_white_balance = _parse_optional_int(os.getenv("CAMERA_COLOR_WHITE_BALANCE"))
    if color_white_balance is not None:
        camera_tuning["color_white_balance"] = color_white_balance

    network_camera = NetworkCameraDiscoveryConfig.from_mapping(
        {
            "enabled": os.getenv("NETWORK_CAMERA_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
            "subnet": os.getenv("NETWORK_CAMERA_SUBNET", "192.168.137.0/24"),
            "ips": os.getenv("NETWORK_CAMERA_IPS", ""),
            "ports": os.getenv("NETWORK_CAMERA_PORTS", "8080"),
            "timeout_ms": os.getenv("NETWORK_CAMERA_TIMEOUT_MS", "350"),
            "max_cameras": os.getenv("NETWORK_CAMERA_MAX_CAMERAS", "16"),
            "max_workers": os.getenv("NETWORK_CAMERA_MAX_WORKERS", "32"),
        }
    )
    network_camera.validate()

    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        cors_allowed_origins=_parse_origins(os.getenv("CORS_ALLOWED_ORIGINS", origins_default)),
        calibration_file=Path(os.getenv("CALIBRATION_FILE", str(calibration_default))).resolve(),
        color_width=int(os.getenv("CAMERA_COLOR_WIDTH", "3840")),
        color_height=int(os.getenv("CAMERA_COLOR_HEIGHT", "2160")),
        depth_width=int(os.getenv("CAMERA_DEPTH_WIDTH", "640")),
        depth_height=int(os.getenv("CAMERA_DEPTH_HEIGHT", "576")),
        fps=int(os.getenv("CAMERA_FPS", "30")),
        use_depth=os.getenv("CAMERA_USE_DEPTH", "true").lower() in {"1", "true", "yes", "on"},
        max_cameras=int(os.getenv("MAX_CAMERAS", "6")),
        volumetric_capture_output_dir=Path(
            os.getenv("VOLUMETRIC_CAPTURE_OUTPUT_DIR", str(repo_root / "calib_out" / "captures"))
        ).resolve(),
        capture_output_url_prefix=os.getenv("CAPTURE_OUTPUT_URL_PREFIX", "/captures").strip() or "/captures",
        camera_tuning=camera_tuning,
        network_camera=network_camera,
    )
