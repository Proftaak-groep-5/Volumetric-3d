from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CameraInfo(BaseModel):
    camera_id: str
    serial_number: str | None = None
    device_name: str | None = None
    connection_type: str | None = None
    width: int
    height: int
    fps: int
    connected: bool
    stream_url: str
    snapshot_url: str
    log_ws_url: str | None = None


class CameraListResponse(BaseModel):
    cameras: list[CameraInfo]


class PointObservation(BaseModel):
    camera_id: str = Field(..., min_length=1)
    u: float
    v: float


class CreateVolumetricPointRequest(BaseModel):
    observations: list[PointObservation] = Field(..., min_length=2)


class CreateVolumetricPointResponse(BaseModel):
    point_world_xyz: list[float]
    point_unity_xyz: list[float]
    cameras_used: list[str]
    reprojection_error_px: dict[str, float]
    debug: dict[str, Any] | None = None


class CreateVolumetricCaptureRequest(BaseModel):
    camera_ids: list[str] | None = None
    pixel_step: int | None = Field(default=None, ge=1, le=32)
    depth_min_m: float | None = Field(default=None, gt=0.0)
    depth_max_m: float | None = Field(default=None, gt=0.0)


class CreateVolumetricCaptureResponse(BaseModel):
    capture_file_path: str
    preview_image_path: str
    capture_file_url: str
    preview_image_url: str
    points_total: int
    points_per_camera: dict[str, int]
    cameras_used: list[str]
    debug: dict[str, Any] | None = None


class DepthRgbBaselineEntry(BaseModel):
    ok: bool
    reason: str | None = None
    delta_translation_m: float | None = None
    delta_x_m: float | None = None
    calib_x_m: float | None = None
    sdk_x_m: float | None = None
    tolerance_m: float | None = None


class DepthRgbBaselineResponse(BaseModel):
    tolerance_m: float
    results: dict[str, DepthRgbBaselineEntry]


class ConfigureNetworkCamerasRequest(BaseModel):
    camera_ids: list[str] | None = None


class ConfigureNetworkCamerasResponse(BaseModel):
    results: dict[str, dict[str, Any]]


class CalibrationRunStatusResponse(BaseModel):
    state: str
    running: bool
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    return_code: int | None = None
    message: str | None = None
    command: list[str] | None = None
    log_file: str | None = None
    output_tail: str | None = None


class StartCalibrationResponse(BaseModel):
    accepted: bool
    status: CalibrationRunStatusResponse


class RecordingStatusResponse(BaseModel):
    running: bool
    can_start: bool
    disable_reasons: list[str]
    calibration_file: str
    calibration_file_exists: bool
    selected_output_dir: str | None = None
    output_dir_empty: bool | None = None
    active_output_dir: str | None = None
    start_unix_seconds: int | None = None
    started_at_utc: str | None = None
    stopped_at_utc: str | None = None
    target_fps: int | None = None
    frames_written: int
    failed_frames: int
    last_error: str | None = None
    camera_ids: list[str]


class PickRecordingOutputDirectoryResponse(BaseModel):
    selected_output_dir: str | None = None
    cancelled: bool


class StartRecordingRequest(BaseModel):
    output_dir: str = Field(..., min_length=1)
    camera_ids: list[str] | None = None
    depth_min_m: float | None = Field(default=None, gt=0.0)
    depth_max_m: float | None = Field(default=None, gt=0.0)


class StartRecordingResponse(BaseModel):
    accepted: bool
    status: RecordingStatusResponse


class StopRecordingResponse(BaseModel):
    accepted: bool
    status: RecordingStatusResponse


class EmailCaptureRequest(BaseModel):
    email: str = Field(..., min_length=3)
    capture_file_name: str | None = None


class EmailCaptureResponse(BaseModel):
    accepted: bool
    message: str
