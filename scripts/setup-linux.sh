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

install_with_pm() {
  local package="$1"
  if command -v apt-get >/dev/null 2>&1; then
    echo "[install] apt-get $package"
    sudo apt-get update -y
    sudo apt-get install -y $package
    return 0
  fi
  if command -v dnf >/dev/null 2>&1; then
    echo "[install] dnf $package"
    sudo dnf install -y $package
    return 0
  fi
  if command -v yum >/dev/null 2>&1; then
    echo "[install] yum $package"
    sudo yum install -y $package
    return 0
  fi
  if command -v pacman >/dev/null 2>&1; then
    echo "[install] pacman $package"
    sudo pacman -S --noconfirm $package
    return 0
  fi
  if command -v apk >/dev/null 2>&1; then
    echo "[install] apk $package"
    sudo apk add $package
    return 0
  fi
  if command -v zypper >/dev/null 2>&1; then
    echo "[install] zypper $package"
    sudo zypper install -y $package
    return 0
  fi
  echo "[warn] No supported package manager found (apt/dnf/yum/pacman/apk/zypper)."
  return 1
}

parse_node_major() {
  local v="$1"
  v="${v#v}"
  echo "${v%%.*}"
}

download_file() {
  local url="$1"
  local output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO "$output" "$url"
    return 0
  fi
  echo "[missing] curl or wget"
  echo "  Install curl or wget to download Python source."
  return 1
}

install_python_313_from_source() {
  local python_version="${PYTHON_VERSION:-3.13.0}"
  local install_dir="$repo_root/.tooling/python-${python_version}"
  local python_bin="$install_dir/bin/python3.13"
  local build_dir
  build_dir="$(mktemp -d)"

  if [[ -x "$python_bin" ]]; then
    echo "[ok] Python 3.13 already installed at $python_bin"
    return 0
  fi

  for tool in tar make cc; do
    require_cmd "$tool" "Install build tooling for compiling Python from source." || return 1
  done

  echo "[install] Python ${python_version} from source"
  trap 'rm -rf "$build_dir"' RETURN

  download_file "https://www.python.org/ftp/python/${python_version}/Python-${python_version}.tgz" "$build_dir/Python-${python_version}.tgz"
  tar -xzf "$build_dir/Python-${python_version}.tgz" -C "$build_dir"

  pushd "$build_dir/Python-${python_version}" >/dev/null
  ./configure --prefix="$install_dir" --enable-optimizations --with-ensurepip=install
  make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
  make altinstall
  popd >/dev/null

  if [[ ! -x "$python_bin" ]]; then
    echo "Python 3.13 source build finished, but $python_bin was not created."
    return 1
  fi
}

section "Python 3.13 (source build)"
python_cmd=""
if command -v python3.13 >/dev/null 2>&1; then
  python_cmd="$(command -v python3.13)"
elif install_python_313_from_source; then
  python_cmd="$repo_root/.tooling/python-${PYTHON_VERSION:-3.13.0}/bin/python3.13"
fi

if [[ -z "$python_cmd" || ! -x "$python_cmd" ]]; then
  echo "Python 3.13 not found and source build failed. Install a compiler toolchain and try again."
  exit 1
fi

"$python_cmd" -V

section "Python venv + deps"
venv_path="$repo_root/.venv"
if [[ ! -x "$venv_path/bin/python" ]]; then
  echo "Creating venv at $venv_path"
  "$python_cmd" -m venv "$venv_path"
fi

"$venv_path/bin/python" -m pip install --upgrade pip
"$venv_path/bin/python" -m pip install -r "$repo_root/calibration/requirements.txt" -r "$repo_root/controller/backend/requirements.txt"

section "Node.js 20+"
if ! require_cmd node "Install Node.js 20+ from https://nodejs.org/"; then
  install_with_pm "nodejs" || true
  install_with_pm "npm" || true
fi
require_cmd node "Install Node.js 20+ from https://nodejs.org/" || exit 1
node_version="$(node -v)"
node_major="$(parse_node_major "$node_version")"
if [[ -z "$node_major" || "$node_major" -lt 20 ]]; then
  echo "[warn] Node.js 20+ required. Found $node_version"
  install_with_pm "nodejs" || true
  node_version="$(node -v)"
  node_major="$(parse_node_major "$node_version")"
  if [[ -z "$node_major" || "$node_major" -lt 20 ]]; then
    echo "Node.js 20+ required. Found $node_version"
    exit 1
  fi
fi

section "Node deps (controller frontend)"
( cd "$repo_root/controller/frontend" && npm install )

section "CMake"
if ! require_cmd cmake "Install CMake 3.24+ and ensure it is on PATH."; then
  install_with_pm "cmake" || true
fi
require_cmd cmake "Install CMake 3.24+ and ensure it is on PATH." || exit 1
cmake --version | head -n 1

section "GStreamer"
if ! require_cmd gst-inspect-1.0 "Install GStreamer 1.0"; then
  install_with_pm "gstreamer1.0-tools" || true
  install_with_pm "gstreamer1.0-plugins-base" || true
  install_with_pm "gstreamer1.0-plugins-good" || true
  require_cmd gst-inspect-1.0 "Install GStreamer 1.0" || true
fi

section "Orbbec SDK"
echo "[info] Orbbec SDK is Windows-only for the NUC service."

section "Done"
echo "Setup complete. Next steps:"
echo "- Run calibration: .venv/bin/python -m calibration.main --config calibration/calibration_config.json"
echo "- Run controller backend: cd controller/backend; .venv/bin/python -m app.main"
echo "- Run controller frontend: cd controller/frontend; npm run dev"
