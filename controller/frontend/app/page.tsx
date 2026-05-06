"use client";

import { useEffect, useMemo, useState } from "react";

import { CameraGrid } from "@/components/camera-grid";
import {
    CameraInfo,
    CameraListResponse,
    Observation,
    VolumetricCaptureResponse,
    VolumetricPointResponse,
} from "@/lib/types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function HomePage() {
    const [cameras, setCameras] = useState<CameraInfo[]>([]);
    const [observations, setObservations] = useState<Record<string, Observation>>({});
    const [result, setResult] = useState<VolumetricPointResponse | null>(null);
    const [captureResult, setCaptureResult] = useState<VolumetricCaptureResponse | null>(null);
    const [error, setError] = useState<string>("");
    const [busy, setBusy] = useState<boolean>(false);
    const [captureBusy, setCaptureBusy] = useState<boolean>(false);

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

        fetchCameras();
        const interval = globalThis.setInterval(fetchCameras, 2000);
        return () => {
            cancelled = true;
            globalThis.clearInterval(interval);
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
                pixel_step: 4,
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

    return (
        <main className="page-shell">
            <section className="hero">
                <h1>Volumetric Femto Controller</h1>
                <p>Live preview from all connected Femto Bolt cameras, plus click-to-triangulate 3D points from calibration.</p>
            </section>

            <section className="toolbar">
                <div className="status">Connected cameras: {cameras.length}</div>
                <div className="status">Picked views: {pickedCount}</div>
                <button onClick={createPoint} disabled={busy || pickedCount < 2}>
                    {busy ? "Creating..." : "Create Volumetric Point"}
                </button>
                <button onClick={createStitchedCapture} disabled={captureBusy || cameras.length < 1}>
                    {captureBusy ? "Capturing..." : "Capture Stitched Point Cloud"}
                </button>
                <button className="secondary" onClick={clearPicks}>
                    Clear Picks
                </button>
            </section>

            {error && <section className="error-box">{error}</section>}

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
