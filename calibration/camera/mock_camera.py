from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
import numpy.typing as npt

from calibration.calibration.aruco_cube import ArucoCubeModel
from calibration.camera.base import CameraDevice, CameraFrame, CameraIntrinsics, SimulatedMarkerPose
from calibration.math3d.transforms import invert_transform, make_transform, transform_to_rvec_tvec

ArrayF64 = npt.NDArray[np.float64]


@dataclass
class MockCameraSpec:
    camera_id: str
    t_camera_world: ArrayF64


def _normalize(vec: ArrayF64) -> ArrayF64:
    norm = float(np.linalg.norm(vec))
    if norm <= np.finfo(np.float64).eps:
        raise ValueError("Cannot normalize zero-length vector")
    return vec / norm


def _look_at_world_to_camera(position_world: Sequence[float], target_world: Sequence[float], up_world: Sequence[float]) -> ArrayF64:
    position = np.asarray(position_world, dtype=np.float64).reshape(3)
    target = np.asarray(target_world, dtype=np.float64).reshape(3)
    up = np.asarray(up_world, dtype=np.float64).reshape(3)

    z_axis = _normalize(target - position)
    x_axis = _normalize(np.cross(z_axis, up))
    y_axis = _normalize(np.cross(x_axis, z_axis))

    rotation = np.vstack([x_axis, y_axis, z_axis])
    translation = -(rotation @ position)
    return make_transform(rotation, translation)


