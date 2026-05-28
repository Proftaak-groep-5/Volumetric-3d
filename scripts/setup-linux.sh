#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

section() {
  echo ""
  echo "=== $1 ==="
}

require_cmd() {
  local name="$1"
  local hint="$2"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "[missing] $name"
    [[ -n "$hint" ]] && echo "  $hint"
    return 1
  fi
  echo "[ok] $name -> $(command -v "$name")"
  return 0
}

parse_node_major() {
  local v="$1"
  v="${v#v}"
  echo "${v%%.*}"
}

section "Python 3.13"
python_cmd=""
if require_cmd python3.13 "Install Python 3.13 and ensure python3.13 is on PATH."; then
  python_cmd="python3.13"
  "${python_cmd}" -V
fi

if [[ -z "$python_cmd" ]]; then
  echo "Python 3.13 not found. Install Python 3.13 and try again."
  exit 1
fi

section "Python venv + deps"
venv_path="$repo_root/.venv"
if [[ ! -x "$venv_path/bin/python" ]]; then
  echo "Creating venv at $venv_path"
  "$python_cmd" -m venv "$venv_path"
fi

"$venv_path/bin/python" -m pip install --upgrade pip
"$venv_path/bin/python" -m pip install -r "$repo_root/calibration/requirements.txt" -r "$repo_root/controller/backend/requirements.txt"

section "Node.js 20+"
require_cmd node "Install Node.js 20+ from https://nodejs.org/" || exit 1
node_version="$(node -v)"
node_major="$(parse_node_major "$node_version")"
if [[ -z "$node_major" || "$node_major" -lt 20 ]]; then
  echo "Node.js 20+ required. Found $node_version"
  exit 1
fi

section "Node deps (controller frontend)"
( cd "$repo_root/controller/frontend" && npm install )

section "CMake"
require_cmd cmake "Install CMake 3.24+ and ensure it is on PATH." || exit 1
cmake --version | head -n 1

section "GStreamer"
if ! require_cmd gst-inspect-1.0 "Install GStreamer 1.0 (sudo apt install gstreamer1.0-tools)"; then
  echo "[warn] GStreamer tools not found."
fi

section "Orbbec SDK"
echo "[info] Orbbec SDK is Windows-only for the NUC service."

section "Done"
echo "Setup complete. Next steps:"
echo "- Run calibration: .venv/bin/python -m calibration.main --config calibration/calibration_config.json"
echo "- Run controller backend: cd controller/backend; .venv/bin/python -m app.main"
echo "- Run controller frontend: cd controller/frontend; npm run dev"
