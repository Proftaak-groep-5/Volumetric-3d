import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three-stdlib';
import { CameraFrame } from '../types';
import { api } from '../services/api';
import './PointCloudViewer.css';

interface CombinedPointCloudViewerProps {
  frames: { [camera_id: string]: CameraFrame | null };
}

export const CombinedPointCloudViewer: React.FC<CombinedPointCloudViewerProps> = ({ frames }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointCloudsRef = useRef<Map<string, THREE.Points>>(new Map());
  const animationFrameRef = useRef<number | null>(null);
  
  const [pointCount, setPointCount] = useState(0);
  const [pointSize, setPointSize] = useState(0.01);
  const [calibrationLoaded, setCalibrationLoaded] = useState(false);
  const [stereoCalibration, setStereoCalibration] = useState<any>(null);
  const [isLive, setIsLive] = useState(true);
  const [capturedFrames, setCapturedFrames] = useState<{ [camera_id: string]: CameraFrame | null }>({});

  // Initialize Three.js scene
  useEffect(() => {
    if (!containerRef.current) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a0a);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(
      60,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.01,
      100
    );
    camera.position.set(0, 0, 2);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    const gridHelper = new THREE.GridHelper(4, 20, 0x444444, 0x222222);
    scene.add(gridHelper);

    const axesHelper = new THREE.AxesHelper(1);
    scene.add(axesHelper);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    const animate = () => {
      animationFrameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!containerRef.current || !camera || !renderer) return;
      const width = containerRef.current.clientWidth;
      const height = containerRef.current.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      renderer.dispose();
      controls.dispose();
      if (containerRef.current && renderer.domElement) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Load stereo calibration
  useEffect(() => {
    const cameraIds = Object.keys(frames).filter(id => frames[id] !== null);
    if (cameraIds.length >= 2) {
      api.getStereoCalibration(cameraIds[0], cameraIds[1])
        .then(calib => {
          setStereoCalibration(calib);
          setCalibrationLoaded(true);
        })
        .catch(err => {
          console.warn('Stereo calibration not found, using default alignment:', err);
          setCalibrationLoaded(true);
        });
    }
  }, [frames]);


  // Update point size
  useEffect(() => {
    pointCloudsRef.current.forEach(pointCloud => {
      const material = pointCloud.material as THREE.PointsMaterial;
      material.size = pointSize;
    });
  }, [pointSize]);

  // Transform point cloud using stereo calibration
  const transformPoints = (points: number[], R?: number[][], T?: number[][]): number[] => {
    if (!R || !T) return points; // No transformation if calibration not available
    
    const transformed: number[] = [];
    const rotationMatrix = new THREE.Matrix3().fromArray(R.flat());
    const translation = new THREE.Vector3(T[0][0], T[1][0], T[2][0]);
    
    for (let i = 0; i < points.length; i += 3) {
      const point = new THREE.Vector3(points[i], points[i + 1], points[i + 2]);
      point.applyMatrix3(rotationMatrix);
      point.add(translation);
      transformed.push(point.x, point.y, point.z);
    }
    
    return transformed;
  };

  // Generate point cloud from frame (async)
  const generatePointCloud = async (
    frame: CameraFrame,
    cameraId: string,
    applyTransform: boolean = false
  ): Promise<{ positions: number[]; colors: number[] }> => {
    if (!frame.depth_b64 || !frame.color_b64) {
      return { positions: [], colors: [] };
    }

    return new Promise<{ positions: number[]; colors: number[] }>((resolve) => {
      const depthImg = new Image();
      const colorImg = new Image();
      
      let depthLoaded = false;
      let colorLoaded = false;

      const process = async () => {
        if (!depthLoaded || !colorLoaded) return;

        const depthCanvas = document.createElement('canvas');
        const colorCanvas = document.createElement('canvas');
        
        depthCanvas.width = depthImg.width;
        depthCanvas.height = depthImg.height;
        colorCanvas.width = colorImg.width;
        colorCanvas.height = colorImg.height;
        
        const depthCtx = depthCanvas.getContext('2d');
        const colorCtx = colorCanvas.getContext('2d');
        
        if (!depthCtx || !colorCtx) {
          resolve({ positions: [], colors: [] });
          return;
        }
        
        depthCtx.drawImage(depthImg, 0, 0);
        colorCtx.drawImage(colorImg, 0, 0);
        
        const depthData = depthCtx.getImageData(0, 0, depthImg.width, depthImg.height);
        const colorData = colorCtx.getImageData(0, 0, colorImg.width, colorImg.height);
        
        // Get calibration intrinsics, fallback to estimates
        let fx = depthImg.width * 0.65;
        let fy = depthImg.height * 0.65;
        let cx = depthImg.width / 2;
        let cy = depthImg.height / 2;

        try {
          const calib = await api.getCameraCalibration(cameraId);
          if (calib.depth_intrinsics) {
            fx = calib.depth_intrinsics.fx;
            fy = calib.depth_intrinsics.fy;
            cx = calib.depth_intrinsics.cx;
            cy = calib.depth_intrinsics.cy;
          }
        } catch {
          // Use defaults already set
        }

        const positions: number[] = [];
        const colors: number[] = [];
        const step = 2;

        for (let v = 0; v < depthImg.height; v += step) {
          for (let u = 0; u < depthImg.width; u += step) {
            const depthIdx = (v * depthImg.width + u) * 4;
            const depthValue = depthData.data[depthIdx];
            
            if (depthValue < 10) continue;
            const z = (depthValue / 255.0) * 5.0;
            if (z > 4.0) continue;
            
            const x = ((u - cx) * z) / fx;
            const y = -((v - cy) * z) / fy;
            
            positions.push(x, y, -z);
            
            const colorU = Math.floor((u / depthImg.width) * colorImg.width);
            const colorV = Math.floor((v / depthImg.height) * colorImg.height);
            const colorIdx = (colorV * colorImg.width + colorU) * 4;
            
            colors.push(
              colorData.data[colorIdx] / 255,
              colorData.data[colorIdx + 1] / 255,
              colorData.data[colorIdx + 2] / 255
            );
          }
        }

        // Apply stereo transformation if needed
        let finalPositions = positions;
        if (applyTransform && stereoCalibration) {
          finalPositions = transformPoints(
            positions,
            stereoCalibration.R,
            stereoCalibration.T
          );
        }

        resolve({ positions: finalPositions, colors });
      };

      depthImg.onload = () => {
        depthLoaded = true;
        process();
      };

      colorImg.onload = () => {
        colorLoaded = true;
        process();
      };

      depthImg.src = `data:image/jpeg;base64,${frame.depth_b64}`;
      colorImg.src = `data:image/jpeg;base64,${frame.color_b64}`;
    });
  };

  // Capture frames when switching to capture mode
  useEffect(() => {
    if (!isLive) {
      setCapturedFrames({ ...frames });
    }
  }, [isLive]);

  // Update point clouds when frames change (only in live mode) or when captured frames change
  useEffect(() => {
    if (!sceneRef.current || !calibrationLoaded) return;

    const cameraIds = Object.keys(frames).filter(id => frames[id] !== null);
    if (cameraIds.length < 2) return;

    // Use captured frames if in capture mode, otherwise use live frames
    const framesToUse = isLive ? frames : capturedFrames;
    const activeCameraIds = Object.keys(framesToUse).filter(id => framesToUse[id] !== null);
    if (activeCameraIds.length < 2) return;

    let totalPoints = 0;
    let processedCount = 0;

    activeCameraIds.forEach(async (cameraId, index) => {
      const frame = framesToUse[cameraId];
      if (!frame) return;

      const isSecondCamera = index === 1;
      try {
        const { positions, colors } = await generatePointCloud(frame, cameraId, isSecondCamera);
        if (positions.length === 0) {
          processedCount++;
          if (processedCount === activeCameraIds.length) {
            setPointCount(totalPoints);
          }
          return;
        }

        totalPoints += positions.length / 3;

        // Remove old point cloud for this camera
        const oldPointCloud = pointCloudsRef.current.get(cameraId);
        if (oldPointCloud) {
          sceneRef.current?.remove(oldPointCloud);
          oldPointCloud.geometry.dispose();
          if (Array.isArray(oldPointCloud.material)) {
            oldPointCloud.material.forEach(m => m.dispose());
          } else {
            oldPointCloud.material.dispose();
          }
        }

        // Create new point cloud
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
          size: pointSize,
          vertexColors: true,
          sizeAttenuation: true,
        });

        const pointCloud = new THREE.Points(geometry, material);
        pointCloudsRef.current.set(cameraId, pointCloud);
        sceneRef.current?.add(pointCloud);

        processedCount++;
        if (processedCount === activeCameraIds.length) {
          setPointCount(totalPoints);
        }
      } catch (error) {
        console.error(`Error generating point cloud for ${cameraId}:`, error);
        processedCount++;
        if (processedCount === activeCameraIds.length) {
          setPointCount(totalPoints);
        }
      }
    });
  }, [isLive ? frames : capturedFrames, pointSize, calibrationLoaded, stereoCalibration, isLive]);

  const takeScreenshot = () => {
    if (!rendererRef.current) return;
    const link = document.createElement('a');
    link.download = `combined_pointcloud_${Date.now()}.png`;
    link.href = rendererRef.current.domElement.toDataURL('image/png');
    link.click();
  };

  const toggleLiveCapture = () => {
    if (isLive) {
      // Switching to capture mode - capture current frames
      setCapturedFrames({ ...frames });
    }
    setIsLive(!isLive);
  };

  const exportPointCloud = async () => {
    // Use captured frames if in capture mode, otherwise use current frames
    const framesToUse = isLive ? frames : capturedFrames;
    const cameraIds = Object.keys(framesToUse).filter(id => framesToUse[id] !== null);
    if (cameraIds.length < 2) {
      alert('Need at least 2 cameras for combined point cloud');
      return;
    }

    const allPositions: number[] = [];
    const allColors: number[] = [];

    for (let i = 0; i < cameraIds.length; i++) {
      const cameraId = cameraIds[i];
      const frame = framesToUse[cameraId];
      if (!frame) continue;

      const isSecondCamera = i === 1;
      const { positions, colors } = await generatePointCloud(frame, cameraId, isSecondCamera);
      allPositions.push(...positions);
      allColors.push(...colors);
    }

    // Export as PLY file
    const plyContent = `ply
format ascii 1.0
element vertex ${allPositions.length / 3}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
${Array.from({ length: allPositions.length / 3 }, (_, i) => {
  const x = allPositions[i * 3];
  const y = allPositions[i * 3 + 1];
  const z = allPositions[i * 3 + 2];
  const r = Math.round(allColors[i * 3] * 255);
  const g = Math.round(allColors[i * 3 + 1] * 255);
  const b = Math.round(allColors[i * 3 + 2] * 255);
  return `${x} ${y} ${z} ${r} ${g} ${b}`;
}).join('\n')}`;

    const blob = new Blob([plyContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.download = `combined_pointcloud_${Date.now()}.ply`;
    link.href = url;
    link.click();
    URL.revokeObjectURL(url);

    alert(`Point cloud exported! ${(allPositions.length / 3).toLocaleString()} points`);
  };

  const cameraIds = Object.keys(frames).filter(id => frames[id] !== null);
  if (cameraIds.length < 2) {
    return (
      <div className="pointcloud-placeholder">
        <div className="placeholder-content">
          <div className="placeholder-icon">🎯</div>
          <p>Need at least 2 cameras for combined view</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pointcloud-viewer">
      <div className="pointcloud-header">
        <span className="view-type">Combined 3D Point Cloud</span>
        <span className="point-count">
          {pointCount.toLocaleString()} points
        </span>
        <span className={`live-indicator ${!isLive ? 'captured' : ''}`}>
          <span className="live-dot"></span> {isLive ? 'LIVE' : 'CAPTURED'}
        </span>
      </div>
      
      <div className="pointcloud-controls">
        <div className="control-group">
          <label htmlFor="pointSize">Point Size: {pointSize.toFixed(3)}</label>
          <input
            id="pointSize"
            type="range"
            min="0.001"
            max="0.05"
            step="0.001"
            value={pointSize}
            onChange={(e) => setPointSize(parseFloat(e.target.value))}
            className="slider"
          />
        </div>

        <div className="control-buttons">
          <button
            className={`control-btn ${isLive ? 'active' : ''}`}
            onClick={toggleLiveCapture}
            title={isLive ? 'Capture current frame' : 'Switch to live view'}
          >
            {isLive ? '📷 Capture' : '▶️ Live'}
          </button>

          <button
            className="control-btn"
            onClick={takeScreenshot}
            title="Take screenshot"
          >
            📸 Screenshot
          </button>

          <button
            className="control-btn export-btn"
            onClick={exportPointCloud}
            title="Export as PLY file"
          >
            💾 Export PLY
          </button>
        </div>
      </div>

      <div ref={containerRef} className="pointcloud-container" />
      
      <div className="pointcloud-controls-hint">
        🖱️ Left: Rotate • Right: Pan • Scroll: Zoom
        {!calibrationLoaded && <span className="calibration-warning"> (Loading calibration...)</span>}
      </div>
    </div>
  );
};

