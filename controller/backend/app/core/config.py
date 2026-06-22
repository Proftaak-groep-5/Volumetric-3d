from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING
from pathlib import Path

from app.core.path_setup import ensure_repo_root_on_path

if TYPE_CHECKING:
    from calibration.camera.network_api import NetworkCameraDiscoveryConfig


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    host: str
    port: int
    cors_allowed_origins: list[str]
    calibration_file: Path
    calibration_config_file: Path
    color_width: int
    color_height: int
    depth_width: int
    depth_height: int
    fps: int
    use_depth: bool
    max_cameras: int
    volumetric_capture_output_dir: Path
    capture_output_url_prefix: str
    blender_update_command: list[str] | None
    camera_tuning: dict[str, int | bool]
    network_camera: "NetworkCameraDiscoveryConfig"
    gmail_address: str | None
    gmail_app_password: str | None



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


def _parse_command(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return shlex.split(value, posix=os.name != "nt")


def _default_blender_update_command(repo_root: Path) -> list[str] | None:
    blender_file = repo_root / "blender" / "ColorCloud.blend"
    if not blender_file.exists():
        return None

    blender_executable = os.getenv("BLENDER_EXECUTABLE", "blender")
    return [
        blender_executable,
        str(blender_file),
        "--background",
        "--python-expr",
        "import bpy; exec(bpy.data.texts['Text.py'].as_string())",
    ]



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
            "ips": os.getenv("NETWORK_CAMERA_IPS", "127.0.0.1,localhost"),
            "ports": os.getenv("NETWORK_CAMERA_PORTS", "8080"),
            "timeout_ms": os.getenv("NETWORK_CAMERA_TIMEOUT_MS", "350"),
            "max_cameras": os.getenv("NETWORK_CAMERA_MAX_CAMERAS", "16"),
            "max_workers": os.getenv("NETWORK_CAMERA_MAX_WORKERS", "32"),
        }
    )
    network_camera.validate()

    blender_update_command = _parse_command(os.getenv("BLENDER_UPDATE_COMMAND"))
    if blender_update_command is None:
        blender_update_command = _default_blender_update_command(repo_root)

    return Settings(
        repo_root=repo_root.resolve(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        cors_allowed_origins=_parse_origins(os.getenv("CORS_ALLOWED_ORIGINS", origins_default)),
        calibration_file=Path(os.getenv("CALIBRATION_FILE", str(calibration_default))).resolve(),
        calibration_config_file=Path(
            os.getenv("CALIBRATION_CONFIG_FILE", str(repo_root / "calibration" / "calibration_config.json"))
        ).resolve(),
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
        blender_update_command=blender_update_command,
        camera_tuning=camera_tuning,
        network_camera=network_camera,
        gmail_address=os.getenv("GMAIL_ADDRESS"),
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD"),
    )