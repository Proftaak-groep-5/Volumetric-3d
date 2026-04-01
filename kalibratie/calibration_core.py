"""Calibration logic split from the CLI wrapper."""
import glob
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np

from camera_connection import (
    Context,
    Pipeline,
    Config,
    OBSensorType,
    ensure_orbbec_available,
    get_best_color_profile,
    convert_color_frame,
)
from live_preview import show_preview, check_quit, close_all


@dataclass
class CalibrationResult:
    rms: float
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    image_size: Tuple[int, int]
    used_images: int
    pose: Optional[dict] = None

    def to_dict(self) -> dict:
        data = {
            "rms": float(self.rms),
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.tolist(),
            "image_size": list(self.image_size),
            "used_images": int(self.used_images),
        }
        if self.pose is not None:
            data["pose"] = self.pose
        return data


@dataclass
class LiveCaptureConfig:
    min_images: int
    max_seconds: float
    interval_seconds: float
    depth_res: Tuple[int, int]
    color_res: Tuple[int, int]
    fps: int
    save_frames_dir: Optional[Path]
    preview: bool
    keep_preview_open: bool


def _resolve_dictionary(name: str) -> cv2.aruco_Dictionary:
    name = name.strip().upper()
    if not name.startswith("DICT_"):
        name = "DICT_" + name
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"Unknown ArUco dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def _make_cube_board(
    dictionary: cv2.aruco_Dictionary,
    marker_length: float,
    cube_length: float,
    ids: List[int],
) -> cv2.aruco_Board:
    if len(ids) != 6:
        raise ValueError("Cube board requires exactly 6 marker IDs")

    half = cube_length / 2.0
    m = marker_length / 2.0

    def face(center, x_axis, y_axis) -> np.ndarray:
        corners = [
            center + (-m) * x_axis + (-m) * y_axis,
            center + (m) * x_axis + (-m) * y_axis,
            center + (m) * x_axis + (m) * y_axis,
            center + (-m) * x_axis + (m) * y_axis,
        ]
        return np.asarray(corners, dtype=np.float32)

    x = np.array([1.0, 0.0, 0.0])
    y = np.array([0.0, 1.0, 0.0])
    z = np.array([0.0, 0.0, 1.0])

    obj_points = [
        face(np.array([0.0, 0.0, half]), x, y),     # +Z
        face(np.array([0.0, 0.0, -half]), -x, y),    # -Z
        face(np.array([half, 0.0, 0.0]), -z, y),     # +X
        face(np.array([-half, 0.0, 0.0]), z, y),     # -X
        face(np.array([0.0, half, 0.0]), x, -z),     # +Y (down)
        face(np.array([0.0, -half, 0.0]), x, z),     # -Y (up)
    ]

    ids_array = np.asarray(ids, dtype=np.int32).reshape(-1, 1)

    if hasattr(cv2.aruco, "Board_create"):
        return cv2.aruco.Board_create(obj_points, dictionary, ids_array)
    return cv2.aruco.Board(obj_points, dictionary, ids_array)


def _collect_calibration_points(
    image_paths: List[str],
    detector: cv2.aruco_ArucoDetector,
    board: cv2.aruco_Board,
) -> Tuple[List[np.ndarray], List[np.ndarray], Tuple[int, int], int]:
    obj_points = []
    img_points = []
    image_size = None
    used = 0

    for path in image_paths:
        image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        if image_size is None:
            image_size = (image.shape[1], image.shape[0])

        corners, ids, _ = detector.detectMarkers(image)
        if ids is None:
            continue

        if hasattr(board, "matchImagePoints"):
            obj, img = board.matchImagePoints(corners, ids)
            if obj is None or img is None:
                continue
            obj_points.append(obj)
            img_points.append(img)
            used += 1
        else:
            return [], [], image_size, 0

    if image_size is None:
        raise RuntimeError("No readable images found")

    return obj_points, img_points, image_size, used


