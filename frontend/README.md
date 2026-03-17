# Multi-Camera 3D Recording Interface - Frontend

React + TypeScript frontend for real-time camera streaming and recording controls.

## Features

- 🎥 Live preview of color and depth streams via WebSocket
- 🔴 Recording controls with real-time status
- 📊 Multi-camera support with grid view
- 🎨 Modern, glassmorphic UI design
- 🔄 Automatic WebSocket reconnection
- 📱 Responsive layout

## Setup

### Prerequisites

- Node.js 16+ and npm
- Backend server running (see backend/README.md)

### Installation

```bash
cd frontend
npm install
```

### Configuration

Create `.env` file in the `frontend` directory:

```env
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000/ws
```

## Development

```bash
npm start
```

Opens at [http://localhost:3000](http://localhost:3000)

## Build for Production

```bash
npm run build
```

Builds optimized production files to `build/` directory.

## Project Structure

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── components/
│   │   ├── CameraPreview.tsx     # Live camera feed display
│   │   ├── CameraPreview.css
│   │   ├── RecordingControls.tsx # Recording start/stop
│   │   ├── RecordingControls.css
│   │   ├── StatusBar.tsx          # Connection status
│   │   └── StatusBar.css
│   ├── hooks/
│   │   └── useWebSocket.ts        # WebSocket hook
│   ├── services/
│   │   └── api.ts                 # REST API client
│   ├── types.ts                   # TypeScript types
│   ├── App.tsx                    # Main app component
│   ├── App.css
│   ├── index.tsx
│   └── index.css
├── package.json
└── tsconfig.json
```

## Usage

1. Ensure backend is running
2. Start frontend with `npm start`
3. Open browser to [http://localhost:3000](http://localhost:3000)
4. View live camera feeds
5. Click "Start Recording" to begin recording
6. Click "Stop Recording" to finalize and save

## View Modes

- **Color**: Show only RGB streams
- **Depth**: Show only depth maps
- **Both**: Show color and depth side-by-side (default)

## WebSocket Protocol

The frontend receives real-time frames via WebSocket:

```typescript
{
  "type": "frames",
  "cameras": {
    "cam0": {
      "camera_id": "cam0",
      "timestamp": 1730900000.123,
      "color_b64": "base64_encoded_jpeg",
      "depth_b64": "base64_encoded_png",
      "color_shape": [1080, 1920, 3],
      "depth_shape": [1024, 1024]
    }
  }
}
```

## Troubleshooting

### WebSocket not connecting

- Check backend is running on correct port
- Verify REACT_APP_WS_URL in `.env`
- Check browser console for errors

### No camera feed

- Ensure cameras are connected to backend
- Check backend logs for camera initialization
- Verify camera permissions and drivers