class MockCamera(CameraDevice):
    def __init__(
        self,
        spec: MockCameraSpec,
        cube_model: ArucoCubeModel,
        resolution: Tuple[int, int],
        fps: int,
        marker_position_noise_m: float = 0.003,
        marker_rotation_noise_deg: float = 0.4,
        marker_dropout_probability: float = 0.2,
        seed: int = 42,
    ) -> None:
        self._camera_id = spec.camera_id
        self._t_camera_world = np.asarray(spec.t_camera_world, dtype=np.float64)
        self._cube_model = cube_model
        self._width, self._height = int(resolution[0]), int(resolution[1])
        self._fps = int(fps)

        self._marker_position_noise_m = float(marker_position_noise_m)
        self._marker_rotation_noise_deg = float(marker_rotation_noise_deg)
        self._marker_dropout_probability = float(marker_dropout_probability)

        self._rng = np.random.default_rng(seed=seed)
        self._frame_index = 0
        self._running = False

        fx = fy = 0.9 * float(max(self._width, self._height))
        cx = self._width / 2.0
        cy = self._height / 2.0
        camera_matrix = np.array(
            [
                [fx, 0.0, cx],
                [0.0, fy, cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        dist = np.zeros((5,), dtype=np.float64)
        self._intrinsics = CameraIntrinsics(camera_matrix=camera_matrix, dist_coeffs=dist, width=self._width, height=self._height)

    @property
    def camera_id(self) -> str:
        return self._camera_id

    def start(self) -> None:
        self._running = True
        self._frame_index = 0

    def stop(self) -> None:
        self._running = False

    def get_intrinsics(self) -> CameraIntrinsics:
        return self._intrinsics

    def get_frame(self, timeout_ms: int = 1000) -> Optional[CameraFrame]:
        if not self._running:
            return None

        # Simulate a hardware frame interval.
        if self._fps > 0:
            time.sleep(1.0 / float(self._fps))

        marker_poses = self._simulate_visible_marker_poses()
        color = self._render_synthetic_frame(marker_poses)

        frame = CameraFrame(
            camera_id=self._camera_id,
            frame_index=self._frame_index,
            timestamp_ns=time.time_ns(),
            color=color,
            depth=None,
            simulated_marker_poses=marker_poses,
        )
        self._frame_index += 1
        return frame

    def _simulate_visible_marker_poses(self) -> List[SimulatedMarkerPose]:
        visible_marker_poses: List[SimulatedMarkerPose] = []

        t_world_camera = invert_transform(self._t_camera_world)
        camera_position_world = t_world_camera[:3, 3]

        face_normals = self._cube_model.face_normals_cube_frame()

        for marker_id in self._cube_model.marker_ids():
            face_transform = self._cube_model.get_transform_for_marker_id(marker_id)
            t_world_marker = face_transform.t_cube_marker
            face_name = face_transform.face_name

            marker_center_world = t_world_marker[:3, 3]
            face_normal_world = face_normals[face_name]

            # Marker should face the camera and also project in front of the camera.
            if np.dot(face_normal_world, camera_position_world - marker_center_world) <= 0.0:
                continue

            t_camera_marker = self._t_camera_world @ t_world_marker
            marker_center_camera = t_camera_marker[:3, 3]
            if marker_center_camera[2] <= 0.15:
                continue

            projected = self._project_point(marker_center_camera)
            if projected is None:
                continue
            px, py = projected
            margin = 60
            if not (-margin <= px < self._width + margin and -margin <= py < self._height + margin):
                continue

            if self._rng.random() < self._marker_dropout_probability:
                continue

            rvec, tvec = transform_to_rvec_tvec(t_camera_marker)

            tvec_noise = self._rng.normal(loc=0.0, scale=self._marker_position_noise_m, size=(3,))
            rvec_noise = self._rng.normal(
                loc=0.0,
                scale=np.radians(self._marker_rotation_noise_deg),
                size=(3,),
            )

            noisy_tvec = tvec + tvec_noise
            noisy_rvec = rvec + rvec_noise

            reproj_error = float(np.clip(self._rng.normal(loc=0.35, scale=0.15), 0.08, 1.2))
            confidence = float(np.clip(1.0 - reproj_error / 2.0, 0.4, 1.0))

            visible_marker_poses.append(
                SimulatedMarkerPose(
                    marker_id=int(marker_id),
                    rvec=noisy_rvec.astype(np.float64),
                    tvec=noisy_tvec.astype(np.float64),
                    reprojection_error_px=reproj_error,
                    confidence=confidence,
                )
            )

        # Keep at least one marker to let mock runs progress unless everything is out of view.
        if not visible_marker_poses:
            marker_id = int(next(iter(self._cube_model.marker_ids())))
            face_transform = self._cube_model.get_transform_for_marker_id(marker_id)
            t_camera_marker = self._t_camera_world @ face_transform.t_cube_marker
            rvec, tvec = transform_to_rvec_tvec(t_camera_marker)
            visible_marker_poses.append(
                SimulatedMarkerPose(
                    marker_id=marker_id,
                    rvec=rvec.astype(np.float64),
                    tvec=tvec.astype(np.float64),
                    reprojection_error_px=0.6,
                    confidence=0.5,
                )
            )

        return visible_marker_poses

    def _project_point(self, point_camera: ArrayF64) -> Optional[Tuple[float, float]]:
        z = float(point_camera[2])
        if z <= 1e-6:
            return None
        fx = self._intrinsics.camera_matrix[0, 0]
        fy = self._intrinsics.camera_matrix[1, 1]
        cx = self._intrinsics.camera_matrix[0, 2]
        cy = self._intrinsics.camera_matrix[1, 2]
        x = float(fx * point_camera[0] / z + cx)
        y = float(fy * point_camera[1] / z + cy)
        return x, y

    def _render_synthetic_frame(self, marker_poses: List[SimulatedMarkerPose]) -> npt.NDArray[np.uint8]:
        image = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        image[:, :] = (18, 18, 18)

        for idx, marker in enumerate(marker_poses):
            tvec = marker.tvec
            projected = self._project_point(tvec)
            if projected is None:
                continue
            px, py = int(projected[0]), int(projected[1])
            color = (80 + (idx * 53) % 120, 180, 80)
            cv2.circle(image, (px, py), 10, color, -1, lineType=cv2.LINE_AA)
            cv2.putText(
                image,
                f"id={marker.marker_id}",
                (px + 12, py - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )

        cv2.putText(
            image,
            f"{self._camera_id} frame={self._frame_index}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            "MOCK MODE",
            (20, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 200, 255),
            2,
            cv2.LINE_AA,
        )
        return image


def create_mock_cameras(
    camera_count: int,
    cube_model: ArucoCubeModel,
    color_resolution: Tuple[int, int],
    fps: int,
    seed: int = 42,
) -> List[MockCamera]:
    if camera_count < 1 or camera_count > 6:
        raise ValueError("camera_count must be between 1 and 6")

    specs: List[MockCameraSpec] = []

    radius = 1.8
    for idx in range(camera_count):
        angle = 2.0 * np.pi * float(idx) / float(camera_count)
        position_world = np.array(
            [
                radius * np.cos(angle),
                0.45 + 0.2 * np.sin(2.0 * angle),
                radius * np.sin(angle),
            ],
            dtype=np.float64,
        )
        target_world = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        up_world = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        t_camera_world = _look_at_world_to_camera(position_world, target_world, up_world)
        specs.append(MockCameraSpec(camera_id=f"mock_cam{idx}", t_camera_world=t_camera_world))

    cameras = [
        MockCamera(
            spec=spec,
            cube_model=cube_model,
            resolution=color_resolution,
            fps=fps,
            seed=seed + idx,
        )
        for idx, spec in enumerate(specs)
    ]
    return cameras

