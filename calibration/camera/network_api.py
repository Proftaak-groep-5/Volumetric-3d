from __future__ import annotations

import ipaddress
import json
import logging
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
    subnet: str = "192.168.137.0/24"
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
            subnet=str(payload.get("subnet", "192.168.137.0/24")).strip() or "192.168.137.0/24",
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
            "Accept": "application/json",
            "User-Agent": "volumetric-3d-network-camera/1.0",
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
        "Accept": "application/json",
        "User-Agent": "volumetric-3d-network-camera/1.0",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        charset = response.headers.get_content_charset("utf-8")
        return json.loads(response.read().decode(charset))


def _http_bytes(url: str, *, timeout_s: float) -> tuple[bytes, Mapping[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "volumetric-3d-network-camera/1.0"})
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
        self._frame_index = 0
        self._started = False

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
        return self._depth_intrinsics

    def get_depth_to_color_transform(self) -> np.ndarray | None:
        if self._depth_to_color_transform is None:
            return None
        return self._depth_to_color_transform.copy()

    def apply_stream_configuration(
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
            color_payload = payload["color"]
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

        response = _http_json_request(
            f"{self._base_url}/settings",
            timeout_s=timeout_s,
            method="POST",
            payload=payload,
        )
        if not bool(response.get("ok", False)):
            raise RuntimeError(f"Failed to update network camera settings for {self._camera_id}: {response}")

        if bool(response.get("restart_required", False)):
            _http_json_request(
                f"{self._base_url}/settings/restart-streams",
                timeout_s=max(timeout_s, 1.0),
                method="POST",
                payload={},
            )
            time.sleep(1.0)

        self.refresh_metadata()
        return response

    def refresh_metadata(self) -> None:
        timeout_s = max(0.1, float(self._timeout_ms) / 1000.0)
        metadata = _http_json(f"{self._base_url}/metadata", timeout_s=max(timeout_s, 1.0))
        calibration = metadata.get("calibration")
        if not isinstance(calibration, Mapping):
            raise RuntimeError(f"Network camera {self._camera_id} returned no calibration metadata after restart")

        color_intrinsics = _intrinsics_from_payload(
            calibration.get("color_intrinsic") if calibration.get("color_intrinsic") is not None else calibration.get("color")
        )
        if color_intrinsics is None:
            raise RuntimeError(f"Network camera {self._camera_id} returned invalid color intrinsics after restart")

        depth_intrinsics = _intrinsics_from_payload(
            calibration.get("depth_intrinsic") if calibration.get("depth_intrinsic") is not None else calibration.get("depth")
        )
        depth_to_color_transform = _depth_to_color_transform_from_payload(
            calibration.get("depth_to_color_extrinsic")
            if calibration.get("depth_to_color_extrinsic") is not None
            else calibration.get("depth_to_color")
        )

        self._intrinsics = color_intrinsics
        self._depth_intrinsics = depth_intrinsics
        self._depth_to_color_transform = None if depth_to_color_transform is None else np.asarray(depth_to_color_transform, dtype=np.float64)
        self._depth_scale_m = _depth_scale_to_meters(metadata.get("depth_scale"))

    def get_frame(self, timeout_ms: int = 1000) -> CameraFrame | None:
        if not self._started:
            raise RuntimeError(f"Camera {self._camera_id} is not started")

        timeout_s = max(0.05, float(timeout_ms if timeout_ms > 0 else self._timeout_ms) / 1000.0)
        try:
            color_bytes, _ = _http_bytes(f"{self._base_url}/snapshot/color.jpg", timeout_s=timeout_s)
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, socket.timeout, ValueError) as exc:
            LOGGER.debug("Network camera color fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)
            return None

        color_array = cv2.imdecode(np.frombuffer(color_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if color_array is None:
            LOGGER.warning("Network camera %s returned undecodable color snapshot", self._camera_id)
            return None

        depth_frame = None
        depth_scale_m = self._depth_scale_m
        if self._use_depth:
            try:
                depth_bytes, headers = _http_bytes(f"{self._base_url}/snapshot/depth.png", timeout_s=timeout_s)
                depth_frame = cv2.imdecode(np.frombuffer(depth_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                header_scale = headers.get("X-Depth-Scale") or headers.get("x-depth-scale")
                if header_scale:
                    depth_scale_m = _depth_scale_to_meters(float(header_scale))
            except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, socket.timeout, ValueError) as exc:
                LOGGER.debug("Network camera depth fetch failed camera=%s url=%s error=%s", self._camera_id, self._base_url, exc)
                depth_frame = None

        self._frame_index += 1
        return CameraFrame(
            camera_id=self._camera_id,
            frame_index=self._frame_index,
            timestamp_ns=time.time_ns(),
            color=color_array,
            depth=None if depth_frame is None else np.asarray(depth_frame, dtype=np.uint16),
            depth_scale_m=depth_scale_m,
        )


def _candidate_addresses(config: NetworkCameraDiscoveryConfig) -> list[tuple[str, int]]:
    addresses: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    for ip in config.ips:
        for port in config.ports:
            candidate = (ip, int(port))
            if candidate not in seen:
                seen.add(candidate)
                addresses.append(candidate)

    try:
        network = ipaddress.ip_network(config.subnet, strict=False)
    except ValueError:
        return addresses

    for host in network.hosts():
        host_text = str(host)
        for port in config.ports:
            candidate = (host_text, int(port))
            if candidate not in seen:
                seen.add(candidate)
                addresses.append(candidate)

    return addresses


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
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
        return None

    if str(discovery.get("service_name", "")).strip() != "FemtoBoltNuc":
        return None
    if str(discovery.get("source_mode", "")).strip().lower() != "camera":
        return None

    try:
        metadata = _http_json(f"{base_url}/metadata", timeout_s=timeout_s)
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError):
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
