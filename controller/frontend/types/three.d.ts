declare module "three" {
    export class WebGLRenderer {
        domElement: HTMLCanvasElement;
        constructor(parameters?: Record<string, unknown>);
        setPixelRatio(value: number): void;
        setSize(width: number, height: number): void;
        render(scene: Scene, camera: PerspectiveCamera): void;
        dispose(): void;
    }

    export class Scene {
        add(object: unknown): void;
    }

    export class PerspectiveCamera {
        aspect: number;
        position: { set(x: number, y: number, z: number): void };
        constructor(fov: number, aspect: number, near: number, far: number);
        updateProjectionMatrix(): void;
    }

    export class AmbientLight {
        constructor(color: number, intensity: number);
    }

    export class DirectionalLight {
        position: { set(x: number, y: number, z: number): void };
        constructor(color: number, intensity: number);
    }

    export class Vector3 {
        x: number;
        y: number;
        z: number;
    }

    export class BufferGeometry {
        boundingBox: { getSize(target: Vector3): void } | null;
        dispose(): void;
        computeVertexNormals(): void;
        center(): void;
        hasAttribute(name: string): boolean;
        computeBoundingBox(): void;
    }

    export class PointsMaterial {
        constructor(parameters?: Record<string, unknown>);
        dispose(): void;
    }

    export class Points {
        geometry: BufferGeometry;
        material: PointsMaterial | PointsMaterial[];
        scale: { setScalar(value: number): void };
        constructor(geometry: BufferGeometry, material: PointsMaterial);
    }
}

declare module "three/examples/jsm/controls/OrbitControls.js" {
    import { PerspectiveCamera } from "three";

    export class OrbitControls {
        enableDamping: boolean;
        autoRotate: boolean;
        autoRotateSpeed: number;
        minDistance: number;
        maxDistance: number;
        constructor(camera: PerspectiveCamera, domElement: HTMLElement);
        update(): void;
        dispose(): void;
    }
}

declare module "three/examples/jsm/loaders/PLYLoader.js" {
    import { BufferGeometry } from "three";

    export class PLYLoader {
        load(
            url: string,
            onLoad: (geometry: BufferGeometry) => void,
            onProgress?: ((event: ProgressEvent) => void) | undefined,
            onError?: ((error: unknown) => void) | undefined,
        ): void;
    }
}