def calibrate_from_images(
    image_glob: str,
    dictionary_name: str,
    marker_length: float,
    cube_length: float,
    ids: List[int],
) -> CalibrationResult:
    image_paths = sorted(glob.glob(image_glob))
    if not image_paths:
        raise FileNotFoundError(f"No images found for pattern: {image_glob}")

    dictionary = _resolve_dictionary(dictionary_name)
    board = _make_cube_board(dictionary, marker_length, cube_length, ids)
    detector = cv2.aruco.ArucoDetector(dictionary)

    obj_points, img_points, image_size, used = _collect_calibration_points(
        image_paths, detector, board
    )

    if used < 1:
        raise RuntimeError("Need at least 1 valid image, found 0")

    if used < 10:
        print("Warning: calibration from fewer than 10 images can be unstable.")

    fx = image_size[0] * 0.9
    fy = image_size[0] * 0.9
    cx = image_size[0] / 2.0
    cy = image_size[1] / 2.0
    camera_matrix_init = np.array(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64
    )
    dist_coeffs_init = np.zeros((5, 1), dtype=np.float64)

    rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        obj_points,
        img_points,
        image_size,
        camera_matrix_init,
        dist_coeffs_init,
        flags=cv2.CALIB_USE_INTRINSIC_GUESS,
    )

    return CalibrationResult(
        rms=rms,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        image_size=image_size,
        used_images=used,
    )


def _collect_live_points(
    dictionary: cv2.aruco_Dictionary,
    board: cv2.aruco_Board,
    capture_config: LiveCaptureConfig,
) -> Tuple[
    Dict[str, List[np.ndarray]],
    Dict[str, List[np.ndarray]],
    Dict[str, Tuple[int, int]],
]:
    ensure_orbbec_available()

    ctx = Context()
    device_list = ctx.query_devices()
    device_count = device_list.get_count()
    if device_count == 0:
        raise RuntimeError("No Orbbec devices found")

    detector = cv2.aruco.ArucoDetector(dictionary)

    pipelines = {}
    image_sizes: Dict[str, Tuple[int, int]] = {}
    obj_points: Dict[str, List[np.ndarray]] = {}
    img_points: Dict[str, List[np.ndarray]] = {}

    for i in range(device_count):
        device = device_list.get_device_by_index(i)
        camera_id = f"cam{i}"
        pipeline = Pipeline(device)
        config = Config()

        color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        color_profile = get_best_color_profile(
            color_profiles,
            capture_config.color_res[0],
            capture_config.color_res[1],
            capture_config.fps,
        )
        if color_profile is None:
            raise RuntimeError(f"No color profile found for {camera_id}")
        config.enable_stream(color_profile)
        pipeline.start(config)

        pipelines[camera_id] = pipeline
        obj_points[camera_id] = []
        img_points[camera_id] = []

    start = time.time()
    last_capture = 0.0

    if capture_config.save_frames_dir:
        capture_config.save_frames_dir.mkdir(parents=True, exist_ok=True)
    stop_requested = False
    capture_done = False

    try:
        while True:
            now = time.time()
            if not capture_done and now - start > capture_config.max_seconds:
                break
            if now - last_capture < capture_config.interval_seconds:
                time.sleep(0.005)
                continue
            last_capture = now

            for camera_id, pipeline in pipelines.items():
                frames = pipeline.wait_for_frames(100)
                if frames is None:
                    continue
                color_frame = frames.get_color_frame()
                color = convert_color_frame(color_frame)
                if color is None:
                    continue
                gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
                if camera_id not in image_sizes:
                    image_sizes[camera_id] = (gray.shape[1], gray.shape[0])

                corners, ids, _ = detector.detectMarkers(gray)

                if capture_config.preview:
                    show_preview(camera_id, color, corners, ids)

                if ids is None or len(ids) == 0:
                    continue

                if not capture_done:
                    obj, img = board.matchImagePoints(corners, ids)
                    if obj is None or img is None:
                        continue

                    obj_points[camera_id].append(obj)
                    img_points[camera_id].append(img)

                    if capture_config.save_frames_dir:
                        filename = (
                            capture_config.save_frames_dir
                            / f"{camera_id}_{len(obj_points[camera_id]):04d}.png"
                        )
                        cv2.imwrite(str(filename), gray)

            if capture_config.preview and check_quit():
                stop_requested = True
                break

            if stop_requested:
                break

            if not capture_done and all(
                len(points) >= capture_config.min_images
                for points in obj_points.values()
            ):
                if capture_config.keep_preview_open:
                    capture_done = True
                else:
                    break
    finally:
        for pipeline in pipelines.values():
            pipeline.stop()
        if capture_config.preview and not capture_config.keep_preview_open:
            close_all()

    return obj_points, img_points, image_sizes


