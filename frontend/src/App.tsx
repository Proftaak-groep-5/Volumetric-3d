import React, { useState, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { CameraPreview } from './components/CameraPreview';
import { PointCloudViewer } from './components/PointCloudViewer';
import { CombinedPointCloudViewer } from './components/CombinedPointCloudViewer';
import { CalibrationPanel } from './components/CalibrationPanel';
import { RecordingControls } from './components/RecordingControls';
import { StatusBar } from './components/StatusBar';
import { CameraFrame, SystemStatus } from './types';
import './App.css';

function App() {
  const { isConnected, lastMessage, isPaused, pause, resume } = useWebSocket();
  const [frames, setFrames] = useState<{ [camera_id: string]: CameraFrame }>({});
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [viewMode, setViewMode] = useState<'color' | 'depth' | 'both' | 'pointcloud' | 'combined'>('both');
  const [showCalibration, setShowCalibration] = useState(false);

  useEffect(() => {
    if (lastMessage?.type === 'frames' && lastMessage.cameras) {
      setFrames(lastMessage.cameras);
    }
  }, [lastMessage]);

  const cameraIds = Object.keys(frames);
  const cameraCount = status?.cameras.count || cameraIds.length;

  return (
    <div className="app">
      <header className="app-header">
        <h1>📹 Multi-Camera 3D Recording Interface</h1>
        <p className="subtitle">Orbbec Femto Bolt • Real-time Depth & Color Streaming</p>
      </header>

      <main className="app-main">
        <StatusBar isConnected={isConnected} cameraCount={cameraCount} />

        <div className="main-grid">
          <div className="preview-section">
            <div className="section-header">
              <h2>Live Preview</h2>
              <div className="view-mode-toggle">
                <button
                  className={`toggle-btn ${viewMode === 'color' ? 'active' : ''}`}
                  onClick={() => setViewMode('color')}
                >
                  Color
                </button>
                <button
                  className={`toggle-btn ${viewMode === 'depth' ? 'active' : ''}`}
                  onClick={() => setViewMode('depth')}
                >
                  Depth
                </button>
                <button
                  className={`toggle-btn ${viewMode === 'both' ? 'active' : ''}`}
                  onClick={() => setViewMode('both')}
                >
                  Both
                </button>
                <button
                  className={`toggle-btn ${viewMode === 'pointcloud' ? 'active' : ''}`}
                  onClick={() => setViewMode('pointcloud')}
                >
                  🎯 3D Point Cloud
                </button>
                {cameraIds.length >= 2 && (
                  <button
                    className={`toggle-btn ${viewMode === 'combined' ? 'active' : ''}`}
                    onClick={() => setViewMode('combined')}
                  >
                    🎯 Combined 3D
                  </button>
                )}
              </div>
              <div className="control-buttons-header">
                <button
                  className={`control-btn ${isPaused ? 'paused' : ''}`}
                  onClick={isPaused ? resume : pause}
                  title={isPaused ? 'Resume feed' : 'Pause feed'}
                >
                  {isPaused ? '▶️ Resume' : '⏸️ Pause'}
                </button>
                <button
                  className="control-btn"
                  onClick={() => setShowCalibration(!showCalibration)}
                  title="Camera calibration"
                >
                  📐 Calibration
                </button>
              </div>
            </div>

            {cameraIds.length === 0 ? (
              <div className="no-cameras">
                <div className="no-cameras-content">
                  <div className="no-cameras-icon">📷</div>
                  <h3>No camera feed available</h3>
                  <p>Make sure cameras are connected and the backend is running.</p>
                  <div className="connection-status">
                    WebSocket: <strong>{isConnected ? '✅ Connected' : '❌ Disconnected'}</strong>
                  </div>
                </div>
              </div>
            ) : viewMode === 'pointcloud' ? (
              <div className="pointcloud-grid">
                {cameraIds.map((cameraId) => (
                  <PointCloudViewer
                    key={cameraId}
                    frame={frames[cameraId]}
                  />
                ))}
              </div>
            ) : viewMode === 'combined' ? (
              <CombinedPointCloudViewer frames={frames} />
            ) : (
              <div className="camera-grid">
                {cameraIds.map((cameraId) => (
                  <React.Fragment key={cameraId}>
                    {(viewMode === 'color' || viewMode === 'both') && (
                      <CameraPreview
                        frame={frames[cameraId]}
                        showDepth={false}
                      />
                    )}
                    {(viewMode === 'depth' || viewMode === 'both') && (
                      <CameraPreview
                        frame={frames[cameraId]}
                        showDepth={true}
                      />
                    )}
                  </React.Fragment>
                ))}
              </div>
            )}
          </div>

          <aside className="controls-section">
            <RecordingControls onStatusChange={setStatus} />
          </aside>
        </div>
      </main>

      {showCalibration && (
        <CalibrationPanel
          cameraIds={cameraIds}
          frames={frames}
          onClose={() => setShowCalibration(false)}
        />
      )}

      <footer className="app-footer">
        <p>MVP • Multi-Camera 3D Recording Interface • Fontys Semester 6</p>
      </footer>
    </div>
  );
}

export default App;

