from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import numpy.typing as npt

ArrayF64 = npt.NDArray[np.float64]


@dataclass
class CameraIntrinsics:
    camera_matrix: ArrayF64
    dist_coeffs: ArrayF64
    width: int
    height: int

    def validate(self) -> None:
        if self.camera_matrix.shape != (3, 3):
            raise ValueError("camera_matrix must have shape (3, 3)")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("intrinsics width/height must be positive")


@dataclass
class SimulatedMarkerPose:
    marker_id: int
    rvec: ArrayF64
    tvec: ArrayF64
    reprojection_error_px: float = 0.1
    confidence: float = 1.0


@dataclass
class CameraFrame:
    camera_id: str
    frame_index: int
    timestamp_ns: int
    color: Optional[npt.NDArray[np.uint8]] = None
    color_jpeg: bytes | None = None
    depth: Optional[npt.NDArray[np.uint16]] = None
    depth_scale_m: float | None = None
    simulated_marker_poses: Optional[List[SimulatedMarkerPose]] = field(default=None)


class CameraDevice(ABC):
    """Abstract camera interface used by the calibration pipeline."""

    @property
    @abstractmethod
    def camera_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_intrinsics(self) -> CameraIntrinsics:
        raise NotImplementedError

    @abstractmethod
    def get_frame(self, timeout_ms: int = 1000) -> Optional[CameraFrame]:
        raise NotImplementedError

    def get_depth_intrinsics(self) -> Optional[CameraIntrinsics]:
        return None

    def get_depth_to_color_transform(self) -> npt.NDArray[np.float64] | None:
        return None

    @property
    def serial_number(self) -> str:
        return ""

    @property
    def device_name(self) -> str:
        return ""

    @property
    def connection_type(self) -> str:
        return "unknown"
