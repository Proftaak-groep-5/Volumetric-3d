import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services/api';
import { CalibrationStatus } from '../types';
import './CalibrationPanel.css';

import { CameraFrame } from '../types';

interface CalibrationPanelProps {
  cameraIds: string[];
  frames: { [camera_id: string]: CameraFrame | null };
  onClose: () => void;
}

export const CalibrationPanel: React.FC<CalibrationPanelProps> = ({ cameraIds, frames, onClose }) => {
  const [calibrationStatus, setCalibrationStatus] = useState<CalibrationStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [capturedCount, setCapturedCount] = useState(0);
  const [checkerboardCols, setCheckerboardCols] = useState(8);
  const [checkerboardRows, setCheckerboardRows] = useState(5);
  const [squareSize, setSquareSize] = useState(0.025);
  const [checkerboardDetected, setCheckerboardDetected] = useState<{ [key: string]: boolean }>({});
  const [logs, setLogs] = useState<Array<{ timestamp: Date; level: 'info' | 'error' | 'success' | 'warning'; message: string }>>([]);
  
  // Refs to prevent duplicate logs and excessive updates
  const lastLogMessage = useRef<string>('');
  const lastLogTime = useRef<number>(0);
  const isCheckingCheckerboard = useRef<boolean>(false);
  const lastCheckerboardState = useRef<{ [key: string]: boolean }>({});

  const addLog = useCallback((level: 'info' | 'error' | 'success' | 'warning', message: string) => {
    const now = Date.now();
    // Prevent duplicate logs within 1 second
    if (message === lastLogMessage.current && (now - lastLogTime.current) < 1000) {
      return;
    }
    
    lastLogMessage.current = message;
    lastLogTime.current = now;
    
    const timestamp = new Date();
    setLogs(prev => {
      const newLogs = [...prev, { timestamp, level, message }];
      return newLogs.slice(-50); // Keep last 50 logs
    });
    // Also log to console for debugging
    console.log(`[Calibration ${level.toUpperCase()}] ${message}`);
  }, []);

  // Only load calibration status once when component mounts or cameraIds change significantly
  useEffect(() => {
    if (cameraIds.length > 0) {
      loadCalibrationStatus();
      loadCaptureStatus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraIds.length]); // Only depend on length, not the array itself

  // Poll for capture status - less frequently
  useEffect(() => {
    if (capturing) {
      const interval = setInterval(() => {
        loadCaptureStatus();
      }, 3000); // Check every 3 seconds instead of 1
      return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capturing]);

  // Check for checkerboard in frames - throttled
  useEffect(() => {
    if (cameraIds.length >= 2 && capturing && !isCheckingCheckerboard.current) {
      const interval = setInterval(() => {
        if (!isCheckingCheckerboard.current) {
          checkCheckerboard();
        }
      }, 2000); // Check every 2 seconds instead of 500ms
      return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capturing, cameraIds.length, checkerboardCols, checkerboardRows]); // Removed frames dependency

  const loadCalibrationStatus = useCallback(async () => {
    try {
      setLoading(true);
      const status = await api.getCalibrationStatus();
      setCalibrationStatus(status);
      setError(null);
      // Only log on first load or if there's a change
      if (!calibrationStatus) {
        addLog('success', 'Calibration status loaded');
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load calibration status';
      setError(errorMsg);
      addLog('error', errorMsg);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addLog]);

  const loadCaptureStatus = useCallback(async () => {
    try {
      const status = await api.getCalibrationCaptureStatus();
      const newCount = status.total_captured;
      if (newCount !== capturedCount) {
        setCapturedCount(newCount);
        // Only log when count actually changes and is > 0
        if (newCount > 0 && newCount !== capturedCount) {
          addLog('info', `Captured: ${newCount} image pairs`);
        }
      }
    } catch (err: any) {
      // Don't log every error, only first one
      if (!error) {
        addLog('warning', `Failed to load capture status: ${err.message || 'Unknown error'}`);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capturedCount, addLog]);

  const checkCheckerboard = useCallback(async () => {
    if (cameraIds.length < 2 || isCheckingCheckerboard.current) return;
    
    isCheckingCheckerboard.current = true;
    
    try {
      const result = await api.checkCheckerboard(
        cameraIds[0],
        cameraIds[1],
        checkerboardCols,
        checkerboardRows
      );
      
      const detected1 = result.camera_1.detected;
      const detected2 = result.camera_2.detected;
      
      const newState = {
        [cameraIds[0]]: detected1,
        [cameraIds[1]]: detected2
      };
      
      // Only update if state changed
      const stateChanged = 
        newState[cameraIds[0]] !== lastCheckerboardState.current[cameraIds[0]] ||
        newState[cameraIds[1]] !== lastCheckerboardState.current[cameraIds[1]];
      
      if (stateChanged) {
        setCheckerboardDetected(newState);
        lastCheckerboardState.current = newState;
        
        // Only log state changes, not every check
        if (detected1 && detected2) {
          addLog('success', `Checkerboard detected in both cameras (pattern: ${result.pattern_tested || 'unknown'})`);
        } else {
          // Log reasons only on first detection failure or when reason changes
          if (!detected1 && result.camera_1.reason) {
            addLog('warning', `Camera ${cameraIds[0]}: ${result.camera_1.reason}`);
          }
          if (!detected2 && result.camera_2.reason) {
            addLog('warning', `Camera ${cameraIds[1]}: ${result.camera_2.reason}`);
          }
          if (!detected1 && !detected2) {
            addLog('info', `Tip: Count the INNER corners (not squares). Pattern tested: ${result.pattern_tested || 'unknown'}`);
          }
        }
      }
    } catch (err: any) {
      // Only log errors once
      let errorMsg = 'Unknown error';
      if (err.message) {
        errorMsg = err.message;
      } else if (typeof err === 'string') {
        errorMsg = err;
      } else if (err.detail) {
        errorMsg = err.detail;
      }
      
      const fullErrorMsg = `Checkerboard check failed: ${errorMsg}`;
      if (lastLogMessage.current !== fullErrorMsg) {
        addLog('error', fullErrorMsg);
      }
      setCheckerboardDetected({
        [cameraIds[0]]: false,
        [cameraIds[1]]: false
      });
    } finally {
      isCheckingCheckerboard.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraIds, checkerboardCols, checkerboardRows, addLog]);

  const startCalibrationCapture = async () => {
    if (cameraIds.length < 2) {
      const errorMsg = 'Need at least 2 cameras for stereo calibration';
      setError(errorMsg);
      addLog('error', errorMsg);
      return;
    }

    addLog('info', 'Starting calibration capture mode...');
    addLog('info', `Using cameras: ${cameraIds[0]} and ${cameraIds[1]}`);
    addLog('info', `Checkerboard pattern: ${checkerboardCols}x${checkerboardRows} inner corners`);

    // Clear previous captures
    try {
      await api.clearCalibrationCaptures();
      addLog('info', 'Previous captures cleared');
    } catch (err: any) {
      addLog('warning', `Failed to clear previous captures: ${err.message || 'Unknown error'}`);
    }

    setCapturing(true);
    setCapturedCount(0);
    setError(null);
    setSuccess(null);
    addLog('success', 'Capture mode started. Make sure cameras are streaming and checkerboard is visible.');
  };

  const captureImage = async () => {
    if (cameraIds.length < 2) return;

    const cam1 = cameraIds[0];
    const cam2 = cameraIds[1];

    try {
      setError(null);
      addLog('info', `Attempting to capture image pair from ${cam1} and ${cam2}...`);
      
      const result = await api.captureCalibrationImage(
        cam1,
        cam2,
        checkerboardCols,
        checkerboardRows
      );
      
      setCapturedCount(result.total_captured);
      const successMsg = `Captured image pair ${result.total_captured}!`;
      setSuccess(successMsg);
      addLog('success', successMsg);
      
      // Clear success message after 2 seconds
      setTimeout(() => setSuccess(null), 2000);
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to capture image';
      setError(errorMsg);
      addLog('error', `Capture failed: ${errorMsg}`);
    }
  };

  const stopCapture = () => {
    setCapturing(false);
  };

  const performCalibration = async () => {
    if (cameraIds.length < 2) {
      const errorMsg = 'Need at least 2 cameras for stereo calibration';
      setError(errorMsg);
      addLog('error', errorMsg);
      return;
    }

    if (capturedCount < 10) {
      const errorMsg = `Need at least 10 captured image pairs, currently have ${capturedCount}`;
      setError(errorMsg);
      addLog('error', errorMsg);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      const cam1 = cameraIds[0];
      const cam2 = cameraIds[1];
      
      addLog('info', `Starting stereo calibration with ${capturedCount} image pairs...`);
      addLog('info', `Settings: ${checkerboardCols}x${checkerboardRows} pattern, ${squareSize}m square size`);
      
      const result = await api.performStereoCalibration(
        cam1,
        cam2,
        checkerboardCols,
        checkerboardRows,
        squareSize
      );
      
      const successMsg = `Calibration successful! Used ${result.images_used} image pairs. ` +
        (result.translation ? `Translation: [${result.translation.map(t => t.toFixed(4)).join(', ')}]` : '') +
        (result.reprojection_error ? ` Reprojection error: ${result.reprojection_error.toFixed(4)}` : '');
      
      setSuccess(successMsg);
      addLog('success', successMsg);
      
      await loadCalibrationStatus();
      
      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err: any) {
      const errorMsg = err.message || 'Calibration failed';
      setError(errorMsg);
      addLog('error', `Calibration failed: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !calibrationStatus) {
    return (
      <div className="calibration-panel-overlay">
        <div className="calibration-panel">
          <div className="calibration-loading">Loading calibration status...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="calibration-panel-overlay" onClick={onClose}>
      <div className="calibration-panel" onClick={(e) => e.stopPropagation()}>
        <div className="calibration-header">
          <h2>📐 Camera Calibration</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="calibration-content">
          {error && (
            <div className="calibration-error">
              ⚠️ {error}
            </div>
          )}

          {success && (
            <div className="calibration-success">
              ✓ {success}
            </div>
          )}

          <div className="calibration-section">
            <h3>Camera Intrinsics</h3>
            {calibrationStatus && Object.entries(calibrationStatus.cameras).map(([cameraId, status]) => (
              <div key={cameraId} className="calibration-item">
                <div className="calibration-item-header">
                  <strong>{cameraId}</strong>
                  <span className={`status-badge ${status.calibrated ? 'calibrated' : 'not-calibrated'}`}>
                    {status.calibrated ? '✓ Calibrated' : '✗ Not Calibrated'}
                  </span>
                </div>
                {status.has_intrinsics && status.intrinsics && (
                  <div className="calibration-details">
                    <div>Resolution: {status.depth_resolution?.join('x')}</div>
                    <div>fx: {status.intrinsics.fx.toFixed(2)}, fy: {status.intrinsics.fy.toFixed(2)}</div>
                    <div>cx: {status.intrinsics.cx.toFixed(2)}, cy: {status.intrinsics.cy.toFixed(2)}</div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {cameraIds.length >= 2 && (
            <div className="calibration-section">
              <h3>Stereo Calibration</h3>
              
              {capturing && (
                <div className="calibration-capture-mode">
                  <div className="capture-status">
                    <strong>Capture Mode Active</strong>
                    <div className="capture-count">
                      Captured: {capturedCount} / 20 (minimum 10 required)
                    </div>
                  </div>
                  <div className="capture-instructions">
                    <p>1. Place the checkerboard in view of both cameras</p>
                    <p>2. Move the checkerboard to different positions and angles</p>
                    <p>3. Click "Capture Image" when checkerboard is visible in both views</p>
                    <p>4. Capture at least 10-20 image pairs</p>
                  </div>
                  <div className="capture-actions">
                    <button
                      className="calibration-btn primary"
                      onClick={captureImage}
                      disabled={loading}
                    >
                      📸 Capture Image
                    </button>
                    <button
                      className="calibration-btn"
                      onClick={stopCapture}
                    >
                      Stop Capture
                    </button>
                  </div>
                  {Object.keys(checkerboardDetected).length > 0 && (
                    <div className="checkerboard-status">
                      Checkerboard detection:
                      {cameraIds.map(id => (
                        <span key={id} className={checkerboardDetected[id] ? 'detected' : 'not-detected'}>
                          {id}: {checkerboardDetected[id] ? '✓' : '✗'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {calibrationStatus && Object.entries(calibrationStatus.stereo).map(([key, status]) => (
                <div key={key} className="calibration-item">
                  <div className="calibration-item-header">
                    <strong>{key.replace('_', ' ↔ ')}</strong>
                    <span className={`status-badge ${status.calibrated ? 'calibrated' : 'not-calibrated'}`}>
                      {status.calibrated ? '✓ Calibrated' : '✗ Not Calibrated'}
                    </span>
                  </div>
                  {status.calibrated && status.translation && (
                    <div className="calibration-details">
                      <div>Translation: [
                        {status.translation[0]?.toFixed(4) ?? 'N/A'}, 
                        {status.translation[1]?.toFixed(4) ?? 'N/A'}, 
                        {status.translation[2]?.toFixed(4) ?? 'N/A'}
                      ]</div>
                    </div>
                  )}
                </div>
              ))}

              {(!calibrationStatus || Object.keys(calibrationStatus.stereo).length === 0) && !capturing && (
                <div className="calibration-item">
                  <p>No stereo calibration found. Start capture mode to calibrate.</p>
                </div>
              )}
            </div>
          )}

          <div className="calibration-section">
            <h3>Calibration Settings</h3>
            <div className="calibration-settings">
              <div className="setting-item">
                <label>Checkerboard Columns (inner corners):</label>
                <input
                  type="number"
                  min="3"
                  max="20"
                  value={checkerboardCols}
                  onChange={(e) => setCheckerboardCols(parseInt(e.target.value))}
                />
              </div>
              <div className="setting-item">
                <label>Checkerboard Rows (inner corners):</label>
                <input
                  type="number"
                  min="3"
                  max="20"
                  value={checkerboardRows}
                  onChange={(e) => setCheckerboardRows(parseInt(e.target.value))}
                />
              </div>
              <div className="setting-item">
                <label>Square Size (meters):</label>
                <input
                  type="number"
                  min="0.001"
                  max="1"
                  step="0.001"
                  value={squareSize}
                  onChange={(e) => setSquareSize(parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>

          <div className="calibration-actions">
            <button
              className="calibration-btn primary"
              onClick={() => {
                addLog('info', 'Manually refreshing calibration status...');
                loadCalibrationStatus();
              }}
              disabled={loading}
            >
              {loading ? '⏳ Loading...' : '🔄 Refresh Status'}
            </button>
            {cameraIds.length >= 2 && (
              <>
                {!capturing ? (
                  <button
                    className="calibration-btn primary"
                    onClick={startCalibrationCapture}
                    disabled={loading}
                  >
                    📸 Start Capture Mode
                  </button>
                ) : null}
                <button
                  className="calibration-btn"
                  onClick={performCalibration}
                  disabled={loading || capturedCount < 10}
                  title={capturedCount < 10 ? `Need at least 10 images, have ${capturedCount}` : 'Perform calibration'}
                >
                  ⚙️ Perform Calibration ({capturedCount} images)
                </button>
                {capturedCount > 0 && (
                  <button
                    className="calibration-btn"
                    onClick={async () => {
                      try {
                        await api.clearCalibrationCaptures();
                        setCapturedCount(0);
                        setSuccess('Captured images cleared');
                        setTimeout(() => setSuccess(null), 2000);
                      } catch (err: any) {
                        setError(err.message || 'Failed to clear captures');
                      }
                    }}
                    disabled={loading}
                  >
                    🗑️ Clear Captures
                  </button>
                )}
              </>
            )}
          </div>

          <div className="calibration-info">
            <h4>Instructions:</h4>
            <ol>
              <li><strong>IMPORTANT:</strong> Make sure cameras are streaming (live view active)</li>
              <li><strong>CRITICAL:</strong> Count the <strong>INNER CORNERS</strong> (not squares!)</li>
              <li style={{color: '#ffaa44'}}>
                <strong>Example:</strong> If you see 6 rows and 8 columns of squares, 
                you have <strong>5 inner corners</strong> (rows) and <strong>7 inner corners</strong> (columns)
              </li>
              <li>Print the checkerboard pattern from <code>backend/checkerboard_9x6.png</code></li>
              <li>Measure a square to verify it's exactly {squareSize * 1000}mm</li>
              <li>Mount on a flat, rigid surface (cardboard, foam board)</li>
              <li>Click "Start Capture Mode" and capture 10-20 image pairs</li>
              <li>Click "Perform Calibration" to calculate stereo parameters</li>
              <li>Calibration files are saved automatically in ./calibrations/</li>
            </ol>
            <div style={{marginTop: '15px', padding: '10px', background: '#2a2a1a', borderRadius: '6px', border: '1px solid #ffaa44'}}>
              <strong style={{color: '#ffaa44'}}>💡 Tip:</strong> If detection fails, try adjusting the pattern size. 
              The system will automatically try alternative sizes, but you can manually change the columns/rows above.
            </div>
          </div>

          <div className="calibration-logs">
            <h4>Log Feed</h4>
            <div className="logs-container">
              {logs.length === 0 ? (
                <div className="log-empty">No logs yet...</div>
              ) : (
                logs.map((log, idx) => (
                  <div key={idx} className={`log-entry log-${log.level}`}>
                    <span className="log-time">
                      {log.timestamp.toLocaleTimeString()}
                    </span>
                    <span className="log-message">{log.message}</span>
                  </div>
                ))
              )}
            </div>
            {logs.length > 0 && (
              <button
                className="calibration-btn small"
                onClick={() => setLogs([])}
              >
                Clear Logs
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

