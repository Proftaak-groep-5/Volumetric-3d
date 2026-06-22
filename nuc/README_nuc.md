# FemtoBoltNuc

`FemtoBoltNuc` is a Windows x64 C++ service for an Intel NUC with one Orbbec Femto Bolt over USB.

Current scope in this repository:

- auto-detect/open the camera with Orbbec SDK v2
- capture color + depth
- serve REST + WebSocket endpoints
- publish browser preview as JPEG-over-WebSocket
- publish authoritative compressed 16-bit depth frames over WebSocket
- export true 16-bit PNG depth snapshots
- support a one-shot `--test-capture` mode for bring-up on a NUC
- support no-camera operation with optional synthetic color/depth frames

Not implemented in this pass:

- WebRTC
- auth
- cloud/fleet features

## Stable vs placeholder

Currently considered stable for the next hardware pass:

- REST and WebSocket server startup even with no camera attached
- degraded no-camera mode
- optional synthetic frame mode for preview, snapshots, and depth transport
- bounded JPEG-over-WebSocket preview path
- versioned authoritative depth packet framing
- true 16-bit PNG depth snapshots
- startup logging for dependency expectations and runtime DLL requirements

Currently still placeholder / intentionally temporary:

- browser preview transport is JPEG-over-WebSocket, not WebRTC
- preview publisher is behind `IPreviewPublisher`, but only the JPEG implementation exists
- `/stats` contains throughput and frame counters, but not true CPU/memory instrumentation
- point cloud browser rendering and WebRTC signaling are not implemented

## 1. Windows build requirements

Required for full functionality:

- Windows 10/11 x64
- Visual Studio 2022 with Desktop C++ workload
- CMake 3.24+
- Orbbec SDK v2 for Windows
- GStreamer 1.0 MSVC x64 runtime + development files

Not separately required by default:

- `zstd` is fetched and linked by CMake when `NUC_FETCH_DEPS=ON` (default)
- `Crow`, `spdlog`, and `nlohmann/json` are also fetched by CMake by default

## 2. Expected install locations

### Orbbec SDK v2

Expected install root:

- `C:\Program Files\OrbbecSDK 2.7.6`

Expected CMake package location:

- `C:\Program Files\OrbbecSDK 2.7.6\lib`

Alternative environment variables supported by this repo:

- `OrbbecSDK_DIR`
- `ORBBECSDK_ROOT`
- `ORBBEC_SDK_ROOT`

Important Windows metadata step:

- Run the Orbbec metadata registration script as Administrator after installing the SDK.
- Typical path:
  - `C:\Program Files\OrbbecSDK 2.7.6\shared\obsensor_metadata_win10.ps1`

### GStreamer

Recommended install root:

- `C:\gstreamer\1.0\msvc_x86_64`

Alternative supported environment variables:

- `GSTREAMER_ROOT_DIR`
- `GSTREAMER_1_0_ROOT_MSVC_X86_64`
- `GSTREAMER_1_0_ROOT_X86_64`

The build expects headers under:

- `include\gstreamer-1.0`
- `include\glib-2.0`
- `lib\glib-2.0\include`

Recommended runtime environment on the NUC:

```powershell
$env:PATH="C:\Program Files\OrbbecSDK\bin;C:\gstreamer\1.0\msvc_x86_64\bin;$env:PATH"
$env:GST_PLUGIN_PATH="C:\gstreamer\1.0\msvc_x86_64\lib\gstreamer-1.0"
$env:GST_PLUGIN_SCANNER="C:\gstreamer\1.0\msvc_x86_64\libexec\gstreamer-1.0\gst-plugin-scanner.exe"
```

## 3. Configure and build

Run these from:

- `x64 Native Tools Command Prompt for VS 2022`
- or `Developer PowerShell for VS 2022`

### Visual Studio generator

```powershell
cmake -S . -B build-vs -G "Visual Studio 17 2022" -A x64 `
  -DNUC_REQUIRE_ORBBEC=ON `
  -DNUC_REQUIRE_GSTREAMER=ON `
  -DNUC_FETCH_DEPS=ON `
  -DOrbbecSDK_DIR="C:\Program Files\OrbbecSDK 2.7.6\lib" `
  -DGSTREAMER_ROOT_DIR="C:\gstreamer\1.0\msvc_x86_64"

