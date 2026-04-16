from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration loaded from env vars and .env."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    recordings_path: Path = Path("./recordings")
    calibration_capture_path: Path = Path("./calibration_images")
    external_calibration_path: Path = REPO_ROOT / "calib_out" / "final_calibration.json"

    max_cameras: int = Field(default=6, ge=1, le=6)
    depth_width: int = 640
    depth_height: int = 576
    color_width: int = 1920
    color_height: int = 1080
    fps: int = 30

    ws_broadcast_interval_sec: float = Field(default=0.033, ge=0.001)
    ws_jpeg_quality_color: int = Field(default=85, ge=10, le=100)
    ws_jpeg_quality_depth: int = Field(default=90, ge=10, le=100)

    pointcloud_max_depth_m: float = Field(default=5.0, gt=0.1)
    pointcloud_sample_stride: int = Field(default=2, ge=1)

    cors_allow_origins: list[str] = ["*"]


settings = Settings()
settings.recordings_path.mkdir(parents=True, exist_ok=True)
settings.calibration_capture_path.mkdir(parents=True, exist_ok=True)
