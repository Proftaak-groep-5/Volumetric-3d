import React, { useEffect, useRef } from 'react';
import { CameraFrame } from '../types';
import './CameraPreview.css';

interface CameraPreviewProps {
  frame: CameraFrame | null;
  showDepth?: boolean;
}

export const CameraPreview: React.FC<CameraPreviewProps> = ({ frame, showDepth = false }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!frame || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const imageData = showDepth ? frame.depth_b64 : frame.color_b64;
    if (!imageData) return;

    // Create image from base64
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    // Both color and depth are now sent as JPEG
    img.src = `data:image/jpeg;base64,${imageData}`;
  }, [frame, showDepth]);

  if (!frame) {
    return (
      <div className="camera-preview-placeholder">
        <div className="placeholder-content">
          <div className="placeholder-icon">📷</div>
          <p>Waiting for camera feed...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="camera-preview">
      <div className="preview-header">
        <span className="camera-id">{frame.camera_id}</span>
        <span className="stream-type">{showDepth ? 'Depth' : 'Color'}</span>
        <span className="live-indicator">
          <span className="live-dot"></span> LIVE
        </span>
      </div>
      <canvas ref={canvasRef} className="preview-canvas" />
      <div className="preview-footer">
        <span className="timestamp">
          {new Date(frame.timestamp * 1000).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
};

