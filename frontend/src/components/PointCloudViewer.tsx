import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three-stdlib';
import { CameraFrame } from '../types';
import './PointCloudViewer.css';

interface PointCloudViewerProps {
  frame: CameraFrame | null;
}

export const PointCloudViewer: React.FC<PointCloudViewerProps> = ({ frame }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointCloudRef = useRef<THREE.Points | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const recordedFramesRef = useRef<Array<{timestamp: number, positions: Float32Array, colors: Float32Array}>>([]);
  
  const [pointCount, setPointCount] = useState(0);
  const [pointSize, setPointSize] = useState(0.01);
  const [isRecording, setIsRecording] = useState(false);
  const [recordedFrameCount, setRecordedFrameCount] = useState(0);

  // Initialize Three.js scene
  useEffect(() => {
    if (!containerRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a0a);
    sceneRef.current = scene;

    // Camera setup
    const camera = new THREE.PerspectiveCamera(
      60,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.01,
      100
    );
    camera.position.set(0, 0, 2);
    cameraRef.current = camera;

    // Renderer setup
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    // Add grid helper
    const gridHelper = new THREE.GridHelper(4, 20, 0x444444, 0x222222);
    scene.add(gridHelper);

    // Add axes helper
    const axesHelper = new THREE.AxesHelper(1);
    scene.add(axesHelper);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    // Animation loop
    const animate = () => {
      animationFrameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
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


  // Update point size
  useEffect(() => {
    if (pointCloudRef.current) {
      const material = pointCloudRef.current.material as THREE.PointsMaterial;
      material.size = pointSize;
    }
  }, [pointSize]);

  // Update point cloud when frame changes
  useEffect(() => {
    if (!frame || !sceneRef.current) return;
    if (!frame.depth_b64 || !frame.color_b64) return;

    // Decode depth and color images
    const depthImg = new Image();
    const colorImg = new Image();
    
    let depthLoaded = false;
    let colorLoaded = false;

    const generatePointCloud = () => {
      if (!depthLoaded || !colorLoaded) return;
      
      // Create canvases to extract pixel data
      const depthCanvas = document.createElement('canvas');
      const colorCanvas = document.createElement('canvas');
      
      depthCanvas.width = depthImg.width;
      depthCanvas.height = depthImg.height;
      colorCanvas.width = colorImg.width;
      colorCanvas.height = colorImg.height;
      
      const depthCtx = depthCanvas.getContext('2d');
      const colorCtx = colorCanvas.getContext('2d');
      
      if (!depthCtx || !colorCtx) return;
      
      depthCtx.drawImage(depthImg, 0, 0);
      colorCtx.drawImage(colorImg, 0, 0);
      
      const depthData = depthCtx.getImageData(0, 0, depthImg.width, depthImg.height);
      const colorData = colorCtx.getImageData(0, 0, colorImg.width, colorImg.height);
      
      // Camera intrinsics (estimated for Femto Bolt)
      const fx = 500; // Focal length X
      const fy = 500; // Focal length Y
      const cx = depthImg.width / 2;
      const cy = depthImg.height / 2;
      
      const positions: number[] = [];
      const colors: number[] = [];
      
      // Downsample for performance (every 2nd pixel)
      const step = 2;
      
      for (let v = 0; v < depthImg.height; v += step) {
        for (let u = 0; u < depthImg.width; u += step) {
          const depthIdx = (v * depthImg.width + u) * 4;
          
          // Get depth value (grayscale, so r=g=b)
          const depthValue = depthData.data[depthIdx];
          
          // Skip if depth is too low (invalid)
          if (depthValue < 10) continue;
          
          // Convert normalized depth (0-255) to actual depth in meters
          // Assuming max depth of 5 meters
          const z = (depthValue / 255.0) * 5.0;
          
          // Skip if too far
          if (z > 4.0) continue;
          
          // Calculate 3D position
          const x = ((u - cx) * z) / fx;
          const y = -((v - cy) * z) / fy; // Negative Y for proper orientation
          
          positions.push(x, y, -z); // Negative Z for proper viewing
          
          // Get color (match color image position, accounting for different resolutions)
          const colorU = Math.floor((u / depthImg.width) * colorImg.width);
          const colorV = Math.floor((v / depthImg.height) * colorImg.height);
          const colorIdx = (colorV * colorImg.width + colorU) * 4;
          
          const r = colorData.data[colorIdx] / 255;
          const g = colorData.data[colorIdx + 1] / 255;
          const b = colorData.data[colorIdx + 2] / 255;
          
          colors.push(r, g, b);
        }
      }
      
      setPointCount(positions.length / 3);
      
      // Remove old point cloud
      if (pointCloudRef.current) {
        sceneRef.current?.remove(pointCloudRef.current);
        pointCloudRef.current.geometry.dispose();
        if (Array.isArray(pointCloudRef.current.material)) {
          pointCloudRef.current.material.forEach(m => m.dispose());
        } else {
          pointCloudRef.current.material.dispose();
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
      pointCloudRef.current = pointCloud;
      sceneRef.current?.add(pointCloud);

      // Record frame if recording is active
      if (isRecording) {
        recordedFramesRef.current.push({
          timestamp: Date.now(),
          positions: new Float32Array(positions),
          colors: new Float32Array(colors),
        });
        setRecordedFrameCount(recordedFramesRef.current.length);
      }
    };

    depthImg.onload = () => {
      depthLoaded = true;
      generatePointCloud();
    };

    colorImg.onload = () => {
      colorLoaded = true;
      generatePointCloud();
    };

    depthImg.src = `data:image/jpeg;base64,${frame.depth_b64}`;
    colorImg.src = `data:image/jpeg;base64,${frame.color_b64}`;
  }, [frame, pointSize, isRecording]);

  // Screenshot functionality
  const takeScreenshot = () => {
    if (!rendererRef.current) return;
    
    const link = document.createElement('a');
    link.download = `pointcloud_${Date.now()}.png`;
    link.href = rendererRef.current.domElement.toDataURL('image/png');
    link.click();
  };

  // Recording controls
  const startRecording = () => {
    recordedFramesRef.current = [];
    setRecordedFrameCount(0);
    setIsRecording(true);
  };

  const stopRecording = () => {
    setIsRecording(false);
    
    if (recordedFramesRef.current.length === 0) {
      alert('No frames recorded');
      return;
    }

    // Export as JSON with point cloud data
    const recordingData = {
      metadata: {
        frameCount: recordedFramesRef.current.length,
        pointSize: pointSize,
        timestamp: new Date().toISOString(),
      },
      frames: recordedFramesRef.current.map((frame, index) => ({
        frameIndex: index,
        timestamp: frame.timestamp,
        pointCount: frame.positions.length / 3,
        // Convert to regular arrays for JSON
        positions: Array.from(frame.positions),
        colors: Array.from(frame.colors),
      })),
    };

    // Download as JSON
    const blob = new Blob([JSON.stringify(recordingData)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.download = `pointcloud_recording_${Date.now()}.json`;
    link.href = url;
    link.click();
    URL.revokeObjectURL(url);

    alert(`Point cloud recording saved! ${recordedFramesRef.current.length} frames`);
  };

  if (!frame) {
    return (
      <div className="pointcloud-placeholder">
        <div className="placeholder-content">
          <div className="placeholder-icon">🎯</div>
          <p>Waiting for camera data...</p>
          <p className="placeholder-hint">Point cloud requires both color and depth streams</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pointcloud-viewer">
      <div className="pointcloud-header">
        <span className="camera-id">{frame.camera_id}</span>
        <span className="view-type">3D Point Cloud</span>
        <span className="point-count">
          {pointCount.toLocaleString()} points
        </span>
        <span className="live-indicator">
          <span className="live-dot"></span> LIVE
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
            className="control-btn"
            onClick={takeScreenshot}
            title="Take screenshot"
          >
            📸 Screenshot
          </button>

          <button
            className={`control-btn ${isRecording ? 'recording' : ''}`}
            onClick={isRecording ? stopRecording : startRecording}
            title={isRecording ? 'Stop recording' : 'Start recording'}
          >
            {isRecording ? (
              <>⏹️ Stop ({recordedFrameCount} frames)</>
            ) : (
              <>🎥 Record</>
            )}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="pointcloud-container" />
      
      <div className="pointcloud-controls-hint">
        🖱️ Left: Rotate • Right: Pan • Scroll: Zoom
      </div>
    </div>
  );
};

