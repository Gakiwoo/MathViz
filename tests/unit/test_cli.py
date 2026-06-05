from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from math_to_manim.cli import build_parser, main


def test_parser_rejects_no_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_generate_accepts_prompt_and_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["generate", "explain slopes"])

    assert args.command == "generate"
    assert args.prompt == "explain slopes"
    assert args.audience_level == "high_school"
    assert args.duration == 60
    assert args.style == "cinematic"
    assert args.no_render is False
    assert args.deterministic is False
    assert args.json is False


def test_parser_generate_no_render_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["generate", "test", "--no-render"])

    assert args.no_render is True


def test_parser_generate_deterministic_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["generate", "test", "--deterministic"])

    assert args.deterministic is True


def test_parser_generate_json_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["generate", "test", "--json"])

    assert args.json is True


def test_parser_generate_optional_args() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "generate",
            "test prompt",
            "--audience-level", "university",
            "--duration", "120",
            "--style", "geometric",
            "--quality", "h",
            "--model", "gpt-4",
            "--codegen-provider", "codex-cli",
            "--codex-full-auto",
        ]
    )

    assert args.audience_level == "university"
    assert args.duration == 120
    assert args.style == "geometric"
    assert args.quality == "h"
    assert args.model == "gpt-4"
    assert args.codegen_provider == "codex-cli"
    assert args.codex_full_auto is True


def test_parser_inspect_run_accepts_path() -> None:
    parser = build_parser()
    args = parser.parse_args(["inspect-run", "/some/path"])

    assert args.command == "inspect-run"
    assert args.run_dir == Path("/some/path")


def test_parser_generate_runs_dir_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["generate", "test", "--runs-dir", "/tmp/custom"])

    assert args.runs_dir == Path("/tmp/custom")


def test_main_generate_deterministic_no_render_returns_zero() -> None:
    with TemporaryDirectory() as tmpdir:
        exit_code = main(
            [
                "generate",
                "Test prompt for CLI",
                "--deterministic",
                "--no-render",
                "--runs-dir",
                tmpdir,
            ]
        )

    assert exit_code == 0


def test_main_generate_json_output_returns_zero() -> None:
    with TemporaryDirectory() as tmpdir:
        exit_code = main(
            ["generate", "Test prompt", "--deterministic", "--no-render", "--json", "--runs-dir", tmpdir]
        )

    assert exit_code == 0


def test_main_generate_deterministic_produces_manifest() -> None:
    with TemporaryDirectory() as tmpdir:
        main(
            [
                "generate",
                "Derivative slope test",
                "--deterministic",
                "--no-render",
                "--runs-dir",
                tmpdir,
            ]
        )
        runs = list(Path(tmpdir).iterdir())
        assert len(runs) == 1
        manifest = runs[0] / "manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "animation_package" in data["artifacts"]
        assert "generated_code" in data["artifacts"]


def test_main_generate_json_output_is_valid_json() -> None:
    with TemporaryDirectory() as tmpdir:
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "math_to_manim.cli",
                "generate",
                "JSON test prompt",
                "--deterministic",
                "--no-render",
                "--json",
                "--runs-dir",
                tmpdir,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert "request" in parsed
        assert parsed["request"]["prompt"] == "JSON test prompt"


def test_main_inspect_run_rejects_missing_manifest() -> None:
    with TemporaryDirectory() as tmpdir:
        with pytest.raises(SystemExit):
            main(["inspect-run", tmpdir])
