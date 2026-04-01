"""Live preview utilities for camera calibration."""
from typing import Tuple

import cv2

PREVIEW_SIZE: Tuple[int, int] = (384, 216)
MARKER_OUTLINE_THICKNESS = 2
ID_FONT_SCALE = 0.6
ID_TEXT_THICKNESS = 2


def show_preview(camera_id: str, color_bgr, corners, ids, size: Tuple[int, int] = PREVIEW_SIZE) -> None:
    preview = color_bgr.copy()
    preview = cv2.resize(preview, size, interpolation=cv2.INTER_AREA)
    if ids is not None and len(ids) > 0:
        scale_x = size[0] / color_bgr.shape[1]
        scale_y = size[1] / color_bgr.shape[0]
        scaled_corners = [corner.copy() for corner in corners]
        for corner in scaled_corners:
            corner[:, :, 0] *= scale_x
            corner[:, :, 1] *= scale_y
        for marker_id, corner in zip(ids.flatten(), scaled_corners):
            points = corner[0].astype(int)
            cv2.polylines(preview, [points], isClosed=True, color=(0, 255, 0), thickness=MARKER_OUTLINE_THICKNESS)
            center_x = int(points[:, 0].mean())
            center_y = int(points[:, 1].mean())
            cv2.putText(
                preview,
                str(int(marker_id)),
                (center_x + 6, center_y - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                ID_FONT_SCALE,
                (255, 0, 0),
                ID_TEXT_THICKNESS,
                cv2.LINE_AA,
            )
    cv2.imshow(f"{camera_id} preview", preview)


def check_quit() -> bool:
    return (cv2.waitKey(1) & 0xFF) == ord("q")


def close_all() -> None:
    cv2.destroyAllWindows()
