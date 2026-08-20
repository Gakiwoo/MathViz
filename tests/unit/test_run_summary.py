from __future__ import annotations

import json
import sys

import pytest

from math_to_manim.app.run_summary import (
    check_render_health,
    list_runs,
    restage_run,
    safe_run_dir,
    summarize_run,
)
from math_to_manim.config import RuntimeConfig
from math_to_manim.schemas import ConceptIntent, GeneratedCode
from math_to_manim.tools.manim_fixes import preview_safe_generated_code


def write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_run_reads_artifacts_and_missing_render(tmp_path) -> None:
    run_dir = tmp_path / "20260518T000000Z-demo"
    run_dir.mkdir()
    write_json(
        run_dir / "request.json",
        {
            "prompt": "Explain derivatives",
            "target_audience": "high_school",
            "duration_seconds": 60,
            "style": "cinematic",
        },
    )
    write_json(
        run_dir / "curriculum.json",
        {"title": "Derivatives", "learning_objectives": ["See slope as change"], "modules": []},
    )
    write_json(
        run_dir / "storyboard.json",
        {
            "title": "Slope story",
            "scenes": [{"title": "Zoom", "narration": "A secant becomes tangent", "visual_actions": ["Draw curve"]}],
        },
    )
    write_json(
        run_dir / "generated_code.json",
        {
            "scene_name": "DemoScene",
            "code": "from manim import *\nclass DemoScene(Scene):\n    def construct(self):\n        pass\n",
        },
    )
    write_json(
        run_dir / "validation_report.json",
        {
            "status": "passed",
            "issues": [],
            "checked_artifacts": ["generated_scene.py"],
            "summary": "ok",
            "metadata": {},
        },
    )
    write_json(
        run_dir / "render_result.json",
        {
            "status": "skipped",
            "scene_name": "DemoScene",
            "output_path": None,
            "command": [],
            "stderr": "render skipped",
            "metadata": {"skipped": True},
        },
    )
    write_json(
        run_dir / "manifest.json", {"created_at": "2026-05-18T00:00:00+00:00", "artifacts": ["request", "curriculum"]}
    )

    summary = summarize_run(run_dir)

    assert summary["run_id"] == "20260518T000000Z-demo"
    assert summary["prompt"] == "Explain derivatives"
    assert summary["status"]["validation"] == "passed"
    assert summary["status"]["render"] == "skipped"
    assert summary["video_url"] is None
    assert "See slope as change" in summary["sections"]["teaching_plan"]
    assert "DemoScene" in summary["sections"]["manim_code"]


def test_summarize_run_hides_failed_integrity_video(tmp_path) -> None:
    run_dir = tmp_path / "20260518T000000Z-short"
    run_dir.mkdir()
    video_path = run_dir / "media" / "videos" / "generated_scene" / "480p15" / "ShortScene.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"short")
    write_json(run_dir / "request.json", {"prompt": "Short render"})
    write_json(run_dir / "generated_code.json", {"scene_name": "ShortScene", "code": "from manim import *\n"})
    write_json(run_dir / "validation_report.json", {"status": "passed", "issues": [], "metadata": {}})
    write_json(
        run_dir / "render_result.json",
        {"status": "succeeded", "scene_name": "ShortScene", "output_path": str(video_path), "metadata": {}},
    )
    write_json(
        run_dir / "review_report.json",
        {
            "score": 0.4,
            "observations": ["1.000s, target at least 3.000s"],
            "issues": [],
            "metadata": {"render_integrity_passed": False},
        },
    )
    write_json(run_dir / "manifest.json", {"created_at": "2026-05-18T00:00:00+00:00", "artifacts": []})

    summary = summarize_run(run_dir)

    assert summary["video_url"] is None
    assert summary["error"]["stage"] == "video_review"
    assert "1.000s" in summary["error"]["details"]


def test_preview_safe_generated_code_rewrites_latex_text_calls() -> None:
    generated = GeneratedCode(
        scene_name="DemoScene",
        code=(
            "from manim import *\n"
            "class DemoScene(Scene):\n"
            "    def construct(self):\n"
            "        self.add(MathTex(r'x^2', color=YELLOW))\n"
            "        self.add(Tex('m_1', '=', 'm_2', tex_environment='center'))\n"
        ),
        dependencies=["manim"],
        metadata={"file_path": "generated_scene.py"},
    )

    safe = preview_safe_generated_code(generated)

    assert "MathTex" not in safe.code
    assert "Tex(" not in safe.code
    assert "Text(" in safe.code
    assert "tex_environment" not in safe.code
    assert safe.metadata["preview_safe_latex_rewrite"] is True


