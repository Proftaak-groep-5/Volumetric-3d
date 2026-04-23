# FemtoBoltNuc Tasks

## Current plan
- Stabilize the current vertical slice for hardware testing.
- Keep the service usable without hardware through degraded no-camera mode and synthetic frames.
- Keep preview bounded and keep the authoritative depth packet schema explicit.
- Prepare the preview publisher boundary for a later WebRTC implementation.

## Completed
- Inspected the workspace and confirmed the repo had to be created from scratch.
- Pulled Orbbec SDK v2 primary-source headers and API surfaces for device, pipeline, frame, calibration, and property control.
- Locked the initial module layout and build/dependency strategy for Windows 10/11 x64 with Visual Studio 2022.
- Scaffolded the CMake project, dependency discovery, config example, README, and task tracking.
- Implemented the Orbbec camera wrapper, preview publishers, authoritative depth publisher, HTTP/WebSocket server, SSDP announcer, and embedded diagnostics page.
- Added raw frame retention and one-shot `--test-capture` mode.
- Added true 16-bit PNG depth export via Windows WIC.
- Added explicit depth packet prefix/schema versioning and example client files.
- Added preview FPS limiting, output resolution enforcement, and frame dropping under load.
- Added Windows WIC MJPG decode so the color path still works when the Femto Bolt advertises MJPG.
- Added versioned-install discovery for Orbbec SDK, clearer dependency error messages, and runtime dependency logging.
- Added no-camera synthetic frame generation for color/depth previews, snapshots, and depth packets.
- Added structured logs for camera lifecycle, preview lifecycle, websocket client connects/disconnects, and depth compression telemetry.

## Blocked / risks
- This shell has `cmake`, but no MSVC/Ninja compiler toolchain is exposed, so I could not run a full compile here.
- A local versioned Orbbec SDK install is visible (`C:\Program Files\OrbbecSDK 2.7.6`), but I could not confirm a GStreamer root from this shell.
- Browser preview remains the intentional JPEG-over-WebSocket fallback for this pass; WebRTC is still not implemented.

## Stable now
- Service starts and serves endpoints without a camera.
- Optional synthetic mode exercises preview, snapshots, and authoritative depth transport without hardware.
- Depth packet schema is explicit and versioned.
- Preview pipeline is bounded, rate-limited, and logs frame drops.
- Startup logs now describe expected runtime DLL and plugin requirements.

## Next phase
- Hardware validation on a NUC with a real Femto Bolt.
- Confirm GStreamer root and plugin discovery on the target machine.
- Verify clean MSVC build output and resolve any compiler warnings seen in the real toolchain.
- Replace JPEG-over-WebSocket preview with WebRTC behind `IPreviewPublisher`.

## Build
```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 `
  -DNUC_REQUIRE_ORBBEC=ON `
  -DNUC_REQUIRE_GSTREAMER=ON `
  -DNUC_FETCH_DEPS=ON `
  -DOrbbecSDK_DIR="C:\Program Files\OrbbecSDK 2.7.6\lib" `
  -DGSTREAMER_ROOT_DIR="C:\gstreamer\1.0\msvc_x86_64"

cmake --build build --config Release
```

## Run
```powershell
.\build\Release\FemtoBoltNuc.exe --config .\config\example.json

.\build\Release\FemtoBoltNuc.exe `
  --config .\config\example.json `
  --test-capture .\capture-out
```
