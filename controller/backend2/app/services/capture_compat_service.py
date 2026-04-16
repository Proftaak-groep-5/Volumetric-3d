from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


class CalibrationCaptureCompatService:
    """Compatibility layer for legacy calibration capture endpoints."""

    def __init__(self, capture_dir: Path) -> None:
        self._capture_dir = capture_dir
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        self._captured: list[dict[str, Any]] = []

    def capture(
        self,
        camera_id_1: str,
        camera_id_2: str,
        img_1_rgb: np.ndarray,
        img_2_rgb: np.ndarray,
        timestamp: float,
    ) -> dict[str, Any]:
        index = len(self._captured)

        img1_bgr = cv2.cvtColor(img_1_rgb, cv2.COLOR_RGB2BGR)
        img2_bgr = cv2.cvtColor(img_2_rgb, cv2.COLOR_RGB2BGR)

        img1_path = self._capture_dir / f"{camera_id_1}_{index:03d}.png"
        img2_path = self._capture_dir / f"{camera_id_2}_{index:03d}.png"
        cv2.imwrite(str(img1_path), img1_bgr)
        cv2.imwrite(str(img2_path), img2_bgr)

        item = {
            "index": index,
            "camera_id_1": camera_id_1,
            "camera_id_2": camera_id_2,
            "timestamp": timestamp,
            "checkerboard_found": True,
        }
        self._captured.append(item)

        return {
            "success": True,
            "image_index": index,
            "total_captured": len(self._captured),
            "checkerboard_found": True,
        }

    def status(self) -> dict[str, Any]:
        return {"total_captured": len(self._captured), "images": list(self._captured)}

    def clear(self) -> dict[str, Any]:
        for image_file in self._capture_dir.glob("*.png"):
            try:
                image_file.unlink()
            except Exception:
                pass
        self._captured = []
        return {"success": True, "message": "Calibration captures cleared"}

    @property
    def capture_count(self) -> int:
        return len(self._captured)
