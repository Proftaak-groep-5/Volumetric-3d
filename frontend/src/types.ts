export interface CameraFrame {
  camera_id: string;
  timestamp: number;
  color_b64?: string;
  depth_b64?: string;
  color_shape?: number[];
  depth_shape?: number[];
}

export interface FrameMessage {
  type: 'frames' | 'status';
  cameras?: {
    [camera_id: string]: CameraFrame;
  };
  data?: any;
}

export interface SystemStatus {
  cameras: {
    count: number;
    active: boolean;
  };
  recording: {
    is_recording: boolean;
    session_id?: string;
    frame_count?: number;
    duration?: number;
  };
  websocket_clients: number;
}

export interface RecordingMetadata {
  session_id: string;
  start_time: string;
  end_time?: string;
  duration_seconds?: number;
  camera_ids: string[];
  camera_count: number;
  total_frames: number;
  status: string;
}

export interface CameraCalibration {
  camera_id: string;
  camera_matrix?: number[][];
  distortion_coeffs?: number[];
  depth_intrinsics?: {
    fx: number;
    fy: number;
    cx: number;
    cy: number;
    width: number;
    height: number;
  };
  color_intrinsics?: {
    fx: number;
    fy: number;
    cx: number;
    cy: number;
    width: number;
    height: number;
  };
  depth_resolution?: [number, number];
  color_resolution?: [number, number];
}

export interface StereoCalibration {
  camera_id_1: string;
  camera_id_2: string;
  R?: number[][];
  T?: number[][];
  E?: number[][];
  F?: number[][];
}

export interface CalibrationStatus {
  cameras: {
    [camera_id: string]: {
      calibrated: boolean;
      has_intrinsics?: boolean;
      depth_resolution?: [number, number];
      color_resolution?: [number, number];
      intrinsics?: {
        fx: number;
        fy: number;
        cx: number;
        cy: number;
        width: number;
        height: number;
      };
    };
  };
  stereo: {
    [key: string]: {
      calibrated: boolean;
      translation?: number[]; // Flat array [x, y, z]
    };
  };
}

