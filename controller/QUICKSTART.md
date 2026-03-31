# Quick Start - Multi-Camera 3D Recording Interface

Kom snel aan de slag met de Multi-Camera 3D Recording Interface.

## ⚡ Snelstart (3 minuten)

### 1. Camera Testen (Optioneel maar aanbevolen)

Test eerst of je camera werkt:

```bash
cd backend
python camera_test.py
```

Verwacht: Een venster met diepte-preview. Druk ESC om te sluiten.

### 2. Backend Starten

**Windows:**
```cmd
cd backend
run.bat
```

**Linux/Mac:**
```bash
cd backend
chmod +x run.sh
./run.sh
```

Wacht tot je ziet: **"Backend ready! 🚀"**

### 3. Frontend Starten (Nieuwe Terminal)

**Windows:**
```cmd
cd frontend
run.bat
```

**Linux/Mac:**
```bash
cd frontend
chmod +x run.sh
./run.sh
```

Browser opent automatisch op http://localhost:3000

### 4. Eerste Opname

1. ✅ Check status bar toont "🟢 Connected"
2. 🎥 Zie live camera feed
3. 🔴 Klik "Start Recording"
4. ⏱️ Wacht 10 seconden
5. ⏹️ Klik "Stop Recording"
6. ✅ Check `backend/recordings/` voor nieuwe map

## 📁 Project Structuur

```
Local_Record_Interface/
├── backend/           # Python FastAPI server
│   ├── main.py        # Start hier
│   ├── run.bat        # Windows start script
│   └── run.sh         # Linux/Mac start script
├── frontend/          # React interface  
│   ├── src/           # React code
│   ├── run.bat        # Windows start script
│   └── run.sh         # Linux/Mac start script
└── README.md          # Volledige documentatie
```

## 🎯 Belangrijke URLs

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Status Check:** http://localhost:8000/api/status

## 🎮 Basis Gebruik

### Live Preview
- **Color**: RGB camera stream
- **Depth**: Diepte camera stream  
- **Both**: Beide streams naast elkaar (standaard)

### Opname
- **Start Recording**: Begin met opnemen van frames
- **Stop Recording**: Sla opname op naar disk

### Opname Output

Elke opname maakt een map aan: `backend/recordings/{timestamp}/`

Bevat:
- `meta.json` - Informatie over de sessie
- `cam0_frames.npz` - Alle frames (compressed)
- `cam0_sample.ply` - 3D point cloud voorbeeld

## 🔧 Snelle Configuratie

### Backend Poort Wijzigen

Edit `backend/.env`:
```env
BACKEND_PORT=9000
```

### Resolutie Verlagen (Voor betere performance)

Edit `backend/.env`:
```env
DEPTH_WIDTH=640
DEPTH_HEIGHT=400
COLOR_WIDTH=1280
COLOR_HEIGHT=720
FPS=15
```

## ❓ Problemen?

### Geen camera gevonden
```bash
# Test camera apart:
cd backend
python camera_test.py
```

### Backend start niet
```bash
# Check Python versie (moet 3.8+):
python --version

# Installeer dependencies opnieuw:
cd backend
pip install -r requirements.txt
```

### Frontend verbindt niet
1. Check backend draait: http://localhost:8000
2. Check browser console (F12) voor errors
3. Herlaad pagina (Ctrl+R of Cmd+R)

### WebSocket disconnected
- Herstart backend
- Herlaad frontend pagina
- Check firewall instellingen

## 🚀 Next Steps

Voor uitgebreide installatie en configuratie, zie:
- **SETUP.md** - Volledige setup instructies
- **README.md** - Complete project documentatie
- **backend/README.md** - Backend API details
- **frontend/README.md** - Frontend development

## 💡 Tips

- **Multi-camera**: Sluit meerdere cameras aan → worden automatisch gedetecteerd
- **Performance**: Verlaag resolutie in `.env` voor snellere streaming
- **Kwaliteit**: Verhoog FPS en resolutie voor betere 3D reconstructie
- **Storage**: Check disk space voor lange opnames (1GB per minuut @ full resolution)

## 📊 Opname Analyseren

Load opname in Python:
```python
import numpy as np

# Load frames
data = np.load('backend/recordings/20241106_153045/cam0_frames.npz')
depth_frames = data['depth_frames']
color_frames = data['color_frames']
timestamps = data['timestamps']

print(f"Recorded {len(timestamps)} frames")
print(f"Depth shape: {depth_frames.shape}")
print(f"Color shape: {color_frames.shape}")
```

## 🎥 Demo Workflow

Typische workflow voor 3D scan:

1. **Setup**
   - Start backend en frontend
   - Positioneer camera(s)
   - Check live preview kwaliteit

2. **Opname**
   - Klik "Start Recording"
   - Voer actie uit / beweeg object
   - Klik "Stop Recording"

3. **Export**
   - Vind opname in `recordings/`
   - Load `.npz` voor processing
   - Gebruik `.ply` voor 3D preview

4. **Processing** (toekomstig)
   - Point cloud reconstruction
   - Multi-camera fusion
   - 3D model export

---

**Veel succes! Bij vragen zie SETUP.md of README.md** 🎬

