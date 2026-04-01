"""Orbbec camera connection helpers."""
from typing import Optional

import cv2
import numpy as np

try:
    from pyorbbecsdk import Context, Pipeline, Config, OBSensorType, OBFormat
except Exception:
    Context = None
    Pipeline = None
    Config = None
    OBSensorType = None
    OBFormat = None


def ensure_orbbec_available() -> None:
    if Context is None:
        raise RuntimeError(
            "pyorbbecsdk is not available. Install it or use --images mode."
        )


def get_best_color_profile(profiles, width: int, height: int, fps: int):
    formats = [OBFormat.RGB, OBFormat.YUYV, OBFormat.MJPG]
    for fmt in formats:
        try:
            return profiles.get_video_stream_profile(width, height, fmt, fps)
        except Exception:
            continue
    fallback = [(1920, 1080, 30), (1280, 720, 30), (640, 480, 30)]
    for w, h, f in fallback:
        for fmt in formats:
            try:
                return profiles.get_video_stream_profile(w, h, fmt, f)
            except Exception:
                continue
    return None


def convert_color_frame(color_frame) -> Optional[np.ndarray]:
    if color_frame is None:
        return None
    data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
    image = data.reshape((color_frame.get_height(), color_frame.get_width(), -1))
    if image.shape[2] == 2:
        image = cv2.cvtColor(image, cv2.COLOR_YUV2BGR_YUYV)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image