cmake --build build-vs --config Release --target FemtoBoltNuc
```

### Ninja generator

```powershell
cmake -S . -B build-ninja -G Ninja `
  -DNUC_REQUIRE_ORBBEC=ON `
  -DNUC_REQUIRE_GSTREAMER=ON `
  -DNUC_FETCH_DEPS=ON `
  -DOrbbecSDK_DIR="C:\Program Files\OrbbecSDK 2.7.6\lib" `
  -DGSTREAMER_ROOT_DIR="C:\gstreamer\1.0\msvc_x86_64"

cmake --build build-ninja --config Release
```

If a dependency is missing, configure now fails with explicit hints showing:

- which environment variables are accepted
- the expected install root layout
- the concrete paths CMake searched

## 4. Runtime DLL requirements

### Orbbec

Required at runtime:

- `OrbbecSDK.dll`

Easiest approach:

- add the Orbbec SDK `bin` directory to `PATH`
- or copy `OrbbecSDK.dll` beside `FemtoBoltNuc.exe`

### GStreamer

Required at runtime from the GStreamer MSVC x64 install:

- `gstreamer-1.0-0.dll`
- `gstapp-1.0-0.dll`
- `gstbase-1.0-0.dll`
- `gstvideo-1.0-0.dll`
- `gobject-2.0-0.dll`
- `glib-2.0-0.dll`
- `intl-8.dll`
- `iconv-2.dll`
- `orc-0.4-0.dll`

Required plugin path:

- `lib\gstreamer-1.0`

The preview path currently depends on JPEG encoding, so the JPEG plugin must also be available in the plugin directory.

If the plugin path is wrong at runtime, preview startup now logs explicit errors for missing `jpegenc` or `videoconvert`.

Easiest approach on the NUC:

- keep `C:\gstreamer\1.0\msvc_x86_64\bin` on `PATH`
- keep the matching `lib\gstreamer-1.0` tree in place

### zstd

- no separate runtime DLL is required in the default build path here because zstd is linked from the fetched build

## 5. Run modes

### Normal service mode

```powershell
.\build-vs\Release\FemtoBoltNuc.exe --config .\config\example.json
```

Expected startup behavior:

- process starts even if no camera is present
- `/health` returns `degraded` until a camera is connected
- startup logs list the expected Orbbec and GStreamer roots and DLL/plugin requirements
- when the Femto Bolt is detected, logs show the selected serial/model
- service exposes HTTP on the configured port, default `8080`

Expected no-camera behavior:

- endpoints still respond
- `/metadata` reports `source.mode = "no_camera"` or `source.mode = "synthetic"`
- if `synthetic_input.enabled = true` and `use_when_no_camera = true`, synthetic frames drive preview, snapshots, and depth transport

### One-shot validation mode

This is the fastest way to validate a Windows NUC + Femto Bolt setup.

```powershell
.\build-vs\Release\FemtoBoltNuc.exe `
  --config .\config\example.json `
  --test-capture .\capture-out
```

Expected output files:

- `.\capture-out\metadata.json`
- `.\capture-out\color.jpg`
- `.\capture-out\depth.png`

Expected successful log pattern:

- `event=camera state=connected ...` or `event=synthetic_source state=active ...`
- metadata JSON printed
- `test capture saved color=True depth=True output=...`

Expected exit code:

- `0` on success

If the camera does not connect or frames are not captured within the timeout, the process exits non-zero.

## 6. HTTP and WebSocket endpoints

- `GET /`
- `GET /health`
- `GET /heartbeat`
- `GET /metadata`
- `GET /streams`
- `GET /settings`
- `POST /settings`
- `POST /settings/restart-streams`
- `GET /capabilities`
- `GET /stats`
- `POST /control/reconnect`
- `POST /control/restart`
- `GET /snapshot/color.jpg`
- `GET /snapshot/depth.png`
- `GET /snapshot/depth.bin`
- `GET /discovery`
- `GET /description.xml`
- `WS /ws/preview/color`
- `WS /ws/preview/depth`
- `WS /ws/depth`
- `WS /ws/logs`

## 7. Preview behavior

Preview is intentionally simple and bounded:

