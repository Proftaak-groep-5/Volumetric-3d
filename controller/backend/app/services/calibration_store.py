from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class CameraExtrinsics:
    camera_id: str
    t_camera_world: np.ndarray


class CalibrationStore:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._extrinsics: dict[str, CameraExtrinsics] = {}

    @property
    def calibration_file(self) -> Path:
        return self._file_path

    def load(self) -> None:
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        cameras = payload.get("cameras", [])
        extrinsics: dict[str, CameraExtrinsics] = {}

        for item in cameras:
            if not item.get("success", False):
                continue

            camera_id = str(item.get("camera_id", "")).strip()
            if not camera_id:
                continue

            matrix = item.get("T_camera_world")
            if matrix is None:
                world_camera = item.get("T_world_camera")
                if world_camera is None:
                    continue
                matrix = np.linalg.inv(np.asarray(world_camera, dtype=np.float64)).tolist()

            t_camera_world = np.asarray(matrix, dtype=np.float64)
            if t_camera_world.shape != (4, 4):
                continue

            extrinsics[camera_id] = CameraExtrinsics(camera_id=camera_id, t_camera_world=t_camera_world)

        self._extrinsics = extrinsics

    def get(self, camera_id: str) -> CameraExtrinsics | None:
        return self._extrinsics.get(camera_id)

    def all_camera_ids(self) -> list[str]:
        return list(self._extrinsics.keys())