def _estimate_camera_pose(
    obj_points_list: List[np.ndarray],
    img_points_list: List[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> Optional[dict]:
    if not obj_points_list:
        return None

    rotations = []
    camera_positions = []

    for obj, img in zip(obj_points_list, img_points_list):
        success, rvec, tvec = cv2.solvePnP(
            obj,
            img,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            continue
        rmat, _ = cv2.Rodrigues(rvec)
        cam_pos = -rmat.T @ tvec
        rotations.append(rmat)
        camera_positions.append(cam_pos)

    if not rotations:
        return None

    r_sum = np.zeros((3, 3), dtype=np.float64)
    for rmat in rotations:
        r_sum += rmat
    u, _, vt = np.linalg.svd(r_sum)
    r_world_to_camera = u @ vt
    if np.linalg.det(r_world_to_camera) < 0:
        u[:, -1] *= -1
        r_world_to_camera = u @ vt

    camera_positions_np = np.hstack(camera_positions)
    camera_position_world = np.mean(camera_positions_np, axis=1, keepdims=True)
    t_world_to_camera = -r_world_to_camera @ camera_position_world
    rvec_world_to_camera, _ = cv2.Rodrigues(r_world_to_camera)

    return {
        "rvec_world_to_camera": rvec_world_to_camera.reshape(-1).tolist(),
        "tvec_world_to_camera": t_world_to_camera.reshape(-1).tolist(),
        "camera_position_world": camera_position_world.reshape(-1).tolist(),
        "rotation_world_to_camera": r_world_to_camera.tolist(),
    }


def calibrate_from_live(
    dictionary_name: str,
    marker_length: float,
    cube_length: float,
    ids: List[int],
    capture_config: LiveCaptureConfig,
) -> Dict[str, CalibrationResult]:
    dictionary = _resolve_dictionary(dictionary_name)
    board = _make_cube_board(dictionary, marker_length, cube_length, ids)

    obj_points, img_points, image_sizes = _collect_live_points(
        dictionary, board, capture_config
    )

    results: Dict[str, CalibrationResult] = {}
    for camera_id, points in obj_points.items():
        used = len(points)
        if used < 1:
            continue
        if used < 10:
            print(
                f"Warning: {camera_id} calibration from fewer than 10 images can be unstable."
            )

        image_size = image_sizes[camera_id]
        fx = image_size[0] * 0.9
        fy = image_size[0] * 0.9
        cx = image_size[0] / 2.0
        cy = image_size[1] / 2.0
        camera_matrix_init = np.array(
            [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64
        )
        dist_coeffs_init = np.zeros((5, 1), dtype=np.float64)

        rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
            points,
            img_points[camera_id],
            image_size,
            camera_matrix_init,
            dist_coeffs_init,
            flags=cv2.CALIB_USE_INTRINSIC_GUESS,
        )

        pose = _estimate_camera_pose(
            obj_points_list=points,
            img_points_list=img_points[camera_id],
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )

        results[camera_id] = CalibrationResult(
            rms=rms,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
            image_size=image_size,
            used_images=used,
            pose=pose,
        )

    if not results:
        raise RuntimeError("No valid calibrations collected from live capture")

    return results
