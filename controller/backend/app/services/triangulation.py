from __future__ import annotations

import numpy as np

from app.schemas import PointObservation
from app.services.calibration_store import CalibrationStore
from app.services.camera_stream_manager import CameraStreamManager


class TriangulationService:
    def __init__(self, camera_manager: CameraStreamManager, calibration_store: CalibrationStore) -> None:
        self._camera_manager = camera_manager
        self._calibration_store = calibration_store

    def create_point(self, observations: list[PointObservation]) -> tuple[np.ndarray, dict[str, float]]:
        rows: list[np.ndarray] = []
        used: list[tuple[str, np.ndarray, float, float]] = []

        for observation in observations:
            camera_id = observation.camera_id
            extrinsics = self._calibration_store.get(camera_id)
            intrinsics = self._camera_manager.intrinsics(camera_id)
            if extrinsics is None or intrinsics is None:
                continue

            projection = intrinsics @ extrinsics.t_camera_world[:3, :]
            u = float(observation.u)
            v = float(observation.v)

            rows.append(u * projection[2, :] - projection[0, :])
            rows.append(v * projection[2, :] - projection[1, :])
            used.append((camera_id, projection, u, v))

        if len(used) < 2:
            raise ValueError("Need at least 2 observations with known intrinsics and calibration")

        matrix_a = np.vstack(rows)
        _, _, vt = np.linalg.svd(matrix_a)
        homogeneous = vt[-1, :]
        point_world = homogeneous[:3] / homogeneous[3]

        reprojection_error: dict[str, float] = {}
        point_h = np.array([point_world[0], point_world[1], point_world[2], 1.0], dtype=np.float64)
        for camera_id, projection, u, v in used:
            projected = projection @ point_h
            projected /= projected[2]
            error = float(np.sqrt((projected[0] - u) ** 2 + (projected[1] - v) ** 2))
            reprojection_error[camera_id] = error

        return point_world, reprojection_error

    @staticmethod
    def to_unity(point_world: np.ndarray) -> np.ndarray:
        return np.array([point_world[0], point_world[1], -point_world[2]], dtype=np.float64)
