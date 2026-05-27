"""Shared subprocess result helpers."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ToolResult:
    """Common result for optional local binary wrappers."""

    ok: bool
    skipped: bool
    command: tuple[str, ...]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None
    output_path: Path | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


def resolve_binary(binary: str) -> str | None:
    """Return an executable path or ``None`` without raising.

    Checks PATH first (via shutil.which), then falls back to venv-local
    ``Scripts/`` and ``bin/`` directories adjacent to the running Python.

    On Windows, a bare file without a recognised executable extension
    (.exe, .bat, .cmd, .com) is not a valid executable and is skipped,
    so that the real .exe in a sibling directory is found instead.
    """

    candidate = Path(binary)
    if candidate.is_absolute() or len(candidate.parts) > 1:
        return str(candidate) if candidate.exists() else None
    result = shutil.which(binary)
    if result is not None:
        return result
    # On Windows, only return bare-name files that have a recognised
    # executable extension.  A stale Unix shebang script (e.g. from a
    # macOS sync into .venv/bin/) passes exists() but causes
    # WinError 193 when subprocess tries to run it.
    _win_exec_extensions: frozenset[str] | None = None
    if sys.platform == "win32":
        _win_exec_extensions = frozenset({".exe", ".bat", ".cmd", ".com"})
    # Fallback: check venv-local directories (important on Windows where
    # pip-installed CLI entry points like manim.exe may not be on PATH).
    for directory in (
        Path(sys.executable).parent,
        Path(sys.prefix) / "bin",
        Path(sys.prefix) / "Scripts",
        Path(sys.executable).resolve().parent,
    ):
        sibling = directory / binary
        if sibling.exists():
            if _win_exec_extensions is None or sibling.suffix.lower() in _win_exec_extensions:
                return str(sibling)
            # Bare name exists but is not a valid Windows executable.
            # Fall through to check for companion .exe below.
        windows_sibling = sibling.with_suffix(".exe")
        if windows_sibling.exists():
            return str(windows_sibling)
    return None
