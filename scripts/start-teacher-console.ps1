param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 7860,
    [switch]$NoOpen,
    [switch]$Bootstrap
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

# ---- Colour helpers ----
function Write-Success  { Write-Host "  [OK] $args" -ForegroundColor Green }
function Write-Warning  { Write-Host "  [WARN] $args" -ForegroundColor Yellow }
function Write-ErrorMsg { Write-Host "  [ERROR] $args" -ForegroundColor Red }
function Write-Action   { Write-Host "  [ACTION] $args" -ForegroundColor Cyan }
function Write-Info     { Write-Host "  [INFO] $args" -ForegroundColor Gray }

Write-Host ""
Write-Host "============================================"
Write-Host "  MathViz Teacher Console"
Write-Host "============================================"
Write-Host ""

# ---- Step 1: Python environment ----
Write-Host "[1/4] Setting up Python environment..."

function Find-Python {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3.10") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        & $candidate.Command @($candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    Write-ErrorMsg "Python 3.10+ is required. Install from https://www.python.org/downloads/windows/"
    exit 1
}

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    $Python = Find-Python
    Write-Host "  Creating virtual environment..."
    & $Python.Command @($Python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to create virtual environment."
        exit 1
    }
}

$env:Path = (Join-Path $RepoRoot ".venv\Scripts") + [System.IO.Path]::PathSeparator + $env:Path

# Ensure pip is available
& $VenvPython -c "import pip" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing pip..."
    & $VenvPython -m pip install pip setuptools wheel -q
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to install pip."
        exit 1
    }
}
Write-Host "  Python ready."

# ---- Helper: pip install with visible output ----
function Invoke-PipInstall {
    param([string[]]$Arguments)
    Write-Info "Running: pip $($Arguments -join ' ')"
    & $VenvPython -m pip @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed with exit code $LASTEXITCODE"
    }
}

# ---- Step 2: Web dependencies ----
Write-Host "[2/4] Checking web dependencies..."

$webDepsOk = $false
& $VenvPython -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -eq 0) {
    $webDepsOk = $true
}

if (-not $webDepsOk) {
    Write-Host "  Installing web packages (this may take a minute)..."
    try {
        Invoke-PipInstall -Arguments @("-e", ".[web]", "-q", "--timeout", "60")
        $webDepsOk = $true
    } catch {
        Write-Warning "Full web install failed. Trying lightweight install (core web packages)..."
    }

    if (-not $webDepsOk) {
        try {
            Invoke-PipInstall -Arguments @("-e", ".", "fastapi", "uvicorn", "httpx", "pyyaml", "-q", "--timeout", "60")
            $webDepsOk = $true
        } catch {
            Write-Warning "Lightweight install failed. Trying core packages..."
        }
    }

    if (-not $webDepsOk) {
        try {
            Invoke-PipInstall -Arguments @("$RepoRoot", "fastapi", "uvicorn", "httpx", "pyyaml", "-q", "--timeout", "120")
            $webDepsOk = $true
        } catch {
            Write-ErrorMsg "All pip install attempts failed."
            Write-ErrorMsg "Please run manually: $VenvPython -m pip install -e '.[web]'"
        }
    }
}

if ($webDepsOk) {
    Write-Success "Web dependencies ready."
} else {
    Write-Warning "Web dependencies may be incomplete. Server may fail to start."
}

# ---- Step 3: Render tools check ----
Write-Host "[3/4] Checking render tools..."

$HealthJson = & $VenvPython -c '
from math_to_manim.app.run_summary import check_render_health
import json, sys
json.dump(check_render_health(), sys.stdout)
' 2>$null

