from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_macos_command_wrapper_delegates_to_shell_script() -> None:
    wrapper = ROOT / "scripts" / "start-teacher-console.command"

    text = wrapper.read_text(encoding="utf-8")

    assert "start-teacher-console.sh" in text
    assert 'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"' in text


def test_windows_powershell_script_starts_local_console() -> None:
    script = ROOT / "scripts" / "start-teacher-console.ps1"

    text = script.read_text(encoding="utf-8")

    assert "param(" in text
    assert "[int]$Port = 7860" in text
    assert "[switch]$NoOpen" in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "math_to_manim.app.api:create_app" in text
    assert "--factory" in text
    assert "Start-Process" in text
    assert "pip install -U pip" not in text
    assert "Install MiKTeX via winget?" not in text
    assert "winget install --id MiKTeX.MiKTeX" not in text


def test_windows_batch_wrapper_uses_powershell_bypass() -> None:
    script = ROOT / "scripts" / "start-teacher-console.bat"

    text = script.read_text(encoding="utf-8")

    assert "start-teacher-console.ps1" in text
    assert "-ExecutionPolicy Bypass" in text


def test_macos_render_bootstrap_reports_system_dependencies() -> None:
    script = ROOT / "scripts" / "bootstrap-render-macos.sh"

    text = script.read_text(encoding="utf-8")

    assert "pkg-config cairo pango" in text
    assert "brew install" in text
    assert "basictex" in text
    assert 'python -m pip install -e ".[render]"' in text


def test_windows_render_bootstrap_reports_system_dependencies() -> None:
    script = ROOT / "scripts" / "bootstrap-render-windows.ps1"

    text = script.read_text(encoding="utf-8")

    assert ".[render]" in text
    assert "Gyan.FFmpeg" in text
    assert "MiKTeX" in text


@pytest.mark.skipif(sys.platform == "win32", reason="requires bash")
def test_unix_start_script_help_mentions_platform_entrypoints() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts" / "start-teacher-console.sh"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "start-teacher-console.command" in result.stdout
    assert "start-teacher-console.ps1" in result.stdout


def test_unix_start_script_does_not_upgrade_pip_on_every_start() -> None:
    script = ROOT / "scripts" / "start-teacher-console.sh"

    text = script.read_text(encoding="utf-8")

    assert "pip install -U pip" not in text
