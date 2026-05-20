from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import numpy.typing as npt

ArrayF64 = npt.NDArray[np.float64]


def make_transform(rotation: ArrayF64, translation: Sequence[float]) -> ArrayF64:
    rotation = np.asarray(rotation, dtype=np.float64)
    translation = np.asarray(translation, dtype=np.float64).reshape(3)

    if rotation.shape != (3, 3):
        raise ValueError("rotation must have shape (3, 3)")

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform


def compose_transforms(*transforms: ArrayF64) -> ArrayF64:
    if not transforms:
        return np.eye(4, dtype=np.float64)

    result = np.eye(4, dtype=np.float64)
    for transform in transforms:
        result = result @ np.asarray(transform, dtype=np.float64)
    return result


def invert_transform(transform: ArrayF64) -> ArrayF64:
    transform = np.asarray(transform, dtype=np.float64)
    if transform.shape != (4, 4):
        raise ValueError("transform must have shape (4, 4)")

    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    inv_rotation = rotation.T
    inv_translation = -(inv_rotation @ translation)

    inv = np.eye(4, dtype=np.float64)
    inv[:3, :3] = inv_rotation
    inv[:3, 3] = inv_translation
    return inv


def rvec_tvec_to_transform(rvec: Sequence[float], tvec: Sequence[float]) -> ArrayF64:
    rvec_arr = np.asarray(rvec, dtype=np.float64).reshape(3, 1)
    tvec_arr = np.asarray(tvec, dtype=np.float64).reshape(3)
    rotation, _ = cv2.Rodrigues(rvec_arr)
    return make_transform(rotation, tvec_arr)


def transform_to_rvec_tvec(transform: ArrayF64) -> Tuple[ArrayF64, ArrayF64]:
    transform = np.asarray(transform, dtype=np.float64)
    rotation = transform[:3, :3]
    translation = transform[:3, 3].reshape(3, 1)
    rvec, _ = cv2.Rodrigues(rotation)
    return rvec.reshape(3), translation.reshape(3)


def extract_rotation_translation(transform: ArrayF64) -> Tuple[ArrayF64, ArrayF64]:
    transform = np.asarray(transform, dtype=np.float64)
    return transform[:3, :3].copy(), transform[:3, 3].copy()


def is_rigid_transform(transform: ArrayF64, atol: float = 1e-6) -> bool:
    transform = np.asarray(transform, dtype=np.float64)
    if transform.shape != (4, 4):
        return False

    bottom = transform[3, :]
    if not np.allclose(bottom, np.array([0.0, 0.0, 0.0, 1.0]), atol=atol):
        return False

    rotation = transform[:3, :3]
    should_be_identity = rotation.T @ rotation
    if not np.allclose(should_be_identity, np.eye(3), atol=atol):
        return False

    det = np.linalg.det(rotation)
    return abs(det - 1.0) <= 1e-4


def rotation_matrix_to_quaternion(rotation: ArrayF64) -> ArrayF64:
    rotation = np.asarray(rotation, dtype=np.float64)
    if rotation.shape != (3, 3):
        raise ValueError("rotation must have shape (3, 3)")

    m00, m01, m02 = rotation[0, 0], rotation[0, 1], rotation[0, 2]
    m10, m11, m12 = rotation[1, 0], rotation[1, 1], rotation[1, 2]
    m20, m21, m22 = rotation[2, 0], rotation[2, 1], rotation[2, 2]

    trace = m00 + m11 + m22

    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (m21 - m12) / s
        qy = (m02 - m20) / s
        qz = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        qw = (m21 - m12) / s
        qx = 0.25 * s
        qy = (m01 + m10) / s
        qz = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        qw = (m02 - m20) / s
        qx = (m01 + m10) / s
        qy = 0.25 * s
        qz = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        qw = (m10 - m01) / s
        qx = (m02 + m20) / s
        qy = (m12 + m21) / s
        qz = 0.25 * s

    quat = np.array([qw, qx, qy, qz], dtype=np.float64)
    return quat / np.linalg.norm(quat)


def quaternion_to_rotation_matrix(quat: Sequence[float]) -> ArrayF64:
    quat_arr = np.asarray(quat, dtype=np.float64).reshape(4)
    norm = np.linalg.norm(quat_arr)
    if norm == 0:
        raise ValueError("Quaternion must have non-zero norm")

    w, x, y, z = quat_arr / norm

    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def average_rotations(rotations: Iterable[ArrayF64], weights: Optional[Sequence[float]] = None) -> ArrayF64:
    rotation_list = [np.asarray(rotation, dtype=np.float64) for rotation in rotations]
    if not rotation_list:
        raise ValueError("No rotations provided")

    if weights is None:
        weights_arr = np.ones(len(rotation_list), dtype=np.float64)
    else:
        weights_arr = np.asarray(weights, dtype=np.float64)
        if weights_arr.shape[0] != len(rotation_list):
            raise ValueError("weights size must match number of rotations")

    weight_sum = np.sum(weights_arr)
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive value")
    weights_arr = weights_arr / weight_sum

    quats: List[ArrayF64] = [rotation_matrix_to_quaternion(rotation) for rotation in rotation_list]
    reference = quats[0]
    for idx in range(len(quats)):
        if np.dot(quats[idx], reference) < 0:
            quats[idx] = -quats[idx]

    accumulator = np.zeros((4, 4), dtype=np.float64)
    for weight, quat in zip(weights_arr, quats):
        accumulator += weight * np.outer(quat, quat)

    eigvals, eigvecs = np.linalg.eigh(accumulator)
    avg_quat = eigvecs[:, np.argmax(eigvals)]
    if avg_quat[0] < 0:
        avg_quat = -avg_quat

    return quaternion_to_rotation_matrix(avg_quat)


def average_transforms(transforms: Iterable[ArrayF64], weights: Optional[Sequence[float]] = None) -> ArrayF64:
    transform_list = [np.asarray(transform, dtype=np.float64) for transform in transforms]
    if not transform_list:
        raise ValueError("No transforms provided")

    if weights is None:
        weights_arr = np.ones(len(transform_list), dtype=np.float64)
    else:
        weights_arr = np.asarray(weights, dtype=np.float64)
        if weights_arr.shape[0] != len(transform_list):
            raise ValueError("weights size must match number of transforms")

    weight_sum = np.sum(weights_arr)
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive value")
    weights_arr = weights_arr / weight_sum

    rotations = [transform[:3, :3] for transform in transform_list]
    translations = np.array([transform[:3, 3] for transform in transform_list], dtype=np.float64)

    avg_rotation = average_rotations(rotations, weights_arr)
    avg_translation = np.average(translations, axis=0, weights=weights_arr)

    return make_transform(avg_rotation, avg_translation)


def rotation_angle_deg(rotation_a: ArrayF64, rotation_b: ArrayF64) -> float:
    rotation_a = np.asarray(rotation_a, dtype=np.float64)
    rotation_b = np.asarray(rotation_b, dtype=np.float64)
    rel = rotation_a.T @ rotation_b
    trace = float(np.trace(rel))
    cos_angle = np.clip((trace - 1.0) / 2.0, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def transform_delta(transform_a: ArrayF64, transform_b: ArrayF64) -> Tuple[float, float]:
    transform_a = np.asarray(transform_a, dtype=np.float64)
    transform_b = np.asarray(transform_b, dtype=np.float64)

    translation_delta = float(np.linalg.norm(transform_a[:3, 3] - transform_b[:3, 3]))
    rotation_delta = rotation_angle_deg(transform_a[:3, :3], transform_b[:3, :3])
    return translation_delta, rotation_delta
