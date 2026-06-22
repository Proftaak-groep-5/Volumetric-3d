"use client";

import { MouseEvent, useEffect, useState } from "react";

import { CameraInfo, Observation } from "@/lib/types";

type Props = {
    apiBaseUrl: string;
    cameras: CameraInfo[];
    observations: Record<string, Observation>;
    onPick: (observation: Observation) => void;
};

const PREVIEW_INTERVAL_MS = 66;

function toPixelObservation(event: MouseEvent<HTMLElement>, image: HTMLImageElement, cameraId: string): Observation {
    const rect = image.getBoundingClientRect();

    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const scaleX = image.naturalWidth / rect.width;
    const scaleY = image.naturalHeight / rect.height;

    return {
        camera_id: cameraId,
        u: x * scaleX,
        v: y * scaleY,
    };
}

type LivePreviewImageProps = {
    snapshotUrl: string;
    alt: string;
    className: string;
};

function LivePreviewImage({ snapshotUrl, alt, className }: Readonly<LivePreviewImageProps>) {
    const [src, setSrc] = useState<string>(() => `${snapshotUrl}?t=${Date.now()}`);

    useEffect(() => {
        let cancelled = false;
        let timer: ReturnType<typeof globalThis.setTimeout> | undefined;

        const schedule = (delayMs: number) => {
            timer = globalThis.setTimeout(loadNext, Math.max(0, delayMs));
        };

        const loadNext = () => {
            if (cancelled) {
                return;
            }
            const startedAt = Date.now();
            const nextSrc = `${snapshotUrl}?t=${startedAt}`;
            const probe = new Image();
            probe.onload = () => {
                if (cancelled) {
                    return;
                }
                setSrc(nextSrc);
                const elapsedMs = Date.now() - startedAt;
                schedule(PREVIEW_INTERVAL_MS - elapsedMs);
            };
            probe.onerror = () => {
                if (cancelled) {
                    return;
                }
                schedule(200);
            };
            probe.src = nextSrc;
        };

        loadNext();
        return () => {
            cancelled = true;
            if (timer !== undefined) {
                globalThis.clearTimeout(timer);
            }
        };
    }, [snapshotUrl]);

    // eslint-disable-next-line @next/next/no-img-element -- Live snapshots are refreshed manually for low-latency preview.
    return <img src={src} alt={alt} className={className} />;
}

export function CameraGrid({ apiBaseUrl, cameras, observations, onPick }: Readonly<Props>) {
    if (cameras.length === 0) {
        return <div className="empty-state">No connected cameras found.</div>;
    }

    return (
        <div className="camera-grid">
            {cameras.map((camera) => {
                const picked = observations[camera.camera_id];
                return (
                    <section className="camera-card" key={camera.camera_id}>
                        <header className="camera-card-header">
                            <h3>{camera.camera_id}</h3>
                            <p>
                                {camera.device_name || "Femto Bolt"} | {camera.width}x{camera.height} @ {camera.fps}fps
                            </p>
                        </header>

                        <div className="camera-preview-wrap">
                            <button
                                type="button"
                                className="preview-button"
                                onClick={(event) => {
                                    const image = event.currentTarget.querySelector("img");
                                    if (!image) {
                                        return;
                                    }
                                    onPick(toPixelObservation(event, image, camera.camera_id));
                                }}
                            >
                                <LivePreviewImage
                                    snapshotUrl={`${apiBaseUrl}${camera.snapshot_url}`}
                                    alt={`Live stream ${camera.camera_id}`}
                                    className="camera-preview"
                                />
                            </button>
                            {picked && (
                                <div className="picked-indicator">
                                    pick ({picked.u.toFixed(1)}, {picked.v.toFixed(1)})
                                </div>
                            )}
                        </div>
                    </section>
                );
            })}
        </div>
    );
}
