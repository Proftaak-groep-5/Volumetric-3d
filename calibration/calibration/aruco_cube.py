from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import numpy.typing as npt

from calibration.config import REQUIRED_FACES
from calibration.math3d.transforms import make_transform

ArrayF64 = npt.NDArray[np.float64]


@dataclass(frozen=True)
class FaceTransform:
    face_name: str
    marker_id: int
    t_cube_marker: ArrayF64


class ArucoCubeModel:
    """
    Models a rigid ArUco cube with analytically derived per-face marker transforms.

    Transform convention used everywhere:
    - T_dst_src maps a point from src-frame coordinates into dst-frame coordinates.
    - x_dst = T_dst_src @ x_src_h

    This class stores T_cube_marker for each face/marker.
    """

    def __init__(self, cube_length: float, marker_length: float, face_ids: Dict[str, int]):
        if cube_length <= 0 or marker_length <= 0:
            raise ValueError("cube_length and marker_length must be > 0")
        if marker_length > cube_length:
            raise ValueError("marker_length should not be greater than cube_length")

        for face in REQUIRED_FACES:
            if face not in face_ids:
                raise ValueError(f"Missing marker ID for face '{face}'")

        self.cube_length = float(cube_length)
        self.marker_length = float(marker_length)
        self.face_ids = {face: int(face_ids[face]) for face in REQUIRED_FACES}

        marker_ids = list(self.face_ids.values())
        if len(set(marker_ids)) != len(marker_ids):
            raise ValueError("Marker IDs must be unique across cube faces")

        self._face_transforms = self._build_face_transforms()
        self._marker_id_to_face = {ft.marker_id: ft.face_name for ft in self._face_transforms.values()}

    @staticmethod
    def _rotation_from_axes(x_axis: Tuple[float, float, float], y_axis: Tuple[float, float, float], z_axis: Tuple[float, float, float]) -> ArrayF64:
        rotation = np.column_stack(
            [
                np.asarray(x_axis, dtype=np.float64),
                np.asarray(y_axis, dtype=np.float64),
                np.asarray(z_axis, dtype=np.float64),
            ]
        )
        # Enforce orthonormality for numerical robustness.
        u, _, vt = np.linalg.svd(rotation)
        rotation = u @ vt
        if np.linalg.det(rotation) < 0:
            rotation[:, 2] *= -1.0
        return rotation

    def _build_face_transforms(self) -> Dict[str, FaceTransform]:
        h = self.cube_length / 2.0

        # Marker axis convention:
        # marker +Z = outward normal from marker plane.
        # marker +X and +Y are in-plane axes, chosen per face to be consistent and right-handed.
        face_specs = {
            "front": {
                "center": (0.0, 0.0, +h),
                "axes": ((+1.0, 0.0, 0.0), (0.0, +1.0, 0.0), (0.0, 0.0, +1.0)),
            },
            "back": {
                "center": (0.0, 0.0, -h),
                "axes": ((-1.0, 0.0, 0.0), (0.0, +1.0, 0.0), (0.0, 0.0, -1.0)),
            },
            "right": {
                "center": (+h, 0.0, 0.0),
                "axes": ((0.0, 0.0, -1.0), (0.0, +1.0, 0.0), (+1.0, 0.0, 0.0)),
            },
            "left": {
                "center": (-h, 0.0, 0.0),
                "axes": ((0.0, 0.0, +1.0), (0.0, +1.0, 0.0), (-1.0, 0.0, 0.0)),
            },
            "top": {
                "center": (0.0, +h, 0.0),
                "axes": ((+1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, +1.0, 0.0)),
            },
            "bottom": {
                "center": (0.0, -h, 0.0),
                "axes": ((+1.0, 0.0, 0.0), (0.0, 0.0, +1.0), (0.0, -1.0, 0.0)),
            },
        }

        face_transforms: Dict[str, FaceTransform] = {}
        for face_name in REQUIRED_FACES:
            spec = face_specs[face_name]
            x_axis, y_axis, z_axis = spec["axes"]
            rotation = self._rotation_from_axes(x_axis, y_axis, z_axis)
            translation = np.asarray(spec["center"], dtype=np.float64)
            transform = make_transform(rotation, translation)

            face_transforms[face_name] = FaceTransform(
                face_name=face_name,
                marker_id=self.face_ids[face_name],
                t_cube_marker=transform,
            )

        return face_transforms

    def marker_id_to_face(self, marker_id: int) -> Optional[str]:
        return self._marker_id_to_face.get(int(marker_id))

    def get_face_transform(self, face_name: str) -> FaceTransform:
        if face_name not in self._face_transforms:
            raise KeyError(f"Unknown face: {face_name}")
        return self._face_transforms[face_name]

    def get_transform_for_marker_id(self, marker_id: int) -> FaceTransform:
        face = self.marker_id_to_face(marker_id)
        if face is None:
            raise KeyError(f"Marker ID {marker_id} is not part of this cube model")
        return self.get_face_transform(face)

    def marker_corners_marker_frame(self) -> ArrayF64:
        half = self.marker_length / 2.0
        return np.array(
            [
                [-half, +half, 0.0],
                [+half, +half, 0.0],
                [+half, -half, 0.0],
                [-half, -half, 0.0],
            ],
            dtype=np.float64,
        )

    def marker_ids(self) -> Iterable[int]:
        return self._marker_id_to_face.keys()

    def face_normals_cube_frame(self) -> Dict[str, ArrayF64]:
        normals: Dict[str, ArrayF64] = {}
        for face_name, face_transform in self._face_transforms.items():
            normals[face_name] = face_transform.t_cube_marker[:3, 2].copy()
        return normals

