from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import cv2
import numpy as np

from calibration.camera.base import CameraDevice, CameraFrame, CameraIntrinsics

LOGGER = logging.getLogger(__name__)
DEFAULT_SUBNET = "192.168.137.0/24"
DEFAULT_ACCEPT_HEADER = "application/json"
DEFAULT_USER_AGENT = "volumetric-3d-network-camera/1.0"
_SNAPSHOT_IO_WORKERS = min(64, max(4, int(os.getenv("NETWORK_SNAPSHOT_IO_WORKERS", "16"))))
_SNAPSHOT_IO_EXECUTOR = ThreadPoolExecutor(max_workers=_SNAPSHOT_IO_WORKERS, thread_name_prefix="network-snapshot")
_PARALLEL_COLOR_DEPTH_FETCH = os.getenv("NETWORK_PARALLEL_COLOR_DEPTH_FETCH", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _depth_scale_to_meters(scale_value: float | None) -> float | None:
    if scale_value is None:
        return None
    scale = float(scale_value)
    if scale <= 0.0:
        return None
    # NUC snapshot headers and metadata report depth as: millimeters = raw * scale.
    return scale / 1000.0


@dataclass(frozen=True)
class NetworkCameraDiscoveryConfig:
    enabled: bool = True
    subnet: str = DEFAULT_SUBNET
    ips: tuple[str, ...] = ()
    ports: tuple[int, ...] = (8080,)
    timeout_ms: int = 350
    max_cameras: int = 16
    max_workers: int = 32

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "NetworkCameraDiscoveryConfig":
        if not isinstance(payload, Mapping):
            return cls()

        ips_value = payload.get("ips", ())
        if isinstance(ips_value, str):
            ips = tuple(part.strip() for part in ips_value.split(",") if part.strip())
        elif isinstance(ips_value, Sequence):
            ips = tuple(str(part).strip() for part in ips_value if str(part).strip())
        else:
            ips = ()

        ports_value = payload.get("ports", (8080,))
        if isinstance(ports_value, str):
            ports = tuple(int(part.strip()) for part in ports_value.split(",") if part.strip())
        elif isinstance(ports_value, Sequence):
            ports = tuple(int(part) for part in ports_value)
        else:
            ports = (8080,)

        max_cameras = int(payload.get("max_cameras", 16))
        max_workers = int(payload.get("max_workers", 32))
        timeout_ms = int(payload.get("timeout_ms", 350))

        return cls(
            enabled=bool(payload.get("enabled", True)),
            subnet=str(payload.get("subnet", DEFAULT_SUBNET)).strip() or DEFAULT_SUBNET,
            ips=ips,
            ports=ports or (8080,),
            timeout_ms=max(50, timeout_ms),
            max_cameras=max(1, max_cameras),
            max_workers=max(1, max_workers),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "subnet": self.subnet,
            "ips": list(self.ips),
            "ports": list(self.ports),
            "timeout_ms": self.timeout_ms,
            "max_cameras": self.max_cameras,
            "max_workers": self.max_workers,
        }

    def validate(self) -> None:
        if not self.enabled:
            return
        ipaddress.ip_network(self.subnet, strict=False)
        if any(port <= 0 or port > 65535 for port in self.ports):
            raise ValueError("network_camera.ports must contain valid TCP ports")
        if self.timeout_ms <= 0:
            raise ValueError("network_camera.timeout_ms must be > 0")
        if self.max_cameras <= 0:
            raise ValueError("network_camera.max_cameras must be > 0")
        if self.max_workers <= 0:
            raise ValueError("network_camera.max_workers must be > 0")


def _http_json(url: str, *, timeout_s: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": DEFAULT_ACCEPT_HEADER,
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        charset = response.headers.get_content_charset("utf-8")
        return json.loads(response.read().decode(charset))


def _http_json_request(
    url: str,
    *,
    timeout_s: float,
    method: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": DEFAULT_ACCEPT_HEADER,
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = DEFAULT_ACCEPT_HEADER

    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        charset = response.headers.get_content_charset("utf-8")
        return json.loads(response.read().decode(charset))


def _http_bytes(url: str, *, timeout_s: float) -> tuple[bytes, Mapping[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read(), dict(response.headers.items())


def _intrinsics_from_payload(payload: Mapping[str, Any] | None) -> CameraIntrinsics | None:
    if not isinstance(payload, Mapping):
        return None

    fx = float(payload.get("fx", 0.0))
    fy = float(payload.get("fy", 0.0))
    cx = float(payload.get("cx", 0.0))
    cy = float(payload.get("cy", 0.0))
    width = int(payload.get("width", 0))
    height = int(payload.get("height", 0))
    if fx <= 0.0 or fy <= 0.0 or width <= 0 or height <= 0:
        return None

    camera_matrix = np.array(
        [
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    dist = np.zeros((5,), dtype=np.float64)
    intrinsics = CameraIntrinsics(camera_matrix=camera_matrix, dist_coeffs=dist, width=width, height=height)
    intrinsics.validate()
    return intrinsics


def _depth_to_color_transform_from_payload(payload: Mapping[str, Any] | None) -> np.ndarray | None:
    if not isinstance(payload, Mapping):
        return None

    rot = payload.get("rot")
    trans = payload.get("trans")
    if not isinstance(rot, Sequence) or not isinstance(trans, Sequence) or len(rot) != 9 or len(trans) != 3:
        return None

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = np.asarray(rot, dtype=np.float64).reshape(3, 3)
    # NUC metadata reports translation in millimeters; convert to meters to match point-cloud math.
    transform[:3, 3] = np.asarray(trans, dtype=np.float64).reshape(3) / 1000.0
    return transform


def _normalize_camera_id(instance_id: str, serial_number: str, host: str) -> str:
    preferred = serial_number.strip() or instance_id.strip() or host.strip()
    token = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in preferred).strip("-")
    return f"net-{token or host.replace('.', '-')}"


class NetworkApiCamera(CameraDevice):
    def __init__(
        self,
        *,
        camera_id: str,
        base_url: str,
        instance_id: str,
        serial_number: str,
        device_name: str,
        intrinsics: CameraIntrinsics,
        depth_intrinsics: CameraIntrinsics | None,
        depth_to_color_transform: np.ndarray | None,
        use_depth: bool,
        timeout_ms: int,
        depth_scale_m: float | None,
        depth_alignment_enabled: bool = False,
    ) -> None:
        self._camera_id = camera_id
        self._base_url = base_url.rstrip("/")
        self._instance_id = instance_id
        self._serial_number = serial_number
        self._device_name = device_name
        self._intrinsics = intrinsics
        self._depth_intrinsics = depth_intrinsics
        self._depth_to_color_transform = None if depth_to_color_transform is None else np.asarray(depth_to_color_transform, dtype=np.float64)
        self._use_depth = bool(use_depth)
        self._timeout_ms = int(timeout_ms)
        self._depth_scale_m = float(depth_scale_m) if depth_scale_m is not None else None
        self._depth_alignment_enabled = bool(depth_alignment_enabled)
        self._frame_index = 0
        self._started = False

    def _next_frame_index(self) -> int:
        self._frame_index += 1
        return self._frame_index

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def connection_type(self) -> str:
        return "network_api"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def get_intrinsics(self) -> CameraIntrinsics:
        return self._intrinsics

    def get_depth_intrinsics(self) -> CameraIntrinsics | None:
        if self._depth_alignment_enabled:
            return self._intrinsics
        return self._depth_intrinsics

    def get_depth_to_color_transform(self) -> np.ndarray | None:
        if self._depth_alignment_enabled:
            return None
        if self._depth_to_color_transform is None:
            return None
        return self._depth_to_color_transform.copy()

    def get_actual_color_resolution(self) -> tuple[int, int] | None:
        """Fetch actual streaming color resolution from NUC metadata (may differ from config if unsupported)."""
        try:
            timeout_s = max(0.05, float(self._timeout_ms) / 1000.0)
            metadata = _http_json(f"{self._base_url}/metadata", timeout_s=timeout_s)
            current_profiles = metadata.get("current_profiles", {})
            if current_profiles:
                color_profile = current_profiles.get("color", {})
                width = color_profile.get("width")
                height = color_profile.get("height")
                if width is not None and height is not None:
                    return (int(width), int(height))
        except Exception:
            pass
        return None

    def apply_stream_configuration(  # noqa: C901
        self,
        *,
        color_width: int,
        color_height: int,
        depth_width: int,
        depth_height: int,
        fps: int,
        align_to_color: bool | None = None,
        camera_tuning: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        timeout_s = max(0.1, float(self._timeout_ms) / 1000.0)
        config_timeout_s = max(timeout_s, 2.0)
        
        payload = self._build_stream_config(
            color_width, color_height, depth_width, depth_height, fps,
            align_to_color, camera_tuning
        )

        response = _http_json_request(
            f"{self._base_url}/settings",
            timeout_s=config_timeout_s,
            method="POST",
            payload=payload,
        )
        if not bool(response.get("ok", False)):
            raise RuntimeError(f"Failed to update network camera settings for {self._camera_id}: {response}")

        restart_required = bool(response.get("restart_required", False))
        if restart_required:
            time.sleep(0.5)
            # Refresh cached calibration after a stream restart so callers see the current geometry.
            self.refresh_metadata(timeout_s=config_timeout_s, retries=6, retry_delay_s=0.5)

        return response

    def _build_stream_config(
        self,
        color_width: int,
        color_height: int,
        depth_width: int,
        depth_height: int,
        fps: int,
        align_to_color: bool | None,
        camera_tuning: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Build stream configuration payload."""
        payload: dict[str, Any] = {
            "color": {
                "width": int(color_width),
                "height": int(color_height),
                "fps": int(fps),
            },
            "depth": {
                "width": int(depth_width),
                "height": int(depth_height),
                "fps": int(fps),
            },
        }
        if align_to_color is not None:
            payload["depth"]["align_to_color"] = bool(align_to_color)
        if camera_tuning:
            self._apply_color_tuning(payload["color"], camera_tuning)
        return payload

    def _apply_color_tuning(self, color_payload: dict[str, Any], camera_tuning: Mapping[str, Any]) -> None:
        """Apply color tuning settings to payload."""
        tuning_field_map = {
            "color_auto_exposure": "exposure_auto",
            "color_exposure": "exposure_value",
            "color_gain": "gain",
            "color_auto_white_balance": "white_balance_auto",
            "color_white_balance": "white_balance_value",
            "color_brightness": "brightness",
            "color_contrast": "contrast",
            "color_saturation": "saturation",
        }
        for source_key, target_key in tuning_field_map.items():
            value = camera_tuning.get(source_key)
            if value is None:
                continue
            color_payload[target_key] = bool(value) if isinstance(value, bool) else int(value)

        # Avoid forcing manual values while auto modes are enabled.
        if bool(color_payload.get("exposure_auto", True)):
            color_payload.pop("exposure_value", None)
        if bool(color_payload.get("white_balance_auto", True)):
            color_payload.pop("white_balance_value", None)

    def refresh_metadata(self, *, timeout_s: float | None = None, retries: int = 1, retry_delay_s: float = 0.0) -> None:  # noqa: C901
        request_timeout_s = max(0.1, float(self._timeout_ms) / 1000.0) if timeout_s is None else max(0.1, float(timeout_s))
        attempts = max(1, int(retries))
        
        metadata = self._fetch_metadata_with_retries(request_timeout_s, attempts, retry_delay_s)
        if metadata is None:
            raise RuntimeError(f"Failed to refresh network camera metadata for {self._camera_id}")
        
        self._parse_and_store_metadata(metadata)

    def _fetch_metadata_with_retries(
        self, timeout_s: float, attempts: int, retry_delay_s: float
    ) -> dict[str, Any] | None:
        """Fetch metadata with retry logic."""
        for attempt in range(1, attempts + 1):
            try:
                return _http_json(f"{self._base_url}/metadata", timeout_s=timeout_s)
            except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
                if attempt < attempts:
                    time.sleep(max(0.0, float(retry_delay_s)))
                    continue
                raise RuntimeError(
                    f"Failed to refresh network camera metadata for {self._camera_id} after {attempts} attempt(s): {exc}"
                ) from exc
        return None

    def _parse_and_store_metadata(self, metadata: dict[str, Any]) -> None:
        """Parse metadata and store camera parameters."""
        calibration = metadata.get("calibration")
        if not isinstance(calibration, Mapping):
            raise RuntimeError(f"Network camera {self._camera_id} returned no calibration metadata after restart")

        color_intrinsics = self._get_intrinsics_from_calibration(calibration, "color")
        if color_intrinsics is None:
            raise RuntimeError(f"Network camera {self._camera_id} returned invalid color intrinsics after restart")

        depth_intrinsics = self._get_intrinsics_from_calibration(calibration, "depth")
        depth_to_color_transform = self._get_depth_to_color_from_calibration(calibration)

        self._intrinsics = color_intrinsics
        self._depth_intrinsics = depth_intrinsics
        self._depth_to_color_transform = None if depth_to_color_transform is None else np.asarray(depth_to_color_transform, dtype=np.float64)
        self._depth_alignment_enabled = bool(calibration.get("depth_alignment_enabled", False))
        self._depth_scale_m = _depth_scale_to_meters(metadata.get("depth_scale"))

    def _get_intrinsics_from_calibration(self, calibration: Mapping[str, Any], prefix: str) -> np.ndarray | None:
        """Extract intrinsics from calibration data."""
        intrinsic_key = f"{prefix}_intrinsic"
        value = calibration.get(intrinsic_key) if calibration.get(intrinsic_key) is not None else calibration.get(prefix)
        return _intrinsics_from_payload(value)

    def _get_depth_to_color_from_calibration(self, calibration: Mapping[str, Any]) -> list[list[float]] | None:
        """Extract depth-to-color transform from calibration data."""
        extrinsic_key = "depth_to_color_extrinsic"
        value = (
            calibration.get(extrinsic_key)
            if calibration.get(extrinsic_key) is not None
            else calibration.get("depth_to_color")
        )
        return _depth_to_color_transform_from_payload(value)

    def get_frame(self, timeout_ms: int = 1000) -> CameraFrame | None:  # noqa: C901
        if not self._started:
            raise RuntimeError(f"Camera {self._camera_id} is not started")

        timeout_s = max(0.05, float(timeout_ms if timeout_ms > 0 else self._timeout_ms) / 1000.0)
        
        if self._use_depth and _PARALLEL_COLOR_DEPTH_FETCH:
            color_payload, depth_payload = self._fetch_parallel(timeout_s)
        else:
            color_payload = self._fetch_color_snapshot(timeout_s)
            depth_payload = self._fetch_depth_snapshot(timeout_s) if self._use_depth else None

        if color_payload is None:
            return None
        
        return self._build_frame(color_payload, depth_payload)

    def _fetch_parallel(self, timeout_s: float) -> tuple[tuple[np.ndarray, bytes] | None, tuple[np.ndarray, float | None] | None]:
        """Fetch color and depth in parallel."""
        color_future = _SNAPSHOT_IO_EXECUTOR.submit(_http_bytes, f"{self._base_url}/snapshot/color.jpg", timeout_s=timeout_s)
        depth_future = _SNAPSHOT_IO_EXECUTOR.submit(_http_bytes, f"{self._base_url}/snapshot/depth.png", timeout_s=timeout_s)

        color_bytes: bytes | None = None
        depth_bytes: bytes | None = None
        depth_headers: Mapping[str, str] | None = None

        try:
            color_bytes, _ = color_future.result()
        except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera color fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)

        try:
            depth_bytes, depth_headers = depth_future.result()
        except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera depth fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)

        color_payload = self._decode_color_snapshot_bytes(color_bytes)
        depth_payload = self._decode_depth_snapshot_bytes(depth_bytes, depth_headers or {}) if depth_bytes is not None else None
        return color_payload, depth_payload

    def _build_frame(
        self,
        color_payload: tuple[np.ndarray, bytes],
        depth_payload: tuple[np.ndarray, float | None] | None,
    ) -> CameraFrame:
        """Build a CameraFrame from payloads."""
        color_array, color_bytes = color_payload
        
        depth_frame: np.ndarray | None = None
        depth_scale_m = self._depth_scale_m
        if depth_payload is not None:
            depth_frame, header_depth_scale = depth_payload
            if header_depth_scale is not None:
                depth_scale_m = header_depth_scale

        return CameraFrame(
            camera_id=self._camera_id,
            frame_index=self._next_frame_index(),
            timestamp_ns=time.time_ns(),
            color=color_array,
            color_jpeg=color_bytes,
            depth=None if depth_frame is None else np.asarray(depth_frame, dtype=np.uint16),
            depth_scale_m=depth_scale_m,
        )

    def get_depth_frame(self, timeout_ms: int = 1000) -> CameraFrame | None:
        if not self._started:
            raise RuntimeError(f"Camera {self._camera_id} is not started")

        timeout_s = max(0.02, float(timeout_ms if timeout_ms > 0 else self._timeout_ms) / 1000.0)
        depth_payload = self._fetch_depth_snapshot(timeout_s)
        if depth_payload is None:
            return None
        depth_frame, depth_scale_m = depth_payload

        return CameraFrame(
            camera_id=self._camera_id,
            frame_index=self._next_frame_index(),
            timestamp_ns=time.time_ns(),
            color=None,
            color_jpeg=None,
            depth=np.asarray(depth_frame, dtype=np.uint16),
            depth_scale_m=depth_scale_m if depth_scale_m is not None else self._depth_scale_m,
        )

    def _fetch_color_snapshot(self, timeout_s: float) -> tuple[np.ndarray, bytes] | None:
        try:
            color_bytes, _ = _http_bytes(f"{self._base_url}/snapshot/color.jpg", timeout_s=timeout_s)
        except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera color fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)
            return None

        return self._decode_color_snapshot_bytes(color_bytes)

    def _fetch_depth_snapshot(self, timeout_s: float) -> tuple[np.ndarray, float | None] | None:
        try:
            depth_bytes, headers = _http_bytes(f"{self._base_url}/snapshot/depth.png", timeout_s=timeout_s)
        except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera depth fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)
            return None

        return self._decode_depth_snapshot_bytes(depth_bytes, headers)

    def _decode_color_snapshot_bytes(self, color_bytes: bytes | None) -> tuple[np.ndarray, bytes] | None:
        if color_bytes is None:
            return None

        color_array = cv2.imdecode(np.frombuffer(color_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if color_array is None:
            LOGGER.warning("Network camera %s returned undecodable color snapshot", self._camera_id)
            return None

        return color_array, color_bytes

    def _decode_depth_snapshot_bytes(
        self,
        depth_bytes: bytes | None,
        headers: Mapping[str, str],
    ) -> tuple[np.ndarray, float | None] | None:
        if depth_bytes is None:
            return None

        depth_frame = cv2.imdecode(np.frombuffer(depth_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if depth_frame is None:
            LOGGER.debug("Network camera depth fetch returned undecodable frame camera=%s", self._camera_id)
            return None

        depth_scale_m = None
        header_scale = headers.get("X-Depth-Scale") or headers.get("x-depth-scale")
        if header_scale:
            try:
                depth_scale_m = _depth_scale_to_meters(float(header_scale))
            except ValueError:
                pass

        return np.asarray(depth_frame, dtype=np.uint16), depth_scale_m

    def get_preview_jpeg(self, timeout_ms: int = 1000) -> tuple[bytes, int] | None:
        if not self._started:
            raise RuntimeError(f"Camera {self._camera_id} is not started")

        timeout_s = max(0.05, float(timeout_ms if timeout_ms > 0 else self._timeout_ms) / 1000.0)
        try:
            color_bytes, _ = _http_bytes(f"{self._base_url}/snapshot/color.jpg", timeout_s=timeout_s)
        except (TimeoutError, urllib.error.URLError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera preview fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)
            return None

        return color_bytes, self._next_frame_index()


def _candidate_addresses(config: NetworkCameraDiscoveryConfig) -> list[tuple[str, int]]:  # noqa: C901
    addresses: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    # Always probe local loopback endpoints so host-local camera services are reachable via network API.
    _add_candidates_from_hosts(["127.0.0.1", "localhost"], config.ports, addresses, seen)

    # Add manually specified IPs.
    _add_candidates_from_hosts(list(config.ips), config.ports, addresses, seen)

    # Add candidates from subnet.
    try:
        network = ipaddress.ip_network(config.subnet, strict=False)
        for host in network.hosts():
            _add_candidates_from_hosts([str(host)], config.ports, addresses, seen)
    except ValueError:
        pass

    return addresses


def _add_candidates_from_hosts(
    hosts: list[str], ports: tuple[int, ...] | list[int],
    addresses: list[tuple[str, int]], seen: set[tuple[str, int]],
) -> None:
    """Add host:port candidates to address list, avoiding duplicates."""
    for host in hosts:
        for port in ports:
            candidate = (host, int(port))
            if candidate not in seen:
                seen.add(candidate)
                addresses.append(candidate)


def _discover_single_network_camera(
    host: str,
    port: int,
    *,
    timeout_ms: int,
    use_depth: bool,
) -> NetworkApiCamera | None:
    timeout_s = max(0.05, float(timeout_ms) / 1000.0)
    base_url = f"http://{host}:{port}"

    try:
        discovery = _http_json(f"{base_url}/discovery", timeout_s=timeout_s)
    except (TimeoutError, urllib.error.URLError, socket.timeout, json.JSONDecodeError):
        return None

    if str(discovery.get("service_name", "")).strip() != "FemtoBoltNuc":
        return None
    if str(discovery.get("source_mode", "")).strip().lower() != "camera":
        return None

    try:
        metadata = _http_json(f"{base_url}/metadata", timeout_s=timeout_s)
    except (TimeoutError, urllib.error.URLError, socket.timeout, json.JSONDecodeError):
        return None

    calibration = metadata.get("calibration")
    if not isinstance(calibration, Mapping):
        return None

    color_intrinsics = _intrinsics_from_payload(
        calibration.get("color_intrinsic") if calibration.get("color_intrinsic") is not None else calibration.get("color")
    )
    if color_intrinsics is None:
        return None

    depth_intrinsics = _intrinsics_from_payload(
        calibration.get("depth_intrinsic") if calibration.get("depth_intrinsic") is not None else calibration.get("depth")
    )
    depth_to_color_transform = _depth_to_color_transform_from_payload(
        calibration.get("depth_to_color_extrinsic")
        if calibration.get("depth_to_color_extrinsic") is not None
        else calibration.get("depth_to_color")
    )
    depth_alignment_enabled = bool(calibration.get("depth_alignment_enabled", False))
    device = metadata.get("device") if isinstance(metadata.get("device"), Mapping) else {}
    instance_id = str(discovery.get("instance_id", "")).strip()
    serial_number = str(discovery.get("serial_number", "")).strip()
    camera_id = _normalize_camera_id(instance_id=instance_id, serial_number=serial_number, host=host)
    depth_scale = _depth_scale_to_meters(metadata.get("depth_scale"))

    return NetworkApiCamera(
        camera_id=camera_id,
        base_url=base_url,
        instance_id=instance_id,
        serial_number=serial_number,
        device_name=str(device.get("name", discovery.get("model", "Femto Bolt NUC"))).strip(),
        intrinsics=color_intrinsics,
        depth_intrinsics=depth_intrinsics,
        depth_to_color_transform=depth_to_color_transform,
        use_depth=use_depth,
        timeout_ms=timeout_ms,
        depth_scale_m=depth_scale,
        depth_alignment_enabled=depth_alignment_enabled,
    )


def discover_network_api_cameras(
    *,
    use_depth: bool,
    allowed_camera_ids: Optional[Sequence[str]],
    discovery_config: NetworkCameraDiscoveryConfig,
) -> list[NetworkApiCamera]:
    if not discovery_config.enabled:
        return []

    allowed = {str(item).strip() for item in (allowed_camera_ids or []) if str(item).strip()}
    addresses = _candidate_addresses(discovery_config)
    if not addresses:
        return []

    cameras: dict[str, NetworkApiCamera] = {}
    with ThreadPoolExecutor(max_workers=min(discovery_config.max_workers, len(addresses))) as executor:
        futures = {
            executor.submit(
                _discover_single_network_camera,
                host,
                port,
                timeout_ms=discovery_config.timeout_ms,
                use_depth=use_depth,
            ): (host, port)
            for host, port in addresses
        }
        for future in as_completed(futures):
            camera = future.result()
            if camera is None:
                continue
            if allowed and camera.camera_id not in allowed and camera.serial_number not in allowed and camera.instance_id not in allowed:
                continue
            cameras.setdefault(camera.camera_id, camera)
            if len(cameras) >= discovery_config.max_cameras:
                break

    ordered = sorted(cameras.values(), key=lambda item: item.camera_id)
    for camera in ordered:
        LOGGER.info(
            "Discovered network camera id=%s name=%s serial=%s base_url=%s",
            camera.camera_id,
            camera.device_name,
            camera.serial_number,
            camera.base_url,
        )
    return ordered[: discovery_config.max_cameras]