def test_safe_run_dir_rejects_path_traversal(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    good = runs_dir / "run-a"
    good.mkdir()

    assert safe_run_dir(runs_dir, "run-a") == good.resolve()
    assert safe_run_dir(runs_dir, "../outside") is None


def test_list_runs_orders_newest_first(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    older = runs_dir / "20260518T000000Z-old"
    newer = runs_dir / "20260518T010000Z-new"
    older.mkdir()
    newer.mkdir()

    assert [run["run_id"] for run in list_runs(runs_dir)] == ["20260518T010000Z-new", "20260518T000000Z-old"]


def test_restage_run_reruns_valid_stage(tmp_path) -> None:
    run_dir = tmp_path / "20260518T000000Z-demo"
    run_dir.mkdir()
    write_json(
        run_dir / "request.json",
        {
            "prompt": "Explain derivatives",
            "target_audience": "high_school",
            "duration_seconds": 60,
            "style": "cinematic",
        },
    )

    result = restage_run(run_dir, RuntimeConfig(deterministic=True), "intent")

    assert result["stage"] == "intent"
    assert result["status"] == "ok"
    intent = json.loads((run_dir / "intent.json").read_text(encoding="utf-8"))
    assert intent["primary_concept"]
    ConceptIntent.model_validate(intent)


def test_restage_run_unknown_stage_returns_error(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = restage_run(run_dir, RuntimeConfig(), "bogus_stage")

    assert "error" in result
    assert "bogus_stage" in result["error"]


def test_restage_run_missing_input_artifact_returns_error(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = restage_run(run_dir, RuntimeConfig(deterministic=True), "intent")

    assert "error" in result
    assert "Missing input artifact" in result["error"]


def test_check_render_health_reports_missing_fake_binaries() -> None:
    health = check_render_health(
        manim_bin="missing-manim-for-test",
        ffmpeg_bin="missing-ffmpeg-for-test",
        latex_bin="missing-latex-for-test",
    )

    assert health["ready"] is False
    assert health["tools"]["manim"]["available"] is False
    assert health["tools"]["ffmpeg"]["available"] is False
    assert health["tools"]["latex"]["available"] is False
    assert health["blocking_missing"] == ["manim", "ffmpeg"]
    assert "latex" in health["optional_missing"]
    assert "./scripts/bootstrap-render-macos.sh" in health["install_commands"]
    assert ".\\scripts\\bootstrap-render-windows.ps1" in health["install_commands"]


@pytest.mark.skipif(sys.platform == "win32", reason="Unix shebang script is not a valid Windows executable")
def test_check_render_health_finds_venv_local_binaries(tmp_path, monkeypatch) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    # Use a unique name not on PATH so the test isolates fallback resolution
    manim = venv_bin / "m2m2-test-manim"
    manim.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    manim.chmod(0o755)
    python = venv_bin / "python"
    python.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    python.chmod(0o755)
    monkeypatch.setattr("sys.executable", str(python))

    health = check_render_health(
        manim_bin="m2m2-test-manim", ffmpeg_bin="missing-ffmpeg-for-test", latex_bin="missing-latex-for-test"
    )

    assert health["tools"]["manim"]["available"] is True
    assert health["tools"]["manim"]["path"] == str(manim)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix shebang script is not a valid Windows executable")
def test_check_render_health_finds_sys_prefix_binaries(tmp_path, monkeypatch) -> None:
    venv_bin = tmp_path / "bin"
    venv_bin.mkdir()
    manim = venv_bin / "m2m2-test-manim"
    manim.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    manim.chmod(0o755)
    python_bin = tmp_path / "other" / "python"
    python_bin.parent.mkdir()
    python_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    python_bin.chmod(0o755)
    monkeypatch.setattr("sys.executable", str(python_bin))
    monkeypatch.setattr("sys.prefix", str(tmp_path))

    health = check_render_health(
        manim_bin="m2m2-test-manim", ffmpeg_bin="missing-ffmpeg-for-test", latex_bin="missing-latex-for-test"
    )

    assert health["tools"]["manim"]["available"] is True
    assert health["tools"]["manim"]["path"] == str(manim)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix shebang script is not a valid Windows executable")
def test_check_render_health_treats_latex_as_optional(tmp_path, monkeypatch) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    for name in ("m2m2-test-manim", "ffmpeg"):
        binary = venv_bin / name
        binary.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
        binary.chmod(0o755)
    python = venv_bin / "python"
    python.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    python.chmod(0o755)
    monkeypatch.setattr("sys.executable", str(python))

    health = check_render_health(manim_bin="m2m2-test-manim", ffmpeg_bin="ffmpeg", latex_bin="missing-latex-for-test")

    assert health["ready"] is True
    assert "latex" in health["missing"]
    assert health["blocking_missing"] == []
    assert "latex" in health["optional_missing"]
    assert health["tools"]["latex"]["required"] is False
