"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { PlyViewer } from "@/components/ply-viewer";

const STATUS_MESSAGES = [
    "Creating something magical",
    "Aligning the camera memories",
    "Merging the pictures together",
    "Painting in the depth map",
    "Almost there",
    "Lighting the final capture",
];

const MESSAGE_INTERVAL_MS = 1500;
const FLASH_DURATION_MS = 450;
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type DemoStage = "idle" | "countdown" | "flash" | "processing" | "review";

type EmailStatus = "idle" | "sending" | "sent";

export default function DemoPage() {
    const [stage, setStage] = useState<DemoStage>("idle");
    const [countdown, setCountdown] = useState<number>(5);
    const [messageIndex, setMessageIndex] = useState<number>(0);
    const [previewToken, setPreviewToken] = useState<number>(0);
    const [previewFileName, setPreviewFileName] = useState<string>("");
    const [captureStartMs, setCaptureStartMs] = useState<number>(0);
    const [email, setEmail] = useState<string>("");
    const [emailStatus, setEmailStatus] = useState<EmailStatus>("idle");
    const [emailError, setEmailError] = useState<string>("");
    const [viewerError, setViewerError] = useState<string>("");

    const statusMessage = useMemo(() => STATUS_MESSAGES[messageIndex] ?? "Preparing...", [messageIndex]);

    const resetDemo = () => {
        setStage("idle");
        setCountdown(5);
        setMessageIndex(0);
        setPreviewToken(0);
        setPreviewFileName("");
        setCaptureStartMs(0);
        setEmail("");
        setEmailStatus("idle");
        setEmailError("");
        setViewerError("");
    };

    const startDemoCapture = () => {
        setEmail("");
        setEmailStatus("idle");
        setEmailError("");
        setViewerError("");
        setPreviewFileName("");
        setCaptureStartMs(0);
        setStage("countdown");
    };

    const sendEmail = () => {
        if (!email.trim()) {
            return;
        }
        setEmailStatus("sending");
        setEmailError("");

        const payload: { email: string; capture_file_name?: string } = {
            email: email.trim(),
        };
        if (previewFileName) {
            payload.capture_file_name = previewFileName;
        }

        fetch(`${apiBaseUrl}/api/demo/email-capture`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then(async (response) => {
                if (!response.ok) {
                    const detail = await response.json().catch(() => ({}));
                    throw new Error(detail.detail || `Failed to send email: ${response.status}`);
                }
                setEmailStatus("sent");
            })
            .catch((requestError) => {
                setEmailStatus("idle");
                setEmailError(
                    requestError instanceof Error ? requestError.message : "Unknown error while sending email",
                );
            });
    };

    const captureStitchedPointCloud = async () => {
        const response = await fetch(`${apiBaseUrl}/api/volumetric-capture`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });

        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail.detail || `Failed to capture point cloud: ${response.status}`);
        }

        const data = await response.json();
        const capturePath = typeof data?.capture_file_path === "string" ? data.capture_file_path : "";
        return capturePath.split(/[/\\]/).pop() || "";
    };

    useEffect(() => {
        if (stage !== "countdown") {
            return;
        }

        setCountdown(5);
        const timer = globalThis.setInterval(() => {
            setCountdown((current) => Math.max(current - 1, 0));
        }, 1000);

        return () => globalThis.clearInterval(timer);
    }, [stage]);

    useEffect(() => {
        if (stage === "countdown" && countdown === 0) {
            setStage("flash");
        }
    }, [stage, countdown]);

    useEffect(() => {
        if (stage !== "flash") {
            return;
        }

        let cancelled = false;
        const startedAt = Date.now();
        setViewerError("");
        setCaptureStartMs(startedAt);
        const flashTimer = globalThis.setTimeout(() => {
            setStage((current) => (current === "flash" ? "processing" : current));
        }, FLASH_DURATION_MS);

        captureStitchedPointCloud()
            .then((fileName) => {
                if (cancelled) {
                    return;
                }
                if (fileName) {
                    setPreviewFileName(fileName);
                }
            })
            .catch((requestError) => {
                if (cancelled) {
                    return;
                }
                setViewerError(
                    requestError instanceof Error ? requestError.message : "Unknown error while capturing point cloud",
                );
                setStage("review");
            });

        return () => {
            cancelled = true;
            globalThis.clearTimeout(flashTimer);
        };
    }, [stage]);

    useEffect(() => {
        if (stage !== "processing") {
            return;
        }

        if (!captureStartMs) {
            return;
        }

        setMessageIndex(Math.floor(Math.random() * STATUS_MESSAGES.length));
        setViewerError("");
        const interval = globalThis.setInterval(() => {
            setMessageIndex(Math.floor(Math.random() * STATUS_MESSAGES.length));
        }, MESSAGE_INTERVAL_MS);

        let cancelled = false;
        const poll = async () => {
            const query = new URLSearchParams();
            query.set("check", "1");
            query.set("after", captureStartMs.toString());
            if (previewFileName) {
                query.set("file", previewFileName);
            }

            try {
                const response = await fetch(`/api/demo-ply?${query.toString()}`);
                if (cancelled) {
                    return;
                }
                if (response.ok) {
                    setPreviewToken(Date.now());
                    setStage("review");
                }
            } catch {
                // Polling failures should not interrupt the demo flow.
            }
        };

        poll();
        const pollInterval = globalThis.setInterval(poll, 1200);

        return () => {
            cancelled = true;
            globalThis.clearInterval(interval);
            globalThis.clearInterval(pollInterval);
        };
    }, [stage, captureStartMs, previewFileName]);

    return (
        <main className="demo-shell">
            <header className="demo-hero">
                <div>
                    <p className="demo-pill">Demo Mode</p>
                    <h1>Capture a Moment in 3D</h1>
                    <p>Tap once, hold still, and watch the magic unfold. This is a guided capture flow for guests.</p>
                </div>
                <div className="demo-hero-actions">
                    <Link className="button-link secondary" href="/">
                        Back to Control Room
                    </Link>
                </div>
            </header>

            <section className="demo-action">
                <div>
                    <h2>Ready for the next guest?</h2>
                    <p>One tap starts the countdown, then we handle the rest.</p>
                </div>
                <button onClick={startDemoCapture} disabled={stage !== "idle"}>
                    {stage === "idle" ? "Start Capture" : "Capture in Progress"}
                </button>
            </section>

            {stage === "processing" && (
                <section className="demo-panel">
                    <div className="demo-processing">
                        <div className="demo-spinner" aria-hidden="true" />
                        <div>
                            <p className="demo-status">{statusMessage}</p>
                            <p className="demo-substatus">Building the volumetric preview...</p>
                        </div>
                    </div>
                </section>
            )}

            {stage === "review" && (
                <section className="demo-panel">
                    <p className="demo-status">Capture ready.</p>
                    <h2>3D Preview</h2>
                    {viewerError ? (
                        <p className="demo-substatus">{viewerError}</p>
                    ) : (
                        <PlyViewer
                            className="demo-preview-3d"
                            src={`/api/demo-ply?t=${previewToken}${previewFileName ? `&file=${encodeURIComponent(previewFileName)}` : ""}`}
                            onError={setViewerError}
                        />
                    )}
                    <div className="demo-choice">
                        <div>
                            <h3>Email this capture?</h3>
                            <p className="demo-substatus">We will send the preview and point cloud when the export finishes.</p>
                        </div>
                        <div className="demo-form">
                            <input
                                type="email"
                                value={email}
                                placeholder="guest@email.com"
                                onChange={(event) => setEmail(event.target.value)}
                                disabled={emailStatus === "sending" || emailStatus === "sent"}
                            />
                            <div className="demo-form-actions">
                                <button onClick={sendEmail} disabled={emailStatus !== "idle" || !email.trim()}>
                                    {emailStatus === "sending" ? "Sending..." : emailStatus === "sent" ? "Sent!" : "Email Me"}
                                </button>
                                <button className="secondary" onClick={resetDemo}>
                                    {emailStatus === "sent" ? "Start Next Capture" : "Skip"}
                                </button>
                            </div>
                            {emailError && <p className="demo-substatus">{emailError}</p>}
                        </div>
                    </div>
                </section>
            )}

            {stage === "countdown" && (
                <div className="demo-overlay" aria-live="polite">
                    <div className="demo-countdown">
                        <span>{Math.max(countdown, 1)}</span>
                        <p>Hold still...</p>
                    </div>
                </div>
            )}

            {stage === "flash" && <div className="flash-overlay" aria-hidden="true" />}
        </main>
    );
}
