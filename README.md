# 8======D

# Multi-Camera 3D Recording Interface (MVP)

Een minimale maar werkende applicatie voor real-time streaming, weergave en opname van diepte- en kleurdata van Orbbec Femto Bolt camera's.

## 🎯 Overzicht

Dit project biedt een complete oplossing voor het opnemen van gesynchroniseerde 3D-data van meerdere Orbbec Femto Bolt camera's:

- **Backend (Python/FastAPI)**: WebSocket streaming, camera management, en opname naar disk
- **Frontend (React/TypeScript)**: Live preview, opnamecontroles, en moderne UI

## ✨ Features

### MVP Features
- ✅ Live preview van kleur + diepte streams via WebSocket
- ✅ Opname starten/stoppen vanuit React interface
- ✅ Opslag van 3D-framegegevens in `.npz` formaat
- ✅ Multi-camera ondersteuning (voorbereid)
- ✅ Sample point cloud export (`.ply` formaat)
- ✅ Metadata tracking per sessie

### Toekomstige Uitbreidingen
- 🔄 Multi-camera kalibratie
- 🎨 Real-time puntwolk visualisatie (three.js)
- 📊 Timecode synchronisatie
- ☁️ Cloud opslag integratie

## 🏗️ Architectuur

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  • Live WebSocket preview                            │
│  • Recording controls                                │
│  • Status monitoring                                 │
└──────────────────┬──────────────────────────────────┘
                   │ WebSocket + REST API
┌──────────────────┴──────────────────────────────────┐
│              FastAPI Backend                         │
│  • WebSocket server voor live frames                │
│  • Camera manager (Orbbec SDK)                       │
│  • Recording manager                                 │
│  • File I/O (.npz, .ply)                             │
└──────────────────┬──────────────────────────────────┘
                   │ pyorbbecsdk
┌──────────────────┴──────────────────────────────────┐
│           Orbbec Femto Bolt Camera(s)                │
│  • Depth stream (1024x1024 @ 30fps)                 │
│  • Color stream (1920x1080 @ 30fps)                 │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Optie 1: Docker (Aanbevolen)

```bash
# Build en start alle containers
docker-compose up -d

# Bekijk logs
docker-compose logs -f
```

De applicatie is dan beschikbaar op:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Zie [DOCKER.md](DOCKER.md) voor gedetailleerde Docker instructies.

### Optie 2: Lokale Installatie

#### Vereisten

- Python 3.8+
- Node.js 16+
- Orbbec SDK geïnstalleerd
- Orbbec Femto Bolt camera aangesloten

#### Backend Setup

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Backend draait op http://localhost:8000

#### Frontend Setup

```bash
cd frontend
npm install
npm start
```

Frontend opent op http://localhost:3000

## 📁 Project Structuur

```
Local_Record_Interface/
├── backend/
│   ├── main.py              # FastAPI applicatie + WebSocket
│   ├── camera_manager.py    # Orbbec camera interface
│   ├── recorder.py          # Recording management
│   ├── config.py            # Configuratie
│   ├── requirements.txt     # Python dependencies
│   └── recordings/          # Opgeslagen recordings
│
├── frontend/
│   ├── src/
│   │   ├── components/      # React componenten
│   │   ├── hooks/           # Custom hooks (WebSocket)
│   │   ├── services/        # API client
│   │   ├── App.tsx          # Hoofd applicatie
│   │   └── types.ts         # TypeScript types
│   ├── package.json
│   └── public/
│
└── README.md                # Dit bestand
```

## 🎥 Gebruik

1. **Start Backend**
   ```bash
   cd backend
   python main.py
   ```

2. **Start Frontend**
   ```bash
   cd frontend
   npm start
   ```

3. **Open Browser**
   - Navigeer naar http://localhost:3000
   - Bekijk live camera feeds
   - Klik "Start Recording" om opname te beginnen
   - Klik "Stop Recording" om op te slaan

## 💾 Opname Formaat

Elke opname sessie creëert een map: `backend/recordings/{timestamp}/`

**Inhoud:**
- `meta.json` - Sessie metadata (camera's, tijden, frame count)
- `cam0_frames.npz` - Compressed NumPy arrays met color en depth frames
- `cam0_sample.ply` - Sample point cloud van eerste frame

**NPZ Structuur:**
```python
{
    'timestamps': np.array([...]),
    'frame_indices': np.array([...]),
    'depth_frames': np.array([...]),  # Shape: (N, H, W)
    'color_frames': np.array([...]),  # Shape: (N, H, W, 3)
}
```

## 🔌 API Endpoints

### REST API

- `GET /api/status` - Systeem status
- `GET /api/cameras` - Lijst van camera's
- `POST /api/record/start` - Start opname
- `POST /api/record/stop` - Stop opname
- `GET /api/recordings` - Lijst alle recordings

### WebSocket

- `WS /ws` - Live frame streaming

**Frame bericht formaat:**
```json
{
  "type": "frames",
  "cameras": {
    "cam0": {
      "camera_id": "cam0",
      "timestamp": 1730900000.123,
      "color_b64": "...",
      "depth_b64": "...",
      "color_shape": [1080, 1920, 3],
      "depth_shape": [1024, 1024]
    }
  }
}
```

## ⚙️ Configuratie

### Backend (.env)
```env
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
RECORDINGS_PATH=./recordings
DEPTH_WIDTH=1024
DEPTH_HEIGHT=1024
COLOR_WIDTH=1920
COLOR_HEIGHT=1080
FPS=30
```

### Frontend (.env)
```env
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:8000/ws
```

## 🛠️ Ontwikkeling

### Python Dependencies
```bash
pip install -r backend/requirements.txt
```

Belangrijkste packages:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `websockets` - WebSocket support
- `numpy` - Array operations
- `opencv-python` - Image processing
- `pyorbbecsdk` - Orbbec camera SDK (apart installeren)

### Frontend Dependencies
```bash
npm install
```

React + TypeScript met custom WebSocket hook voor real-time streaming.

## 📝 Oorspronkelijke Camera Code

De meegeleverde Python code voor directe camera-toegang is geïntegreerd in `camera_manager.py`:

```python
# Originele code werkte met cv2.imshow
# Nieuwe implementatie: WebSocket streaming naar React
```

## 🐛 Troubleshooting

### Geen camera's gevonden
- Controleer USB-verbinding
- Installeer Orbbec SDK drivers
- Run `lsusb` (Linux) of Device Manager (Windows)

### WebSocket verbinding mislukt
- Check backend draait op poort 8000
- Controleer firewall instellingen
- Verify REACT_APP_WS_URL in frontend/.env

### Opname mislukt
- Check disk space
- Verify RECORDINGS_PATH schrijfrechten
- Bekijk backend logs

## 👥 Team

Fontys - Semester 6 (Software) - Group Project

## 📄 License

Internal project - Fontys Hogeschool

## 🔗 Links

- [Orbbec SDK Documentation](https://github.com/orbbec/pyorbbecsdk)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)

---

**Status**: MVP Complete ✅

Voor vragen of problemen, zie de README's in de `backend/` en `frontend/` mappen.

