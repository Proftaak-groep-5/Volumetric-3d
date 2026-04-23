# FemtoBoltNuc Deployment

## Bundle

Build and stage a deployable Release bundle:

```powershell
cmake --build build-vs2026 --target FemtoBoltNuc --config Release
cmake --install build-vs2026 --config Release --prefix .\dist-release
```

The staged runtime bundle is expected to contain:

- `FemtoBoltNuc.exe`
- runtime DLLs beside the EXE
- `OrbbecSDKConfig.xml`
- `extensions\...`
- `gstreamer-plugins\...`
- `gstreamer-libexec\gstreamer-1.0\gst-plugin-scanner.exe`
- `config\example.json`

## NUC Prerequisites

Install on the NUC:

1. Orbbec SDK 2.7.6 x64
2. Run `C:\Program Files\OrbbecSDK 2.7.6\shared\obsensor_metadata_win10.ps1` as Administrator
3. Plug in the Femto Bolt and confirm it appears in Device Manager

GStreamer is optional if you deploy the full bundle above, because the app prefers bundled plugins and scanner files.

## Run

From the bundle directory:

```powershell
.\FemtoBoltNuc.exe --config .\config\example.json
```

Then open:

- `http://localhost:8080/`
- `http://localhost:8080/health`
- `http://localhost:8080/snapshot/color.jpg`
- `http://localhost:8080/snapshot/depth-preview.jpg`

## Autostart

For a simple startup shortcut:

1. Create a shortcut to `FemtoBoltNuc.exe`
2. Set `Start in` to the bundle directory
3. Add arguments: `--config .\config\example.json`
4. Place the shortcut in `shell:startup`

For a more robust setup, wrap it with NSSM or Task Scheduler.
