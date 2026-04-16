from __future__ import annotations

from pydantic import BaseModel


class CalibrationCameraEntry(BaseModel):
    camera_id: str
    success: bool = False
    message: str | None = None
    timestamp: str | None = None
    T_world_camera: list[list[float]] | None = None
    T_camera_world: list[list[float]] | None = None
    rotation_matrix_world_camera: list[list[float]] | None = None
    translation_world_camera: list[float] | None = None
    unity: dict | None = None
    markers_used: list[int] | None = None
    quality_metrics: dict | None = None


class FinalCalibrationDocument(BaseModel):
    timestamp_utc: str | None = None
    world_origin: str | None = None
    successful_cameras: int | None = None
    failed_cameras: int | None = None
    camera_count: int | None = None
    cameras: list[CalibrationCameraEntry] = []
