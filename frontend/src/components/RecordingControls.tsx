import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { SystemStatus } from '../types';
import './RecordingControls.css';

interface RecordingControlsProps {
  onStatusChange?: (status: SystemStatus) => void;
}

export const RecordingControls: React.FC<RecordingControlsProps> = ({ onStatusChange }) => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [recordingDuration, setRecordingDuration] = useState(0);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isRecording) {
      const interval = setInterval(() => {
        setRecordingDuration(prev => prev + 1);
      }, 1000);
      return () => clearInterval(interval);
    } else {
      setRecordingDuration(0);
    }
  }, [isRecording]);

  const fetchStatus = async () => {
    try {
      const data = await api.getStatus();
      setStatus(data);
      setIsRecording(data.recording.is_recording);
      if (data.recording.session_id) {
        setSessionId(data.recording.session_id);
      }
      if (onStatusChange) {
        onStatusChange(data);
      }
    } catch (err) {
      console.error('Error fetching status:', err);
    }
  };

  const handleStartRecording = async () => {
    try {
      setError('');
      const response = await api.startRecording();
      setIsRecording(true);
      setSessionId(response.session_id);
      setRecordingDuration(0);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleStopRecording = async () => {
    try {
      setError('');
      await api.stopRecording();
      setIsRecording(false);
      setSessionId('');
      fetchStatus();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="recording-controls">
      <div className="controls-header">
        <h2>Recording Controls</h2>
        {status && (
          <div className="status-badges">
            <span className={`badge ${status.cameras.active ? 'badge-success' : 'badge-error'}`}>
              {status.cameras.count} Camera{status.cameras.count !== 1 ? 's' : ''}
            </span>
            <span className={`badge ${status.websocket_clients > 0 ? 'badge-success' : 'badge-warning'}`}>
              {status.websocket_clients} Client{status.websocket_clients !== 1 ? 's' : ''}
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="error-message">
          ⚠️ {error}
        </div>
      )}

      <div className="controls-body">
        {isRecording ? (
          <div className="recording-active">
            <div className="recording-indicator">
              <span className="recording-dot"></span>
              <span className="recording-text">RECORDING</span>
            </div>
            <div className="recording-info">
              <div className="info-item">
                <label>Session ID:</label>
                <span className="mono">{sessionId}</span>
              </div>
              <div className="info-item">
                <label>Duration:</label>
                <span className="mono duration">{formatDuration(recordingDuration)}</span>
              </div>
              {status?.recording.frame_count !== undefined && (
                <div className="info-item">
                  <label>Frames:</label>
                  <span className="mono">{status.recording.frame_count}</span>
                </div>
              )}
            </div>
            <button
              onClick={handleStopRecording}
              className="btn btn-stop"
            >
              ⏹️ Stop Recording
            </button>
          </div>
        ) : (
          <div className="recording-idle">
            <p className="idle-message">
              {status?.cameras.active 
                ? 'Ready to record' 
                : 'No cameras detected'}
            </p>
            <button
              onClick={handleStartRecording}
              disabled={!status?.cameras.active}
              className="btn btn-record"
            >
              ⏺️ Start Recording
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

