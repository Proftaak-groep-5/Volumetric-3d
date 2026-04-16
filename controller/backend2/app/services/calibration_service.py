from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.domain.calibration_schema import CalibrationCameraEntry, FinalCalibrationDocument
from app.domain.models import CameraPose, StereoTransform


logger = logging.getLogger(__name__)
MAX_EXTERNAL_CALIBRATION_CAMERAS = 6


@dataclass(slots=True)
class CalibrationLoadState:
    loaded: bool
    source_path: str
    last_error: str | None
    last_loaded_timestamp_utc: str | None
    file_mtime_unix: float | None
    camera_count: int


class ExternalCalibrationService:
    """Load external camera poses from calib_out/final_calibration.json.

    Calibration solving is owned by calibration/main.py. This service only consumes
    the produced artifact and exposes runtime transforms.
    """

    def __init__(self, calibration_path: Path) -> None:
        self._calibration_path = calibration_path
        self._lock = threading.RLock()
        self._camera_poses: dict[str, CameraPose] = {}
        self._last_error: str | None = None
        self._last_loaded_timestamp_utc: str | None = None
        self._file_mtime_unix: float | None = None

    @property
    def calibration_path(self) -> Path:
        return self._calibration_path

    def _reset_load_state(self) -> None:
        self._camera_poses = {}
        self._last_error = None
        self._last_loaded_timestamp_utc = None
        self._file_mtime_unix = None

    def _camera_pose_from_entry(self, entry: CalibrationCameraEntry) -> CameraPose | None:
        if not entry.success or not entry.T_world_camera:
            return None

        t_world_camera = np.asarray(entry.T_world_camera, dtype=np.float64)
        if t_world_camera.shape != (4, 4):
            return None

        if entry.T_camera_world is not None:
            t_camera_world = np.asarray(entry.T_camera_world, dtype=np.float64)
        else:
            t_camera_world = np.linalg.inv(t_world_camera)

        if t_camera_world.shape != (4, 4):
            return None

        return CameraPose(
            camera_id=entry.camera_id,
            t_world_camera=t_world_camera,
            t_camera_world=t_camera_world,
        )

    def load(self) -> CalibrationLoadState:
        with self._lock:
            self._reset_load_state()

            if not self._calibration_path.exists():
                self._last_error = f"Calibration file not found: {self._calibration_path}"
                logger.warning(self._last_error)
                return self.get_state()

            try:
                self._file_mtime_unix = self._calibration_path.stat().st_mtime
                with self._calibration_path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)

                document = FinalCalibrationDocument.model_validate(payload)
                self._last_loaded_timestamp_utc = document.timestamp_utc

                for entry in document.cameras:
                    if len(self._camera_poses) >= MAX_EXTERNAL_CALIBRATION_CAMERAS:
                        logger.warning(
                            "Loaded maximum supported external calibration cameras (%d); extra entries are ignored",
                            MAX_EXTERNAL_CALIBRATION_CAMERAS,
                        )
                        break

                    pose = self._camera_pose_from_entry(entry)
                    if pose is None:
                        continue

                    self._camera_poses[pose.camera_id] = pose

                logger.info(
                    "Loaded external calibration from %s with %d successful camera poses",
                    self._calibration_path,
                    len(self._camera_poses),
                )
            except Exception as exc:
                self._last_error = f"Failed to load external calibration: {exc}"
                logger.exception(self._last_error)

            return self.get_state()

    def reload(self) -> CalibrationLoadState:
        return self.load()

    def get_state(self) -> CalibrationLoadState:
        with self._lock:
            return CalibrationLoadState(
                loaded=bool(self._camera_poses),
                source_path=str(self._calibration_path),
                last_error=self._last_error,
                last_loaded_timestamp_utc=self._last_loaded_timestamp_utc,
                file_mtime_unix=self._file_mtime_unix,
                camera_count=len(self._camera_poses),
            )

    def has_camera(self, camera_id: str) -> bool:
        with self._lock:
            return camera_id in self._camera_poses

    def get_camera_pose(self, camera_id: str) -> CameraPose | None:
        with self._lock:
            return self._camera_poses.get(camera_id)

    def list_camera_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._camera_poses.keys())

    def get_stereo_transform(self, camera_id_1: str, camera_id_2: str) -> StereoTransform | None:
        with self._lock:
            pose_1 = self._camera_poses.get(camera_id_1)
            pose_2 = self._camera_poses.get(camera_id_2)

            if pose_1 is None or pose_2 is None:
                return None

            r1 = pose_1.t_world_camera[:3, :3]
            t1 = pose_1.t_world_camera[:3, 3].reshape(3, 1)
            r2 = pose_2.t_world_camera[:3, :3]
            t2 = pose_2.t_world_camera[:3, 3].reshape(3, 1)

            r_21 = r2 @ r1.T
            t_21 = t2 - (r_21 @ t1)

            return StereoTransform(
                camera_id_1=camera_id_1,
                camera_id_2=camera_id_2,
                r=r_21,
                t=t_21,
            )
