from __future__ import annotations

from pathlib import Path

import numpy as np

from app.domain.models import CameraIntrinsics


def depth_color_to_pointcloud(
    depth: np.ndarray,
    color: np.ndarray,
    intrinsics: CameraIntrinsics,
    stride: int = 2,
    max_depth_m: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert aligned depth/color frames into XYZ + RGB arrays."""
    if depth.ndim != 2:
        raise ValueError("depth frame must be HxW")
    if color.ndim != 3 or color.shape[2] < 3:
        raise ValueError("color frame must be HxWx3+")

    depth_sub = depth[::stride, ::stride].astype(np.float32) / 1000.0
    h, w = depth_sub.shape

    u_coords = (np.arange(w, dtype=np.float32) * stride)[None, :].repeat(h, axis=0)
    v_coords = (np.arange(h, dtype=np.float32) * stride)[:, None].repeat(w, axis=1)

    valid = (depth_sub > 0.0) & (depth_sub < max_depth_m)
    if not np.any(valid):
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)

    z = depth_sub[valid]
    u = u_coords[valid]
    v = v_coords[valid]

    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy

    points = np.column_stack((x, y, z)).astype(np.float32)

    color_u = np.clip((u / depth.shape[1] * color.shape[1]).astype(np.int32), 0, color.shape[1] - 1)
    color_v = np.clip((v / depth.shape[0] * color.shape[0]).astype(np.int32), 0, color.shape[0] - 1)
    colors = color[color_v, color_u, :3].astype(np.uint8)

    return points, colors


def write_ply_ascii(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    with path.open("w", encoding="utf-8") as fh:
        fh.write("ply\n")
        fh.write("format ascii 1.0\n")
        fh.write(f"element vertex {len(points)}\n")
        fh.write("property float x\n")
        fh.write("property float y\n")
        fh.write("property float z\n")
        fh.write("property uchar red\n")
        fh.write("property uchar green\n")
        fh.write("property uchar blue\n")
        fh.write("end_header\n")

        for point, color in zip(points, colors):
            fh.write(
                f"{float(point[0])} {float(point[1])} {float(point[2])} "
                f"{int(color[0])} {int(color[1])} {int(color[2])}\n"
            )
