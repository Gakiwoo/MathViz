"""Optional Manim CLI wrapper."""

from __future__ import annotations

import ast
import subprocess
import sys  # noqa: F401 — used via monkeypatch in tests
from pathlib import Path

from .commands import ToolResult, resolve_binary

QUALITY_FLAGS = {
    "draft": "-ql",
    "l": "-ql",
    "low": "-ql",
    "m": "-qm",
    "medium": "-qm",
    "h": "-qh",
    "high": "-qh",
    "p": "-qp",
    "production": "-qp",
    "k": "-qk",
    "4k": "-qk",
}
LATEX_BACKED_CALLS = {"MathTex", "Tex", "SingleStringMathTex", "BulletedList", "TexTemplate"}


def render_manim_scene(
    source_path: str | Path,
    *,
    scene_name: str | None = None,
    output_dir: str | Path | None = None,
    quality: str = "low",
    manim_bin: str = "manim",
    latex_bin: str = "latex",
    timeout_seconds: float = 120.0,
    working_dir: str | Path | None = None,
    dry_run: bool = False,
) -> ToolResult:
    """Render a Manim scene with the local CLI if it is installed.

    Missing Manim is reported as a skipped result instead of an exception.
    """

    source = Path(source_path).resolve()
    binary = _resolve_tool_binary(manim_bin)
    flag = _quality_flag(quality)
    command = [binary or manim_bin, flag, str(source)]
    if scene_name:
        command.append(scene_name)
    if output_dir is not None:
        media_dir = Path(output_dir).resolve()
        media_dir.mkdir(parents=True, exist_ok=True)
        command.extend(["--media_dir", str(media_dir)])

    if binary is None:
        return ToolResult(False, True, tuple(command), reason=f"Manim binary not found: {manim_bin}")
    if dry_run:
        return ToolResult(True, True, tuple(command), reason="dry run", metadata={"quality": quality})
    if not source.exists():
        return ToolResult(False, True, tuple(command), reason=f"Scene source not found: {source}")
    latex_calls = _latex_backed_calls(source)
    if latex_calls and _resolve_tool_binary(latex_bin) is None:
        calls = ", ".join(latex_calls)
        return ToolResult(
            False,
            True,
            tuple(command),
            reason=(
                f"LaTeX binary not found: {latex_bin}. Scene code uses {calls}, which require LaTeX. "
                "Install BasicTeX/MacTeX, MiKTeX, or TeX Live, or regenerate with plain Text labels."
            ),
            metadata={"missing_tool": "latex", "latex_required": True, "latex_calls": tuple(latex_calls)},
        )

    try:
        completed = subprocess.run(
            command,
            cwd=str(working_dir) if working_dir is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            False,
            False,
            tuple(command),
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            reason=f"Timed out after {timeout_seconds} seconds",
        )
    except OSError as exc:
        return ToolResult(
            False,
            False,
            tuple(command),
            reason=f"Failed to execute {command[0]}: {exc}",
            stderr=str(exc),
        )

    output_path = (
        _discover_rendered_video(Path(output_dir) if output_dir is not None else None)
        if completed.returncode == 0
        else None
    )
    return ToolResult(
        completed.returncode == 0,
        False,
        tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        output_path=output_path,
    )


def _quality_flag(quality: str) -> str:
    if quality.startswith("-q"):
        return quality
    try:
        return QUALITY_FLAGS[quality]
    except KeyError as exc:
        valid = ", ".join(sorted(QUALITY_FLAGS))
        raise ValueError(f"Unknown Manim quality '{quality}'. Valid values: {valid}") from exc


def _latex_backed_calls(source: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()

    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in LATEX_BACKED_CALLS:
            calls.add(name)
    return tuple(sorted(calls))


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _resolve_tool_binary(binary: str) -> str | None:
    return resolve_binary(binary)


def _discover_rendered_video(media_dir: Path | None) -> Path | None:
    if media_dir is None or not media_dir.exists():
        return None
    videos = [path for path in media_dir.rglob("*.mp4") if path.is_file() and "partial_movie_files" not in path.parts]
    if not videos:
        return None
    return max(videos, key=lambda path: path.stat().st_mtime)