- input is RGB from the Orbbec capture path
- frames are resized to configured preview resolution before entering GStreamer
- preview FPS is rate-limited to configured FPS
- if the encoder is busy or the frame arrives too soon, the frame is dropped
- the GStreamer queue is bounded and leaky; it does not grow without bound

This is the current browser-compatible fallback and is the intended state for this pass.

The swap point for future WebRTC work is `IPreviewPublisher`. The expected future GStreamer shape is:

- `appsrc ! videoconvert ! queue leaky=downstream max-size-buffers=2 ! x264enc tune=zerolatency ... ! rtph264pay ! webrtcbin`

## 8. Authoritative depth packet schema

Wire format for each `WS /ws/depth` binary message:

### Prefix

Little-endian binary prefix, 16 bytes total:

1. `magic[4]`
   - ASCII: `OBD1`
2. `uint16 schema_version`
   - currently `1`
3. `uint16 flags`
   - currently `0`
4. `uint32 header_json_bytes`
5. `uint32 payload_bytes`

### Body

1. UTF-8 JSON header, length = `header_json_bytes`
2. compressed payload, length = `payload_bytes`

### JSON header fields

- `schema_version`
- `frame_index`
- `source_timestamp_us`
- `system_timestamp_us`
- `width`
- `height`
- `stride_bytes`
- `pixel_format`
- `compression_type`
- `uncompressed_byte_size`
- `compressed_byte_size`
- `depth_scale`
- `depth_units`
- `invalid_pixel_value`
- `intrinsics_reference`

Current compression:

- `zstd`

Expected transport log line while depth is flowing:

- `event=depth_binary fps=<value> avg_bytes=<value> ratio=<value> raw_mbps=<value> transport_mbps=<value>`

Depth semantics:

- payload represents raw 16-bit depth values
- millimeters are computed as:
  - `depth_mm = raw_value * depth_scale`
- invalid depth is currently represented as raw value `0`

## 9. JavaScript depth client example

See [nuc/examples/depth_packet_client.js](nuc/examples/depth_packet_client.js).

Minimal parser:

```js
const ws = new WebSocket("ws://127.0.0.1:8080/ws/depth");
ws.binaryType = "arraybuffer";

ws.onmessage = (event) => {
  const view = new DataView(event.data);
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== "OBD1") return;

  const schemaVersion = view.getUint16(4, true);
  const flags = view.getUint16(6, true);
  const headerLength = view.getUint32(8, true);
  const payloadLength = view.getUint32(12, true);

  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(event.data, 16, headerLength)));
  const payload = new Uint8Array(event.data, 16 + headerLength, payloadLength);

  console.log({ schemaVersion, flags, frame: header.frame_index, width: header.width, height: header.height, payloadBytes: payload.byteLength });
};
```

## 10. C++ depth client example

See [nuc/examples/depth_packet_client.cpp](nuc/examples/depth_packet_client.cpp).

That example assumes you already have one full websocket message in a `std::vector<uint8_t>`, then:

- validates the `OBD1` prefix
- parses the JSON header
- decompresses the zstd payload
- interprets the result as `uint16_t` depth samples

## 11. Depth snapshot behavior

`GET /snapshot/depth.png` now returns a true 16-bit grayscale PNG generated from the latest raw depth frame.

Response headers include:

- `X-Depth-Scale`
- `X-Depth-Width`
- `X-Depth-Height`
- `X-Depth-Pixel-Format`
- `X-Depth-Units`

## 12. Example commands

```powershell
curl http://localhost:8080/health
curl http://localhost:8080/metadata
curl http://localhost:8080/stats
curl http://localhost:8080/snapshot/depth.png -o depth.png
curl -X POST http://localhost:8080/control/reconnect
curl -X POST http://localhost:8080/settings `
  -H "Content-Type: application/json" `
  -d "{\"depth_preview\":{\"min_depth_mm\":500,\"max_depth_mm\":3500}}"
```

## 13. Honest status

This repository is now aimed at a hardware test-ready Windows bring-up path:

- build the binary on a Windows NUC
- run `--test-capture`
- confirm `metadata.json`, `color.jpg`, and `depth.png`
- run the long-lived service
- confirm `/health`, `/metadata`, preview websockets, and `WS /ws/depth`

What is still intentionally not in scope here:

- WebRTC
- authentication
- production installer/packager
- multi-camera orchestration