if ($LASTEXITCODE -eq 0 -and $HealthJson) {
    try {
        $HealthObj = $HealthJson | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Warning "Health check JSON parse failed: $_"
        $HealthObj = $null
    }

    if ($HealthObj) {
    $BlockingMissing = $HealthObj.blocking_missing
    $OptionalMissing = $HealthObj.optional_missing

    $FfmpegMissing = $BlockingMissing -contains "ffmpeg"
    $ManimMissing = $BlockingMissing -contains "manim"

    if ($BlockingMissing.Count -gt 0) {
        Write-Host "  [REQUIRED] Missing: $($BlockingMissing -join ', ')" -ForegroundColor Red
    }
    if ($OptionalMissing.Count -gt 0) {
        Write-Host "  [OPTIONAL] Missing: $($OptionalMissing -join ', ')" -ForegroundColor Yellow
    }

    # --- ffmpeg ---
    if ($FfmpegMissing) {
        Write-Action "FFmpeg is required for video rendering."
        $installOk = $false

        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            if (-not $Bootstrap) {
                $ffChoice = Read-Host "  Install FFmpeg via winget? (Y/N, default Y)"
            }
            if ($Bootstrap -or $ffChoice -ne 'n') {
                Write-Host "    Running: winget install Gyan.FFmpeg"
                & winget install --id Gyan.FFmpeg --exact --silent --accept-package-agreements --accept-source-agreements
                Write-Info "    winget exit code: $LASTEXITCODE"
                $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
                if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
                    Write-Success "FFmpeg is now available."
                    $installOk = $true
                }
            }
        }

        if (-not $installOk) {
            Write-Host ""
            Write-Action "Install FFmpeg manually:"
            Write-Info "  1. winget install Gyan.FFmpeg"
            Write-Info "  2. Download from https://ffmpeg.org/download.html"
            Write-Info "  3. Add to PATH, then restart this console."
            Write-Host ""
        }
    }

    # --- manim ---
    if ($ManimMissing) {
        Write-Action "Manim is missing. Installing..."
        try {
            Invoke-PipInstall -Arguments @("-e", ".[render]", "-q", "--timeout", "120")
            Write-Success "Manim installed."
        } catch {
            Write-ErrorMsg "Manim install failed."
            Write-Info "Try: $VenvPython -m pip install manim"
        }
    }

    # --- LaTeX / MiKTeX ---
    $LatexMissing = $OptionalMissing -contains "latex"
    if ($LatexMissing) {
        Write-Info "LaTeX is optional. Low-preview rendering falls back to plain text formulas."
        Write-Info "  To render MathTex/Tex formulas later, install MiKTeX manually: winget install MiKTeX.MiKTeX"
    }

    # --- Final health status ---
    Write-Host ""
    $FinalHealth = & $VenvPython -c '
from math_to_manim.app.run_summary import check_render_health
import json, sys
json.dump(check_render_health(), sys.stdout)
' 2>$null

    if ($FinalHealth) {
        try {
            $FinalObj = $FinalHealth | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Warning "Final health JSON parse failed: $_"
            $FinalObj = $null
        }
    }
    if ($FinalObj) {
        if ($FinalObj.ready) {
            Write-Success "All render tools ready."
        } else {
            Write-Warning "Render tools still missing: $($FinalObj.blocking_missing -join ', ')"
            Write-Info "The web UI will start, but rendering will be unavailable."
        }
        if ($FinalObj.optional_missing.Count -gt 0) {
            Write-Info "Optional tools not installed: $($FinalObj.optional_missing -join ', ')"
            Write-Info "  These are only needed for formula rendering (MathTex/Tex)."
        }
    }
    }
}  # end if ($LASTEXITCODE -eq 0 -and $HealthJson)

if ($LASTEXITCODE -ne 0 -or -not $HealthJson) {
    Write-Warning "Could not check render health (pipeline not fully installed)."
    if ($HealthJson) {
        Write-Host "  $HealthJson"
    }
}

# ---- Step 4: Start server ----
Write-Host "[4/4] Starting teacher console..."

$UrlHost = $HostName
if ($UrlHost -eq "0.0.0.0" -or $UrlHost -eq "::") {
    $UrlHost = "127.0.0.1"
}

# Check if port is already in use and offer to kill the old process
$existingPid = netstat -ano | Select-String ":${Port}\s" | Select-String "LISTENING" | ForEach-Object { $_ -split '\s+' | Select-Object -Last 1 }
if ($existingPid) {
    $existingPid = $existingPid | Select-Object -Unique
    Write-Warning "Port $Port is already in use by PID $($existingPid -join ', ')."
    $killChoice = Read-Host "  Kill the existing process? (Y/N, default Y)"
    if ($killChoice -ne 'n') {
        foreach ($procPid in $existingPid) {
            Write-Info "  Stopping process $procPid..."
            & taskkill /F /PID $procPid 2>$null
        }
        Start-Sleep -Seconds 1
    }
}

$Url = "http://${UrlHost}:${Port}"

if (-not $NoOpen) {
    Start-Process $Url
}

Write-Host ""
Write-Host "  Teacher console: $Url"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

& $VenvPython -m uvicorn "math_to_manim.app.api:create_app" --factory --host $HostName --port $Port
