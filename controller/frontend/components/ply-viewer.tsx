"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

type PlyViewerProps = {
    src: string;
    className?: string;
    onError?: (message: string) => void;
};

export function PlyViewer({ src, className, onError }: Readonly<PlyViewerProps>) {
    const containerRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) {
            return;
        }

        let cancelled = false;
        let frameId = 0;
        let resizeObserver: ResizeObserver | null = null;
        let points: THREE.Points | null = null;

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        container.innerHTML = "";
        container.appendChild(renderer.domElement);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
        camera.position.set(0, 0.35, 1.6);

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.6;
        controls.minDistance = 0.2;
        controls.maxDistance = 10;

        scene.add(new THREE.AmbientLight(0xffffff, 0.9));
        const keyLight = new THREE.DirectionalLight(0xffffff, 0.6);
        keyLight.position.set(1.4, 1.2, 1.6);
        scene.add(keyLight);

        const resize = () => {
            const width = Math.max(container.clientWidth, 1);
            const height = Math.max(container.clientHeight, 1);
            renderer.setSize(width, height);
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
        };

        resize();

        if ("ResizeObserver" in window) {
            resizeObserver = new ResizeObserver(resize);
            resizeObserver.observe(container);
        } else {
            window.addEventListener("resize", resize);
        }

        const loader = new PLYLoader();
        loader.load(
            src,
            (geometry) => {
                if (cancelled) {
                    geometry.dispose();
                    return;
                }

                geometry.computeVertexNormals();
                geometry.center();

                const hasColors = geometry.hasAttribute("color");
                const material = new THREE.PointsMaterial({
                    size: 0.035,
                    vertexColors: hasColors,
                    color: hasColors ? 0xffffff : 0x50e3c2,
                });

                points = new THREE.Points(geometry, material);

                geometry.computeBoundingBox();
                if (geometry.boundingBox) {
                    const size = new THREE.Vector3();
                    geometry.boundingBox.getSize(size);
                    const maxAxis = Math.max(size.x, size.y, size.z);
                    const scale = maxAxis > 0 ? 1.4 / maxAxis : 1;
                    points.scale.setScalar(scale);
                }

                scene.add(points);
            },
            undefined,
            () => {
                if (!cancelled && onError) {
                    onError("3D preview unavailable. No .ply found yet.");
                }
            },
        );

        const animate = () => {
            frameId = window.requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        };

        animate();

        return () => {
            cancelled = true;
            if (frameId) {
                window.cancelAnimationFrame(frameId);
            }
            if (resizeObserver) {
                resizeObserver.disconnect();
            } else {
                window.removeEventListener("resize", resize);
            }
            controls.dispose();
            if (points) {
                points.geometry.dispose();
                if (Array.isArray(points.material)) {
                    points.material.forEach((material) => material.dispose());
                } else {
                    points.material.dispose();
                }
            }
            renderer.dispose();
            container.innerHTML = "";
        };
    }, [src, onError]);

    return <div className={className} ref={containerRef} />;
}
