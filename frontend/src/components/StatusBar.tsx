import React from 'react';
import './StatusBar.css';

interface StatusBarProps {
  isConnected: boolean;
  cameraCount: number;
}

export const StatusBar: React.FC<StatusBarProps> = ({ isConnected, cameraCount }) => {
  return (
    <div className="status-bar">
      <div className="status-item">
        <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
        <span className="status-label">
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <div className="status-item">
        <span className="status-icon">📷</span>
        <span className="status-label">
          {cameraCount} Camera{cameraCount !== 1 ? 's' : ''}
        </span>
      </div>
    </div>
  );
};

