import { SystemStatus, RecordingMetadata, CalibrationStatus, CameraCalibration, StereoCalibration } from '../types';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

export const api = {
  async getStatus(): Promise<SystemStatus> {
    const response = await fetch(`${API_URL}/api/status`);
    if (!response.ok) throw new Error('Failed to fetch status');
    return response.json();
  },

  async startRecording(): Promise<{ status: string; session_id: string; cameras: string[] }> {
    const response = await fetch(`${API_URL}/api/record/start`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to start recording');
    }
    return response.json();
  },

  async stopRecording(): Promise<{ status: string; metadata: RecordingMetadata }> {
    const response = await fetch(`${API_URL}/api/record/stop`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to stop recording');
    }
    return response.json();
  },

  async getRecordings(): Promise<{ recordings: RecordingMetadata[] }> {
    const response = await fetch(`${API_URL}/api/recordings`);
    if (!response.ok) throw new Error('Failed to fetch recordings');
    return response.json();
  },

  async getCameras(): Promise<{ cameras: any[] }> {
    const response = await fetch(`${API_URL}/api/cameras`);
    if (!response.ok) throw new Error('Failed to fetch cameras');
    return response.json();
  },

  async getCalibrationStatus(): Promise<CalibrationStatus> {
    const response = await fetch(`${API_URL}/api/calibration/status`);
    if (!response.ok) throw new Error('Failed to fetch calibration status');
    return response.json();
  },

  async getCameraCalibration(cameraId: string): Promise<CameraCalibration> {
    const response = await fetch(`${API_URL}/api/calibration/${cameraId}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch camera calibration');
    }
    return response.json();
  },

  async getStereoCalibration(cameraId1: string, cameraId2: string): Promise<StereoCalibration> {
    const response = await fetch(`${API_URL}/api/calibration/stereo/${cameraId1}/${cameraId2}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch stereo calibration');
    }
    return response.json();
  },

  async captureCalibrationImage(
    cameraId1: string,
    cameraId2: string,
    checkerboardCols: number = 8,
    checkerboardRows: number = 5
  ): Promise<{ success: boolean; image_index: number; total_captured: number; checkerboard_found: boolean }> {
    try {
      const response = await fetch(`${API_URL}/api/calibration/capture?camera_id_1=${cameraId1}&camera_id_2=${cameraId2}&checkerboard_cols=${checkerboardCols}&checkerboard_rows=${checkerboardRows}`, {
        method: 'POST',
      });
      if (!response.ok) {
        let errorDetail = 'Failed to capture calibration image';
        try {
          const error = await response.json();
          errorDetail = error.detail || error.message || errorDetail;
        } catch {
          errorDetail = `HTTP ${response.status}: ${response.statusText}`;
        }
        throw new Error(errorDetail);
      }
      return response.json();
    } catch (err: any) {
      // Re-throw with better error message
      if (err.message) {
        throw err;
      }
      throw new Error(`Failed to capture calibration image: ${err.toString()}`);
    }
  },

  async getCalibrationCaptureStatus(): Promise<{ total_captured: number; images: any[] }> {
    const response = await fetch(`${API_URL}/api/calibration/capture/status`);
    if (!response.ok) throw new Error('Failed to fetch calibration capture status');
    return response.json();
  },

  async clearCalibrationCaptures(): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${API_URL}/api/calibration/capture/clear`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to clear calibration captures');
    }
    return response.json();
  },

  async performStereoCalibration(
    cameraId1: string,
    cameraId2: string,
    checkerboardCols: number = 8,
    checkerboardRows: number = 5,
    squareSize: number = 0.025
  ): Promise<{ success: boolean; reprojection_error?: number; translation?: number[]; images_used: number }> {
    const response = await fetch(`${API_URL}/api/calibration/perform?camera_id_1=${cameraId1}&camera_id_2=${cameraId2}&checkerboard_cols=${checkerboardCols}&checkerboard_rows=${checkerboardRows}&square_size=${squareSize}`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to perform stereo calibration');
    }
    return response.json();
  },

  async checkCheckerboard(
    cameraId1: string,
    cameraId2: string,
    checkerboardCols: number = 8,
    checkerboardRows: number = 5
  ): Promise<{ camera_1: { detected: boolean; reason?: string }; camera_2: { detected: boolean; reason?: string }; both_detected: boolean; pattern_tested?: string }> {
    try {
      const response = await fetch(`${API_URL}/api/calibration/detect-checkerboard?camera_id_1=${cameraId1}&camera_id_2=${cameraId2}&checkerboard_cols=${checkerboardCols}&checkerboard_rows=${checkerboardRows}`);
      if (!response.ok) {
        let errorDetail = 'Failed to check checkerboard';
        try {
          const error = await response.json();
          errorDetail = error.detail || error.message || errorDetail;
        } catch {
          errorDetail = `HTTP ${response.status}: ${response.statusText}`;
        }
        throw new Error(errorDetail);
      }
      return response.json();
    } catch (err: any) {
      // Re-throw with better error message
      if (err.message) {
        throw err;
      }
      throw new Error(`Failed to check checkerboard: ${err.toString()}`);
    }
  },
};

