"use client";

import { useEffect, useMemo, useState } from "react";

import { CameraGrid } from "@/components/camera-grid";
import {
    CalibrationRunStatusResponse,
    CameraInfo,
    CameraListResponse,
    Observation,
    StartCalibrationResponse,
    VolumetricCaptureResponse,
    VolumetricPointResponse,
} from "@/lib/types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function HomePage() {
    const [cameras, setCameras] = useState<CameraInfo[]>([]);
    const [observations, setObservations] = useState<Record<string, Observation>>({});
    const [result, setResult] = useState<VolumetricPointResponse | null>(null);
    const [captureResult, setCaptureResult] = useState<VolumetricCaptureResponse | null>(null);
    const [calibrationStatus, setCalibrationStatus] = useState<CalibrationRunStatusResponse | null>(null);
    const [error, setError] = useState<string>("");
    const [busy, setBusy] = useState<boolean>(false);
    const [captureBusy, setCaptureBusy] = useState<boolean>(false);
    const [calibrationBusy, setCalibrationBusy] = useState<boolean>(false);

    useEffect(() => {
        let cancelled = false;

        const fetchCameras = async () => {
            try {
                const response = await fetch(`${apiBaseUrl}/api/cameras`);
                if (!response.ok) {
                    throw new Error(`Failed to list cameras: ${response.status}`);
                }

                const data: CameraListResponse = await response.json();
                if (!cancelled) {
                    setCameras(data.cameras);
                }
            } catch (fetchError) {
                if (!cancelled) {
                    setError(fetchError instanceof Error ? fetchError.message : "Unknown error while loading cameras");
                }
            }
        };

        const fetchCalibrationStatus = async () => {
            try {
                const response = await fetch(`${apiBaseUrl}/api/calibration/status`);
                if (!response.ok) {
                    return;
                }
                const data: CalibrationRunStatusResponse = await response.json();
                if (!cancelled) {
                    setCalibrationStatus(data);
                }
            } catch {
                // Keep last known status; transient network errors should not wipe UI state.
            }
        };

        fetchCameras();
        fetchCalibrationStatus();
        const interval = globalThis.setInterval(fetchCameras, 2000);
        const statusInterval = globalThis.setInterval(fetchCalibrationStatus, 2000);
        return () => {
            cancelled = true;
            globalThis.clearInterval(interval);
            globalThis.clearInterval(statusInterval);
        };
    }, []);

    const pickedCount = useMemo(() => Object.keys(observations).length, [observations]);

    const onPick = (observation: Observation) => {
        setObservations((current) => ({ ...current, [observation.camera_id]: observation }));
    };

    const clearPicks = () => {
        setObservations({});
        setResult(null);
        setError("");
    };

    const createStitchedCapture = async () => {
        setCaptureBusy(true);
        setError("");

        try {
            const payload = {
                camera_ids: cameras.map((camera) => camera.camera_id),
                pixel_step: 1,
                depth_min_m: 0.15,
                depth_max_m: 5,
            };

            const response = await fetch(`${apiBaseUrl}/api/volumetric-capture`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                throw new Error(detail.detail || `Failed to create volumetric capture: ${response.status}`);
            }

            const data: VolumetricCaptureResponse = await response.json();
            setCaptureResult(data);
        } catch (requestError) {
            setError(requestError instanceof Error ? requestError.message : "Unknown error while capturing point cloud");
        } finally {
            setCaptureBusy(false);
        }
    };

    const createPoint = async () => {
        setBusy(true);
        setError("");

        try {
            const payload = {
                observations: Object.values(observations),
            };

            const response = await fetch(`${apiBaseUrl}/api/volumetric-point`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                throw new Error(detail.detail || `Failed to create point: ${response.status}`);
            }

            const data: VolumetricPointResponse = await response.json();
            setResult(data);
        } catch (requestError) {
            setError(requestError instanceof Error ? requestError.message : "Unknown error while creating point");
        } finally {
            setBusy(false);
        }
    };

    const runCalibration = async () => {
        setCalibrationBusy(true);
        setError("");

        try {
            const response = await fetch(`${apiBaseUrl}/api/calibration/run`, {
                method: "POST",
            });

            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                throw new Error(detail.detail || `Failed to start calibration: ${response.status}`);
            }

            const data: StartCalibrationResponse = await response.json();
            setCalibrationStatus(data.status);
        } catch (requestError) {
            setError(requestError instanceof Error ? requestError.message : "Unknown error while starting calibration");
        } finally {
            setCalibrationBusy(false);
        }
    };

    return (
        <main className="page-shell">
            <section className="hero">
                <h1>Volumetric Femto Controller</h1>
                <p>Live preview from all connected Femto Bolt cameras, plus click-to-triangulate 3D points from calibration.</p>
            </section>

            <section className="toolbar">
                <div className="status">Connected cameras: {cameras.length}</div>
                <div className="status">Picked views: {pickedCount}</div>
                <div className="status">Calibration: {calibrationStatus?.running ? "running" : calibrationStatus?.state || "idle"}</div>
                <button onClick={createPoint} disabled={busy || pickedCount < 2}>
                    {busy ? "Creating..." : "Create Volumetric Point"}
                </button>
                <button onClick={createStitchedCapture} disabled={captureBusy || cameras.length < 1}>
                    {captureBusy ? "Capturing..." : "Capture Stitched Point Cloud"}
                </button>
                <button onClick={runCalibration} disabled={calibrationBusy || calibrationStatus?.running}>
                    {calibrationStatus?.running ? "Calibrating..." : calibrationBusy ? "Starting..." : "Calibrate Cameras"}
                </button>
                <button className="secondary" onClick={clearPicks}>
                    Clear Picks
                </button>
            </section>

            {error && <section className="error-box">{error}</section>}

            <section className="result-panel">
                <h2>Calibration Status</h2>
                <p>state: {calibrationStatus?.state || "idle"}</p>
                <p>running: {calibrationStatus?.running ? "yes" : "no"}</p>
                <p>started: {calibrationStatus?.started_at_utc || "n/a"}</p>
                <p>finished: {calibrationStatus?.finished_at_utc || "n/a"}</p>
                <p>exit code: {calibrationStatus?.return_code ?? "n/a"}</p>
                <p>message: {calibrationStatus?.message || "No calibration run yet."}</p>
                {calibrationStatus?.command && (
                    <p>command: <code>{calibrationStatus.command.join(" ")}</code></p>
                )}
                {calibrationStatus?.log_file && (
                    <p>log file: <code>{calibrationStatus.log_file}</code></p>
                )}
                {calibrationStatus?.output_tail && (
                    <pre className="log-tail">{calibrationStatus.output_tail}</pre>
                )}
            </section>

            <CameraGrid apiBaseUrl={apiBaseUrl} cameras={cameras} observations={observations} onPick={onPick} />

            {result && (
                <section className="result-panel">
                    <h2>Triangulation Result</h2>
                    <p>
                        world xyz: [{result.point_world_xyz.map((value) => value.toFixed(6)).join(", ")}]
                    </p>
                    <p>
                        unity xyz: [{result.point_unity_xyz.map((value) => value.toFixed(6)).join(", ")}]
                    </p>
                    <p>cameras used: {result.cameras_used.join(", ")}</p>
                    <p>
                        reprojection px: {Object.entries(result.reprojection_error_px)
                            .map(([cameraId, value]) => `${cameraId}=${value.toFixed(3)}`)
                            .join(" | ")}
                    </p>
                </section>
            )}

            {captureResult && (
                <section className="result-panel">
                    <h2>Stitched Point Cloud Capture</h2>
                    <p>points total: {captureResult.points_total.toLocaleString()}</p>
                    <p>cameras used: {captureResult.cameras_used.join(", ") || "none"}</p>
                    <p>
                        points per camera: {Object.entries(captureResult.points_per_camera)
                            .map(([cameraId, count]) => `${cameraId}=${count}`)
                            .join(" | ")}
                    </p>
                    <p>
                        files: <a href={`${apiBaseUrl}${captureResult.capture_file_url}`} target="_blank" rel="noreferrer">PLY</a> | {" "}
                        <a href={`${apiBaseUrl}${captureResult.preview_image_url}`} target="_blank" rel="noreferrer">Preview</a>
                    </p>
                    <img
                        src={`${apiBaseUrl}${captureResult.preview_image_url}`}
                        alt="Top-down stitched point cloud preview"
                        className="capture-preview"
                    />
                </section>
            )}
        </main>
    );
}
