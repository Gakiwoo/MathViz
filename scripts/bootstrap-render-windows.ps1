param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "=== MathViz Render Bootstrap (Windows) ==="
Write-Host ""

# ---- Step 1: Python venv ----
Write-Host "[1/5] Setting up Python environment..."

function Find-Python {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3.10") },
        @{ Command = "python"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        & $candidate.Command @($candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }
    throw "Python 3.10+ is required. Install from https://www.python.org/downloads/windows/"
}

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $Python = Find-Python
    Write-Host "  Creating virtual environment..."
    & $Python.Command @($Python.Args) -m venv .venv
}
else {
    Write-Host "  Virtual environment already exists."
}

$env:Path = (Join-Path $RepoRoot ".venv\Scripts") + [System.IO.Path]::PathSeparator + $env:Path
& $VenvPython -m pip install -U pip -q
Write-Host "  Python ready."

# ---- Step 2: System graphics libraries ----
Write-Host "[2/5] Checking system graphics libraries..."
Write-Host "  Windows Manim uses pre-built wheels; no system graphics libraries needed."
Write-Host "  If Manim import fails, install the Visual C++ Redistributable:"
Write-Host "    https://aka.ms/vs/17/release/vc_redist.x64.exe"

# ---- Step 3: Python render dependencies ----
Write-Host "[3/5] Installing Python render dependencies..."
& $VenvPython -m pip install -e ".[render]" -q
Write-Host "  Render packages installed."

# ---- Step 3.5: Dev dependencies ----
Write-Host "[3.5/5] Installing dev dependencies..."
& $VenvPython -m pip install -e ".[dev]" -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Dev tools (pytest, ruff) installed."
} else {
    Write-Host "  [WARN] Dev dependencies install had issues (non-critical)."
    Write-Host "  You can install manually: $VenvPython -m pip install -e '.[dev]'"
}

# ---- Step 4: FFmpeg ----
Write-Host "[4/5] Checking FFmpeg..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "  [WARN] FFmpeg is missing."
    Write-Host "  Install with: winget install Gyan.FFmpeg"
    Write-Host "  Or download from: https://ffmpeg.org/download.html"
    Write-Host "  After installing, restart your terminal."
}
else {
    $ffVer = & ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "  FFmpeg found: $ffVer"
}

# ---- Step 5: LaTeX ----
Write-Host "[5/5] Checking LaTeX..."
if (-not (Get-Command latex -ErrorAction SilentlyContinue)) {
    Write-Host "  [WARN] LaTeX is missing. MathTex rendering will not work."
    Write-Host ""
    Write-Host "  Recommended: Install MiKTeX (auto-installs missing packages on demand):"
    Write-Host "    winget install MiKTeX.MiKTeX"
    Write-Host "  Or download from: https://miktex.org/download"
    Write-Host ""
    Write-Host "  Alternative: Install TeX Live:"
    Write-Host "    https://tug.org/texlive/windows.html"
}
else {
    Write-Host "  LaTeX found. Testing compilation..."
    $TmpDir = Join-Path $env:TEMP "m2m2_tex_test"
    New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
    @'
\documentclass{standalone}
\usepackage[english]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\begin{document}
$x^2 + y^2 = 1$
\end{document}
'@ | Out-File -Encoding utf8 (Join-Path $TmpDir "test.tex")

    $prevDir = Get-Location
    Set-Location $TmpDir
    $latexResult = & latex -interaction=nonstopmode "test.tex" 2>&1
    Set-Location $prevDir

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  LaTeX compilation OK."
    }
    else {
        Write-Host "  [WARN] LaTeX compilation test failed."
        Write-Host "  MiKTeX should auto-install missing packages on first use."
        Write-Host "  If using TeX Live, you may need to install additional packages."
    }
    Remove-Item -Recurse -Force $TmpDir -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Render bootstrap complete ==="

& $VenvPython -c "from math_to_manim.app.run_summary import check_render_health; import json; print(json.dumps(check_render_health(), indent=2))"
