#!/usr/bin/env bash
set -euo pipefail

HOST="127.0.0.1"
PORT="7860"
NO_OPEN="0"
BOOTSTRAP_RENDER="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:?--host requires a value}"
      shift 2
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    --no-open)
      NO_OPEN="1"
      shift
      ;;
    --bootstrap)
      BOOTSTRAP_RENDER="1"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/start-teacher-console.sh [options]

Options:
  --host HOST     Bind address (default: 127.0.0.1)
  --port PORT     Port number (default: 7860)
  --no-open       Don't open browser automatically
  --bootstrap     Also run render bootstrap (install system deps)

Platform entrypoints:
  macOS Terminal: ./scripts/start-teacher-console.sh
  macOS Finder:   double-click scripts/start-teacher-console.command
  Windows:        scripts\start-teacher-console.bat
  PowerShell:     .\scripts\start-teacher-console.ps1
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║       MathViz Teacher Console                ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ---- Step 1: Python venv ----
echo "[1/4] Setting up Python environment..."
if [[ ! -x ".venv/bin/python" ]]; then
  PYTHON_BIN=""
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]]; then
    echo "  [ERROR] Python 3.10+ is required." >&2
    echo "  Install from https://www.python.org/downloads/ and try again." >&2
    exit 1
  fi
  echo "  Creating virtual environment with $PYTHON_BIN..."
  "$PYTHON_BIN" -m venv .venv
fi

PYTHON=".venv/bin/python"
export PATH="$REPO_ROOT/.venv/bin:$PATH"
if ! "$PYTHON" -c "import pip" >/dev/null 2>&1; then
  "$PYTHON" -m ensurepip --upgrade >/dev/null
fi

# Repair corrupted metadata (e.g. numpy version string) that blocks pip
if "$PYTHON" -c "import pip" 2>/dev/null; then
  for pkg in .venv/lib/python*/site-packages/*.dist-info; do
    if [[ -f "$pkg/METADATA" ]] && ! "$PYTHON" -c "import email; email.message_from_bytes(open('$pkg/METADATA','rb').read())" >/dev/null 2>&1; then
      PKG_NAME=$(basename "$pkg" | sed 's/-.*//')
      echo "  [FIX] Corrupted package detected: $PKG_NAME — reinstalling..."
      "$PYTHON" -m pip install --force-reinstall "$PKG_NAME" -q 2>/dev/null || true
    fi
  done
fi

echo "  Python ready."

# ---- Step 2: Web dependencies ----
echo "[2/4] Checking web dependencies..."
if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
PY
then
  echo "  Installing web packages (this may take a minute)..."
  "$PYTHON" -m pip install -e ".[web]" -q --timeout 60 2>/dev/null || \
    { echo "  [INFO] Lightweight install (skipping gradio)..."
      "$PYTHON" -m pip install -e . fastapi uvicorn httpx pyyaml -q --timeout 60 2>/dev/null || \
        { echo "  [WARN] Pip install had issues, retrying core packages only..."
          "$PYTHON" -m pip install fastapi uvicorn httpx pyyaml -q --timeout 120 2>/dev/null; }; }
fi
echo "  Web dependencies ready."

# ---- Step 3: Render tools check + auto-install ----
echo "[3/4] Checking render tools..."
RENDER_HEALTH=$("$PYTHON" -c "
from math_to_manim.app.run_summary import check_render_health
import json
h = check_render_health()
print(json.dumps({
    'ready': h['ready'],
    'blocking': h['blocking_missing'],
    'optional': h['optional_missing']
}))
")

BLOCKING=$(echo "$RENDER_HEALTH" | "$PYTHON" -c "import json,sys; print(' '.join(json.load(sys.stdin)['blocking']))")
OPTIONAL=$(echo "$RENDER_HEALTH" | "$PYTHON" -c "import json,sys; print(' '.join(json.load(sys.stdin)['optional']))")

# Auto-install ffmpeg if missing
if echo "$BLOCKING" | grep -qw "ffmpeg"; then
  echo "  [ACTION] FFmpeg is required. Installing via Homebrew..."
  if command -v brew >/dev/null 2>&1; then
    brew install ffmpeg 2>/dev/null && echo "  [OK] FFmpeg installed." || echo "  [WARN] brew install failed."
  else
    echo "  [INFO] Install FFmpeg manually: brew install ffmpeg"
  fi
fi

# Auto-install manim if missing
if echo "$BLOCKING" | grep -qw "manim"; then
  echo "  [ACTION] Installing Manim..."
  "$PYTHON" -m pip install -e ".[render]" -q --timeout 120 2>/dev/null || true
fi

# Show final status
FINAL_HEALTH=$("$PYTHON" -c "
from math_to_manim.app.run_summary import check_render_health
import json
print(json.dumps(check_render_health()))
")
READY=$(echo "$FINAL_HEALTH" | "$PYTHON" -c "import json,sys; print(json.load(sys.stdin)['ready'])")
BLOCKING_FINAL=$(echo "$FINAL_HEALTH" | "$PYTHON" -c "import json,sys; print(', '.join(json.load(sys.stdin)['blocking_missing']) or 'none')")
OPTIONAL_FINAL=$(echo "$FINAL_HEALTH" | "$PYTHON" -c "import json,sys; print(', '.join(json.load(sys.stdin)['optional_missing']) or 'none')")

echo "  Render ready: $READY"
echo "  Required: $BLOCKING_FINAL"
echo "  Optional: $OPTIONAL_FINAL"

if [[ "$OPTIONAL_FINAL" != "none" ]]; then
  echo ""
  echo "  [INFO] Optional tools (latex/dvisvgm) only needed for formula rendering."
fi

# ---- Step 4: Start server ----
echo "[4/4] Starting teacher console..."

URL_HOST="$HOST"
if [[ "$URL_HOST" == "0.0.0.0" || "$URL_HOST" == "::" ]]; then
  URL_HOST="127.0.0.1"
fi
URL="http://${URL_HOST}:${PORT}"

if [[ "$NO_OPEN" != "1" ]]; then
  (
    sleep 1.5
    if command -v open >/dev/null 2>&1; then
      open "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$URL" >/dev/null 2>&1 || true
    fi
  ) &
fi

echo ""
echo "  Teacher console: $URL"
echo "  Press Ctrl+C to stop."
echo ""

exec "$PYTHON" -m uvicorn "math_to_manim.app.api:create_app" --factory --host "$HOST" --port "$PORT"
