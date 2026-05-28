Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ==="
}

function Require-Command {
    param([string]$Name, [string]$Hint)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "[missing] $Name" -ForegroundColor Red
        if ($Hint) { Write-Host "  $Hint" }
        return $false
    }
    Write-Host "[ok] $Name -> $($cmd.Source)" -ForegroundColor Green
    return $true
}

function Parse-NodeMajor {
    param([string]$VersionString)
    $v = $VersionString.Trim()
    if ($v.StartsWith("v")) { $v = $v.Substring(1) }
    $parts = $v.Split(".")
    if ($parts.Count -lt 1) { return $null }
    return [int]$parts[0]
}

Write-Section "Python 3.13"
$pythonCmd = $null

if (Require-Command "py" "Install Python 3.13 and ensure the py launcher is available.") {
    try {
        $pyVersion = & py -3.13 -V 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[ok] $pyVersion" -ForegroundColor Green
            $pythonCmd = "py -3.13"
        }
    } catch {
        # keep looking
    }
}

if (-not $pythonCmd) {
    if (Require-Command "python3.13" "Install Python 3.13 and ensure python3.13 is on PATH.") {
        $pyVersion = & python3.13 -V
        Write-Host "[ok] $pyVersion" -ForegroundColor Green
        $pythonCmd = "python3.13"
    }
}

if (-not $pythonCmd) {
    throw "Python 3.13 not found. Install Python 3.13 and try again."
}

Write-Section "Python venv + deps"
$venvPath = Join-Path $repoRoot ".venv"
$resolvedVenv = Resolve-Path $venvPath -ErrorAction SilentlyContinue
if ($resolvedVenv) {
    $venvPath = $resolvedVenv.Path
}
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv at $venvPath"
    & $pythonCmd -m venv $venvPath
}

Write-Host "Installing Python deps (calibration + controller backend)"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $repoRoot "calibration\requirements.txt") -r (Join-Path $repoRoot "controller\backend\requirements.txt")

Write-Section "Node.js 20+"
if (-not (Require-Command "node" "Install Node.js 20+ from https://nodejs.org/")) {
    throw "Node.js not found."
}

$nodeVersion = & node -v
$nodeMajor = Parse-NodeMajor $nodeVersion
if (-not $nodeMajor -or $nodeMajor -lt 20) {
    throw "Node.js 20+ required. Found $nodeVersion"
}
Write-Host "[ok] Node.js $nodeVersion" -ForegroundColor Green

Write-Section "Node deps (controller frontend)"
Push-Location (Join-Path $repoRoot "controller\frontend")
try {
    & npm install
} finally {
    Pop-Location
}

Write-Section "CMake"
if (-not (Require-Command "cmake" "Install CMake 3.24+ and ensure it is on PATH.")) {
    throw "CMake not found."
}
$cmakeVersion = & cmake --version | Select-Object -First 1
Write-Host "[ok] $cmakeVersion" -ForegroundColor Green

Write-Section "Orbbec SDK v2"
$orbbecRoot = $env:OrbbecSDK_DIR
if (-not $orbbecRoot) { $orbbecRoot = $env:ORBBECSDK_ROOT }
if (-not $orbbecRoot) { $orbbecRoot = $env:ORBBEC_SDK_ROOT }
if (-not $orbbecRoot) { $orbbecRoot = "C:\Program Files\OrbbecSDK 2.7.6" }

if (Test-Path $orbbecRoot) {
    Write-Host "[ok] Orbbec SDK root: $orbbecRoot" -ForegroundColor Green
    $env:OrbbecSDK_DIR = Join-Path $orbbecRoot "lib"
    Write-Host "[info] OrbbecSDK_DIR=$($env:OrbbecSDK_DIR)"
} else {
    Write-Host "[missing] Orbbec SDK not found at $orbbecRoot" -ForegroundColor Yellow
    Write-Host "  Install Orbbec SDK v2 and set OrbbecSDK_DIR or ORBBECSDK_ROOT."
}

Write-Section "GStreamer 1.0 MSVC x64"
$gstreamerRoot = $env:GSTREAMER_ROOT_DIR
if (-not $gstreamerRoot) { $gstreamerRoot = $env:GSTREAMER_1_0_ROOT_MSVC_X86_64 }
if (-not $gstreamerRoot) { $gstreamerRoot = $env:GSTREAMER_1_0_ROOT_X86_64 }
if (-not $gstreamerRoot) { $gstreamerRoot = "C:\gstreamer\1.0\msvc_x86_64" }

$gstDll = Join-Path $gstreamerRoot "bin\gstreamer-1.0-0.dll"
if (Test-Path $gstDll) {
    Write-Host "[ok] GStreamer root: $gstreamerRoot" -ForegroundColor Green
    $env:GSTREAMER_ROOT_DIR = $gstreamerRoot
    Write-Host "[info] GSTREAMER_ROOT_DIR=$($env:GSTREAMER_ROOT_DIR)"
} else {
    Write-Host "[missing] GStreamer not found at $gstreamerRoot" -ForegroundColor Yellow
    Write-Host "  Install GStreamer 1.0 MSVC x64 runtime + dev files and set GSTREAMER_ROOT_DIR."
}

Write-Section "Visual Studio build tools"
if (-not (Require-Command "cl" "Run from a Developer PowerShell for VS 2022 or install VS Build Tools.")) {
    Write-Host "[warn] cl.exe not found. You may need a VS 2022 dev shell to build C++." -ForegroundColor Yellow
}

Write-Section "Done"
Write-Host "Setup complete. Next steps:"
Write-Host "- Run calibration: .venv\Scripts\python.exe -m calibration.main --config calibration\calibration_config.json"
Write-Host "- Run controller backend: cd controller\backend; .venv\Scripts\python.exe -m app.main"
Write-Host "- Run controller frontend: cd controller\frontend; npm run dev"
Write-Host "- Configure/build NUC: cmake -S nuc -B nuc/build-vs -G \"Visual Studio 17 2022\" -A x64 ..."
