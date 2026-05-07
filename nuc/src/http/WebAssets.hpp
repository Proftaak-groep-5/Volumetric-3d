#pragma once

namespace femto::web {

inline constexpr const char *kIndexHtml = R"HTML(
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FemtoBoltNuc</title>
  <style>
    :root {
      --bg: #0b1116;
      --panel: #15222d;
      --accent: #60d0ff;
      --accent-2: #ffbf5f;
      --text: #ebf5fb;
      --muted: #9bb3c5;
      --ok: #3bd16f;
      --bad: #ff6b6b;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", "IBM Plex Sans", sans-serif;
      color: var(--text);
      background: radial-gradient(circle at top, #12354a, var(--bg) 45%);
    }
    header, section {
      width: min(1200px, calc(100vw - 32px));
      margin: 16px auto;
      padding: 18px 20px;
      border-radius: 18px;
      background: rgba(21, 34, 45, 0.92);
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    }
    h1, h2 { margin: 0 0 12px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }
    .tile {
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255,255,255,0.03);
    }
    img {
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border-radius: 10px;
      background: #081017;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--muted);
      margin: 0;
    }
    label, button, input, select {
      font: inherit;
    }
    form {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    input, select {
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px;
      padding: 10px 12px;
      background: #0d1821;
      color: var(--text);
    }
    button {
      border: 0;
      border-radius: 10px;
      padding: 10px 12px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #081017;
      font-weight: 700;
      cursor: pointer;
    }
    .status { font-weight: 700; }
  </style>
</head>
<body>
  <header>
    <h1>FemtoBoltNuc Diagnostics</h1>
    <div id="status" class="status">Connecting...</div>
  </header>
  <section class="grid">
    <div class="tile">
      <h2>Color Preview</h2>
      <img id="color" alt="Color preview">
    </div>
    <div class="tile">
      <h2>Depth Preview</h2>
      <img id="depth" alt="Depth preview">
    </div>
  </section>
  <section class="grid">
    <div class="tile">
      <h2>Metadata</h2>
      <pre id="metadata"></pre>
    </div>
    <div class="tile">
      <h2>Depth Stats</h2>
      <pre id="depthStats"></pre>
    </div>
  </section>
  <section>
    <h2>Settings</h2>
    <form id="settingsForm">
      <input type="number" name="minDepth" placeholder="Min depth mm" value="250">
      <input type="number" name="maxDepth" placeholder="Max depth mm" value="4000">
      <select name="mode">
        <option value="false_color">False color</option>
        <option value="grayscale">Grayscale</option>
      </select>
      <button type="submit">Apply Preview Settings</button>
    </form>
  </section>
  <script>
    const statusEl = document.getElementById("status");
    const metadataEl = document.getElementById("metadata");
    const depthStatsEl = document.getElementById("depthStats");
    const colorImg = document.getElementById("color");
    const depthImg = document.getElementById("depth");
    let previewFrame = 0;

    function startPreviewPolling(img, path) {
      function refreshPreview() {
        img.src = `${path}?t=${Date.now()}&frame=${previewFrame++}`;
      }
      refreshPreview();
      return setInterval(refreshPreview, 66);
    }

    function startPreviewWebSocket(img, wsPath, fallbackPath) {
      let lastObjectUrl = null;
      let fallbackTimer = null;
      const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${wsPath}`);
      ws.binaryType = "arraybuffer";

      function startFallbackOnce() {
        if (fallbackTimer !== null) {
          return;
        }
        fallbackTimer = startPreviewPolling(img, fallbackPath);
      }

      ws.onmessage = (event) => {
        if (!(event.data instanceof ArrayBuffer)) {
          return;
        }
        const blob = new Blob([event.data], { type: "image/jpeg" });
        const url = URL.createObjectURL(blob);
        if (lastObjectUrl) {
          URL.revokeObjectURL(lastObjectUrl);
        }
        lastObjectUrl = url;
        img.src = url;
      };

      ws.onerror = () => {
        startFallbackOnce();
      };
      ws.onclose = () => {
        startFallbackOnce();
      };
    }

    const depthDataWs = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/depth`);
    depthDataWs.binaryType = "arraybuffer";
    depthDataWs.onmessage = (event) => {
      const view = new DataView(event.data);
      const headerLength = view.getUint32(8, true);
      const payloadLength = view.getUint32(12, true);
      const header = JSON.parse(new TextDecoder().decode(new Uint8Array(event.data, 16, headerLength)));
      depthStatsEl.textContent = JSON.stringify({ header, payloadLength }, null, 2);
    };

    async function refresh() {
      const [health, metadata] = await Promise.all([
        fetch("/health").then((r) => r.json()),
        fetch("/metadata").then((r) => r.json())
      ]);
      statusEl.textContent = `${health.status} | camera connected: ${health.camera_connected}`;
      statusEl.style.color = health.camera_connected ? "var(--ok)" : "var(--bad)";
      metadataEl.textContent = JSON.stringify(metadata, null, 2);
    }

    document.getElementById("settingsForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      await fetch("/settings", {
        method: "POST",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({
          depth_preview: {
            min_depth_mm: Number(form.get("minDepth")),
            max_depth_mm: Number(form.get("maxDepth")),
            mode: form.get("mode")
          }
        })
      });
      refresh();
    });

    setInterval(refresh, 2000);
    refresh();
    startPreviewWebSocket(colorImg, "/ws/preview/color", "/snapshot/color.jpg");
    startPreviewWebSocket(depthImg, "/ws/preview/depth", "/snapshot/depth-preview.jpg");
  </script>
</body>
</html>
)HTML";

}  // namespace femto::web
