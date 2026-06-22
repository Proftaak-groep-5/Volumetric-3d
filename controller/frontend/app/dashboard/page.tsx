"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { CameraInfo, CameraListResponse } from "@/lib/types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const MAX_LOG_LINES_PER_CAMERA = 200;

type ConnectionState = "unavailable" | "connecting" | "live" | "disconnected" | "error";

type CameraLogEntry = {
    id: string;
    receivedAt: string;
    line: string;
};

type CameraLogTarget = {
    cameraId: string;
    deviceName?: string;
    logWsUrl?: string | null;
};

function appendLogLine(current: CameraLogEntry[] | undefined, line: string): CameraLogEntry[] {
    const entry: CameraLogEntry = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        receivedAt: new Date().toLocaleTimeString(),
        line,
    };
    return [...(current ?? []), entry].slice(-MAX_LOG_LINES_PER_CAMERA);
}

export default function DashboardPage() {
    const [cameras, setCameras] = useState<CameraInfo[]>([]);
    const [logsByCamera, setLogsByCamera] = useState<Record<string, CameraLogEntry[]>>({});
    const [connectionStates, setConnectionStates] = useState<Record<string, ConnectionState>>({});
    const [error, setError] = useState<string>("");

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
                    setError("");
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

    const logTargets = useMemo<CameraLogTarget[]>(
        () => cameras
            .map((camera) => ({
                cameraId: camera.camera_id,
                deviceName: camera.device_name,
                logWsUrl: camera.log_ws_url,
            }))
            .sort((left, right) => left.cameraId.localeCompare(right.cameraId)),
        [cameras],
    );

    const targetKey = useMemo(
        () => logTargets.map((target) => `${target.cameraId}:${target.logWsUrl ?? ""}`).join("|"),
        [logTargets],
    );

    useEffect(() => {
        let cancelled = false;
        const sockets: WebSocket[] = [];
        const reconnectTimers: ReturnType<typeof globalThis.setTimeout>[] = [];

        const setConnectionState = (cameraId: string, state: ConnectionState) => {
            setConnectionStates((current) => ({ ...current, [cameraId]: state }));
        };

        for (const target of logTargets) {
            if (!target.logWsUrl) {
                setConnectionState(target.cameraId, "unavailable");
                continue;
            }

            const connect = () => {
                if (cancelled || !target.logWsUrl) {
                    return;
                }

                setConnectionState(target.cameraId, "connecting");
                const socket = new WebSocket(target.logWsUrl);
                sockets.push(socket);

                socket.onopen = () => {
                    setConnectionState(target.cameraId, "live");
                };

                socket.onmessage = (event) => {
                    const line = typeof event.data === "string" ? event.data : "";
                    if (!line.trim()) {
                        return;
                    }
                    setLogsByCamera((current) => ({
                        ...current,
                        [target.cameraId]: appendLogLine(current[target.cameraId], line),
                    }));
                };

                socket.onerror = () => {
                    setConnectionState(target.cameraId, "error");
                };

                socket.onclose = () => {
                    if (cancelled) {
                        return;
                    }
                    setConnectionState(target.cameraId, "disconnected");
                    const timer = globalThis.setTimeout(connect, 2000);
                    reconnectTimers.push(timer);
                };
            };

            connect();
        }

        return () => {
            cancelled = true;
            for (const timer of reconnectTimers) {
                globalThis.clearTimeout(timer);
            }
            for (const socket of sockets) {
                socket.close();
            }
        };
        // targetKey intentionally drives reconnection when camera IDs or URLs change.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [targetKey]);

    const connectedCount = cameras.filter((camera) => camera.connected).length;
    const liveLogCount = Object.values(connectionStates).filter((state) => state === "live").length;

    return (
        <main className="dashboard-shell">
            <header className="dashboard-header">
                <div>
                    <p className="dashboard-pill">Live Logs</p>
                    <h1>Camera Log Dashboard</h1>
                    <p>One live websocket per NUC, with history held locally in this controller view.</p>
                </div>
                <div className="dashboard-actions">
                    <Link className="button-link secondary" href="/">
                        Back to Control Room
                    </Link>
                    <button className="secondary" type="button" onClick={() => setLogsByCamera({})}>
                        Clear Logs
                    </button>
                </div>
            </header>

            <section className="dashboard-stats">
                <div className="dashboard-stat">
                    <span>connected cameras</span>
                    <strong>{connectedCount}</strong>
                </div>
                <div className="dashboard-stat">
                    <span>live log sockets</span>
                    <strong>{liveLogCount}</strong>
                </div>
                <div className="dashboard-stat">
                    <span>history limit</span>
                    <strong>{MAX_LOG_LINES_PER_CAMERA}</strong>
                </div>
            </section>

            {error && <section className="error-box">{error}</section>}

            {logTargets.length === 0 ? (
                <section className="empty-state">No connected cameras found.</section>
            ) : (
                <section className="log-dashboard-grid">
                    {logTargets.map((target) => {
                        const cameraLogs = logsByCamera[target.cameraId] ?? [];
                        const state = connectionStates[target.cameraId] ?? "connecting";
                        return (
                            <article className="log-camera-card" key={target.cameraId}>
                                <header className="log-camera-header">
                                    <div>
                                        <h2>{target.cameraId}</h2>
                                        <p>{target.deviceName || "Femto Bolt NUC"}</p>
                                    </div>
                                    <span className={`log-state ${state}`}>{state}</span>
                                </header>
                                <div className="log-stream">
                                    {cameraLogs.length === 0 ? (
                                        <p className="log-placeholder">
                                            {target.logWsUrl ? "Waiting for the next log line..." : "No NUC log websocket is available for this camera."}
                                        </p>
                                    ) : (
                                        cameraLogs.map((entry) => (
                                            <div className="log-entry" key={entry.id}>
                                                <time>{entry.receivedAt}</time>
                                                <code>{entry.line}</code>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </article>
                        );
                    })}
                </section>
            )}
        </main>
    );
}
