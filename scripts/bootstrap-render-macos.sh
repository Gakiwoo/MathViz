#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

echo "=== M2M2 Render Bootstrap (macOS) ==="
echo ""

# ---- Python venv ----
if [[ ! -x ".venv/bin/python" ]]; then
  PYTHON_BIN=""
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]]; then
    echo "[ERROR] Python 3.10+ is required. Install from https://www.python.org/downloads/" >&2
    exit 1
  fi
  echo "[1/5] Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
else
  echo "[1/5] Virtual environment already exists."
fi

export PATH="$REPO_ROOT/.venv/bin:$PATH"
python -m pip install -U pip -q

# ---- System graphics libraries ----
echo "[2/5] Checking system graphics libraries..."
if ! command -v pkg-config >/dev/null 2>&1 || ! pkg-config --exists cairo pango 2>/dev/null; then
  if command -v brew >/dev/null 2>&1; then
    echo "  Installing cairo + pango via Homebrew..."
    brew install pkg-config cairo pango
  else
    echo "[ERROR] Manim needs pkg-config, cairo, and pango." >&2
    echo "  Install Homebrew from https://brew.sh/, then re-run this script." >&2
    exit 1
  fi
else
  echo "  cairo + pango already installed."
fi

# ---- Python render dependencies ----
echo "[3/5] Installing Python render dependencies..."
python -m pip install -e ".[render]" -q

# ---- Patch manim numpy 2.x compatibility ----
echo "  Checking manim numpy compatibility..."
MANIM_MOBJECT=".venv/lib/python3.11/site-packages/manim/mobject/mobject.py"
if [[ -f "$MANIM_MOBJECT" ]]; then
  if ! grep -q "np_points.ndim < 2" "$MANIM_MOBJECT" 2>/dev/null; then
    echo "  Patching manim for numpy 2.x compatibility..."
    python3 -c "
import re
path = '$MANIM_MOBJECT'
with open(path, 'r') as f:
    content = f.read()
old = '''        np_points: Point3D_Array = (
            self.get_points_defining_boundary()
            if points is None
            else np.asarray(points)
        )
        values = np_points[:, dim]'''
new = '''        np_points: Point3D_Array = (
            self.get_points_defining_boundary()
            if points is None
            else np.asarray(points)
        )
        if np_points.ndim < 2:
            return 0.0
        values = np_points[:, dim]'''
if old in content:
    content = content.replace(old, new)
    with open(path, 'w') as f:
        f.write(content)
    print('    manim patched.')
else:
    print('    Patch pattern not found — may already be patched or version differs.')
"
  else
    echo "  manim already patched."
  fi
fi

# ---- FFmpeg ----
echo "[4/5] Checking FFmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "  Installing FFmpeg via Homebrew..."
    brew install ffmpeg
  else
    echo "  [WARN] FFmpeg not found. Install it manually or via: brew install ffmpeg" >&2
  fi
else
  echo "  FFmpeg found: $(ffmpeg -version 2>&1 | head -1)"
fi

# ---- LaTeX ----
echo "[5/5] Checking LaTeX..."
LATEX_OK=0
if command -v latex >/dev/null 2>&1; then
  # Ensure PATH includes TeX Live binaries
  if [[ -d /Library/TeX/texbin ]]; then
    export PATH="/Library/TeX/texbin:$PATH"
  fi

  # Install essential LaTeX packages if tlmgr is available
  if command -v tlmgr >/dev/null 2>&1; then
    echo "  Checking for required LaTeX packages..."
    MISSING_PKGS=""
    for pkg in standalone preview xcolor; do
      if ! tlmgr info "$pkg" 2>/dev/null | grep -q "installed:.*Yes"; then
        MISSING_PKGS="$MISSING_PKGS $pkg"
      fi
    done

    if [[ -n "$MISSING_PKGS" ]]; then
      echo "  Installing missing LaTeX packages:$MISSING_PKGS"
      if tlmgr --usermode install $MISSING_PKGS 2>/dev/null; then
        echo "  Packages installed in user mode."
      else
        echo "  Trying system install (may ask for password)..."
        sudo tlmgr install $MISSING_PKGS || echo "  [WARN] Could not install LaTeX packages. Run manually: sudo tlmgr install$MISSING_PKGS"
      fi
    fi

    # dvisvgm is a binary package, not relocatable — needs system install
    if ! command -v dvisvgm >/dev/null 2>&1 && ! [[ -x "$REPO_ROOT/.venv/bin/dvisvgm" ]]; then
      echo "  Installing dvisvgm (DVI-to-SVG converter)..."
      if sudo tlmgr install dvisvgm 2>/dev/null; then
        echo "  dvisvgm installed system-wide."
      else
        # Fallback: download pre-built binary directly into venv
        echo "  Downloading pre-built dvisvgm binary..."
        DVISVGM_URL="https://mirror.ctan.org/systems/texlive/tlnet/archive/dvisvgm.universal-darwin.tar.xz"
        TMP_DVI=$(mktemp -d)
        if curl -sL "$DVISVGM_URL" -o "$TMP_DVI/dvisvgm.tar.xz" 2>/dev/null; then
          tar xf "$TMP_DVI/dvisvgm.tar.xz" -C "$TMP_DVI" bin/universal-darwin/dvisvgm 2>/dev/null && \
          cp "$TMP_DVI/bin/universal-darwin/dvisvgm" "$REPO_ROOT/.venv/bin/dvisvgm" && \
          chmod +x "$REPO_ROOT/.venv/bin/dvisvgm" && \
          echo "  dvisvgm installed to .venv/bin/"
        else
          echo "  [WARN] Could not download dvisvgm. Run: sudo tlmgr install dvisvgm"
        fi
        rm -rf "$TMP_DVI"
      fi
    fi
  fi

  # Verify LaTeX actually works for Manim
  echo "  Testing LaTeX compilation..."
  TMPDIR=$(mktemp -d)
  cat > "$TMPDIR/test.tex" << 'TEXEOF'
\documentclass{standalone}
\usepackage[english]{babel}
\usepackage{amsmath}
\usepackage{amssymb}
\begin{document}
$x^2 + y^2 = 1$
\end{document}
TEXEOF
  if latex -interaction=nonstopmode -output-directory "$TMPDIR" "$TMPDIR/test.tex" >/dev/null 2>&1; then
    echo "  LaTeX compilation OK."
    LATEX_OK=1
  else
    echo "  [WARN] LaTeX compilation test failed. Check that required packages are installed."
    echo "  Run: sudo tlmgr install standalone preview"
  fi
  rm -rf "$TMPDIR"
else
  echo "  LaTeX not found. For MathTex rendering, install BasicTeX:"
  echo "    brew install --cask basictex"
  echo "  Then re-run this script to install required packages."
fi

echo ""
echo "=== Render bootstrap complete ==="

python - <<'PY'
from math_to_manim.app.run_summary import check_render_health
import json
print(json.dumps(check_render_health(), indent=2))
PY
