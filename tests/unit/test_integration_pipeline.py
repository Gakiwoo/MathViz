"""Integration tests for the deterministic end-to-end AnimationPipeline.

These tests exercise the full 11-stage pipeline with ``deterministic=True``,
verifying that every artifact is produced, each JSON file is parseable, and
the generated Manim code passes basic static validation.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from math_to_manim.config import RuntimeConfig
from math_to_manim.pipeline.runner import AnimationPipeline

# ---------------------------------------------------------------------------
# Full pipeline — no render
# ---------------------------------------------------------------------------


def _run_and_get_artifacts(
    tmp_path: Path,
    *,
    prompt: str = "Explain why derivatives are slopes",
    audience_level: str = "high_school",
    desired_duration: int = 45,
    style: str = "clean classroom",
    render: bool = False,
) -> tuple[Path, dict[str, dict]]:
    """Run the deterministic pipeline and return (run_dir, artifacts_by_name)."""
    config = RuntimeConfig(
        runs_dir=tmp_path,
        deterministic=True,
        trace_enabled=True,
    )
    pipeline = AnimationPipeline(config)
    pipeline.generate(
        prompt=prompt,
        audience_level=audience_level,
        desired_duration=desired_duration,
        style=style,
        render=render,
    )
    run_dir = next(tmp_path.iterdir())
    artifacts: dict[str, dict] = {}
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "trace.jsonl":
            continue
        artifacts[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return run_dir, artifacts


class TestDeterministicPipelineProducesAllArtifacts:
    """Every stage in the pipeline must write its JSON artifact."""

    EXPECTED_ARTIFACTS = frozenset(
        {
            "request",
            "intent",
            "knowledge_graph",
            "curriculum",
            "math_packet",
            "storyboard",
            "scene_spec",
            "generated_code",
            "validation_report",
            "render_result",
            "review_report",
            "animation_package",
            "manifest",
        }
    )

    def test_all_artifacts_exist(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        missing = self.EXPECTED_ARTIFACTS - set(artifacts)
        assert not missing, f"Missing artifacts: {sorted(missing)}"

    def test_generated_scene_py_exists_and_parses(self, tmp_path: Path) -> None:
        run_dir, _ = _run_and_get_artifacts(tmp_path)

        scene_path = run_dir / "generated_scene.py"
        assert scene_path.exists(), "generated_scene.py not written"

        code = scene_path.read_text(encoding="utf-8")
        # Must be syntactically valid Python
        try:
            ast.parse(code)
        except SyntaxError as exc:
            pytest.fail(f"generated_scene.py has invalid syntax: {exc}")

        # Must define at least one Scene subclass
        tree = ast.parse(code)
        scene_classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id == "Scene" for base in node.bases)
        ]
        assert scene_classes, "No Scene subclass found in generated_scene.py"

    def test_trace_jsonl_exists_when_trace_enabled(self, tmp_path: Path) -> None:
        run_dir, _ = _run_and_get_artifacts(tmp_path)

        trace_path = run_dir / "trace.jsonl"
        assert trace_path.exists(), "trace.jsonl not written when trace_enabled=True"

        lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 3, f"Expected at least 3 trace events, got {len(lines)}"
        for line in lines:
            event = json.loads(line)
            assert "stage" in event, f"Trace event missing 'stage' key: {list(event.keys())}"
            assert "payload" in event, "Trace event missing 'payload' key"
            assert "timestamp" in event, "Trace event missing 'timestamp' key"

    def test_no_trace_when_disabled(self, tmp_path: Path) -> None:
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,
            trace_enabled=False,
        )
        pipeline = AnimationPipeline(config)
        pipeline.generate(prompt="limit definition", render=False)

        run_dir = next(tmp_path.iterdir())
        assert not (run_dir / "trace.jsonl").exists()


# ---------------------------------------------------------------------------
# Validation and render status
# ---------------------------------------------------------------------------


class TestDeterministicValidationAndRender:
    """Static validation must pass; render must be skipped when not requested."""

    def test_validation_passes(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        validation = artifacts["validation_report"]
        assert validation["status"] == "passed", (
            f"Expected passed, got {validation['status']}: {validation.get('summary')}"
        )

    def test_render_is_skipped_when_not_requested(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path, render=False)

        render = artifacts["render_result"]
        assert render["metadata"]["skipped"] is True

    def test_render_requested_but_skipped_without_manim(self, tmp_path: Path) -> None:
        """When render=True but Manim is not installed, result is a skipped failure."""
        _, artifacts = _run_and_get_artifacts(tmp_path, render=True)

        render = artifacts["render_result"]
        # Deterministic mode may skip render, or fail gracefully
        assert render["status"] in ("skipped", "failed"), f"Unexpected render status: {render['status']}"


# ---------------------------------------------------------------------------
# Content quality checks
# ---------------------------------------------------------------------------


class TestDeterministicContentQuality:
    """Verify that deterministic output is substantive, not placeholder text."""

    def test_generated_code_uses_text_not_mathtex(self, tmp_path: Path) -> None:
        """Deterministic codegen must not require LaTeX."""
        run_dir, _ = _run_and_get_artifacts(tmp_path)
        code = (run_dir / "generated_scene.py").read_text(encoding="utf-8")
        assert "MathTex" not in code, "Deterministic codegen must avoid MathTex"

    def test_generated_code_has_manim_imports(self, tmp_path: Path) -> None:
        run_dir, _ = _run_and_get_artifacts(tmp_path)
        code = (run_dir / "generated_scene.py").read_text(encoding="utf-8")
        assert "from manim import *" in code or "from manim import " in code

    def test_prompt_not_embedded_verbatim_in_code(self, tmp_path: Path) -> None:
        """The raw user prompt must not appear as a string literal in generated code."""
        run_dir, _ = _run_and_get_artifacts(tmp_path, prompt="Explain the chain rule")
        code = (run_dir / "generated_scene.py").read_text(encoding="utf-8")
        assert "Explain the chain rule" not in code

    def test_knowledge_graph_has_nodes(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        graph = artifacts["knowledge_graph"]
        assert len(graph.get("nodes", graph.get("concepts", []))) >= 1
        assert graph.get("root_node_id") is not None

    def test_curriculum_has_title(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        curriculum = artifacts["curriculum"]
        assert curriculum.get("title"), "Curriculum must have a title"

    def test_storyboard_has_scenes(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        storyboard = artifacts["storyboard"]
        scenes = storyboard.get("scenes", [])
        assert len(scenes) >= 1, "Storyboard must have at least one scene"


# ---------------------------------------------------------------------------
# Multiple topics and audience levels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt,audience_level,style",
    [
        ("What is a derivative?", "high_school", "clean classroom"),
        ("Explain the Pythagorean theorem with areas", "middle_school", "geometry"),
        ("What is a limit in calculus?", "undergraduate", "cinematic"),
        ("解释为什么导数表示斜率", "high_school", "clean classroom"),
    ],
)
def test_deterministic_pipeline_with_various_inputs(
    tmp_path: Path,
    prompt: str,
    audience_level: str,
    style: str,
) -> None:
    """The deterministic pipeline must complete successfully for all inputs."""
    config = RuntimeConfig(
        runs_dir=tmp_path,
        deterministic=True,
        trace_enabled=False,
    )
    pipeline = AnimationPipeline(config)
    package = pipeline.generate(
        prompt=prompt,
        audience_level=audience_level,
        desired_duration=45,
        style=style,
        render=False,
    )

    assert package.validation_report is not None
    assert package.validation_report.status == "passed"
    assert package.intent is not None
    assert package.knowledge_graph is not None
    assert package.curriculum_plan is not None
    assert package.storyboard is not None

    run_dir = next(tmp_path.iterdir())
    scene_path = run_dir / "generated_scene.py"
    assert scene_path.exists()
    ast.parse(scene_path.read_text(encoding="utf-8"))  # must be valid Python


# ---------------------------------------------------------------------------
# Manifest and reproducibility
# ---------------------------------------------------------------------------


class TestManifestAndReproducibility:
    def test_manifest_structure(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        manifest = artifacts["manifest"]
        assert "run_dir" in manifest
        assert "created_at" in manifest
        assert "artifacts" in manifest
        assert isinstance(manifest["artifacts"], list)
        assert len(manifest["artifacts"]) >= 10

    def test_animation_package_has_all_stages(self, tmp_path: Path) -> None:
        _, artifacts = _run_and_get_artifacts(tmp_path)

        package = artifacts["animation_package"]
        for key in (
            "intent",
            "knowledge_graph",
            "curriculum_plan",
            "math_packet",
            "storyboard",
            "scene_specs",
            "generated_code",
            "validation_report",
            "render_result",
        ):
            assert key in package, f"animation_package missing key: {key}"
