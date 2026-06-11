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

function Install-Package {
    param([
        string]$WingetId,
        [string]$ChocoId,
        [string]$ScoopId
    )

    $attempted = $false

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        if ($WingetId) {
            $attempted = $true
            Write-Host "[install] winget $WingetId" -ForegroundColor Yellow
            try {
                & winget install --id $WingetId -e --source winget --silent --accept-package-agreements --accept-source-agreements
                if ($LASTEXITCODE -eq 0) { return $true }
                Write-Host "[warn] winget failed with exit code $LASTEXITCODE; trying another package manager if available." -ForegroundColor Yellow
            } catch {
                Write-Host "[warn] winget failed: $($_.Exception.Message)" -ForegroundColor Yellow
                Write-Host "       Trying another package manager if available." -ForegroundColor Yellow
            }
        }
    }

    if (Get-Command choco -ErrorAction SilentlyContinue) {
        if ($ChocoId) {
            $attempted = $true
            Write-Host "[install] choco $ChocoId" -ForegroundColor Yellow
            try {
                & choco install $ChocoId -y
                if ($LASTEXITCODE -eq 0) { return $true }
                Write-Host "[warn] choco failed with exit code $LASTEXITCODE; trying another package manager if available." -ForegroundColor Yellow
            } catch {
                Write-Host "[warn] choco failed: $($_.Exception.Message)" -ForegroundColor Yellow
                Write-Host "       Trying another package manager if available." -ForegroundColor Yellow
            }
        }
    }

    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        if ($ScoopId) {
            $attempted = $true
            Write-Host "[install] scoop $ScoopId" -ForegroundColor Yellow
            try {
                & scoop install $ScoopId
                if ($LASTEXITCODE -eq 0) { return $true }
                Write-Host "[warn] scoop failed with exit code $LASTEXITCODE." -ForegroundColor Yellow
            } catch {
                Write-Host "[warn] scoop failed: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }

    if (-not $attempted) {
        Write-Host "[warn] No supported package manager found (winget/choco/scoop)." -ForegroundColor Yellow
    }
    return $false
}

function Update-SessionPath {
    $pathValues = @(
        $env:Path,
        [Environment]::GetEnvironmentVariable("Path", "Machine"),
        [Environment]::GetEnvironmentVariable("Path", "User")
    )

    $seen = @{}
    $parts = foreach ($pathValue in $pathValues) {
        if (-not $pathValue) { continue }
        foreach ($part in $pathValue.Split(";")) {
            $trimmed = $part.Trim()
            if (-not $trimmed) { continue }
            $key = $trimmed.ToLowerInvariant()
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $trimmed
            }
        }
    }

    $env:Path = ($parts -join ";")
}

function Test-Python313 {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    $cmd = Get-Command $FilePath -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }

    try {
        $version = & $FilePath @Arguments -V 2>$null
        if ($LASTEXITCODE -eq 0 -and $version -match "^Python 3\.13\.") {
            Write-Host "[ok] $version" -ForegroundColor Green
            return [pscustomobject]@{
                FilePath = $FilePath
                Arguments = $Arguments
            }
        }
    } catch {
        # keep looking
    }

    return $null
}

function Find-Python313 {
    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        Write-Host "[ok] py -> $($pyLauncher.Source)" -ForegroundColor Green
        $python = Test-Python313 -FilePath "py" -Arguments @("-3.13")
        if ($python) { return $python }
    } else {
        Write-Host "[missing] py" -ForegroundColor Red
        Write-Host "  Install Python 3.13 and ensure the py launcher is available."
    }

    $python313 = Get-Command "python3.13" -ErrorAction SilentlyContinue
    if ($python313) {
        Write-Host "[ok] python3.13 -> $($python313.Source)" -ForegroundColor Green
        $python = Test-Python313 -FilePath "python3.13"
        if ($python) { return $python }
    } else {
        Write-Host "[missing] python3.13" -ForegroundColor Red
        Write-Host "  Install Python 3.13 and ensure python3.13 is on PATH."
    }

    $candidates = @()
    if ($env:LocalAppData) {
        $candidates += (Join-Path $env:LocalAppData "Programs\Python\Python313\python.exe")
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "Python313\python.exe")
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $candidates += (Join-Path $programFilesX86 "Python313\python.exe")
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $python = Test-Python313 -FilePath $candidate
            if ($python) { return $python }
        }
    }

    return $null
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
$pythonCmd = Find-Python313

if (-not $pythonCmd) {
    [void](Install-Package -WingetId "Python.Python.3.13" -ChocoId "python" -ScoopId "python")
    Update-SessionPath
    $pythonCmd = Find-Python313
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
    $venvArgs = @($pythonCmd.Arguments) + @("-m", "venv", $venvPath)
    & $pythonCmd.FilePath @venvArgs
}

Write-Host "Installing Python deps (calibration + controller backend)"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $repoRoot "calibration\requirements.txt") -r (Join-Path $repoRoot "controller\backend\requirements.txt")

Write-Section "Node.js 20+"
if (-not (Require-Command "node" "Install Node.js 20+ from https://nodejs.org/")) {
    Install-Package -WingetId "OpenJS.NodeJS.LTS" -ChocoId "nodejs-lts" -ScoopId "nodejs-lts"
}

if (-not (Require-Command "node" "Install Node.js 20+ from https://nodejs.org/")) {
    throw "Node.js not found."
}

$nodeVersion = & node -v
$nodeMajor = Parse-NodeMajor $nodeVersion
if (-not $nodeMajor -or $nodeMajor -lt 20) {
    Write-Host "[warn] Node.js 20+ required. Found $nodeVersion" -ForegroundColor Yellow
    Install-Package -WingetId "OpenJS.NodeJS.LTS" -ChocoId "nodejs-lts" -ScoopId "nodejs-lts"
    $nodeVersion = & node -v
    $nodeMajor = Parse-NodeMajor $nodeVersion
    if (-not $nodeMajor -or $nodeMajor -lt 20) {
        throw "Node.js 20+ required. Found $nodeVersion"
    }
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
    Install-Package -WingetId "Kitware.CMake" -ChocoId "cmake" -ScoopId "cmake"
}
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
    Install-Package -WingetId "GStreamer.GStreamer" -ChocoId "gstreamer" -ScoopId "gstreamer"
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
