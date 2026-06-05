"""Extended tests for AnimationPipeline covering repair loops and edge cases."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from math_to_manim.agents.render import RenderAgent
from math_to_manim.agents.static_review import StaticReviewAgent
from math_to_manim.agents.video_review import VideoReviewAgent
from math_to_manim.config import RuntimeConfig
from math_to_manim.pipeline.runner import AnimationPipeline, _safe_scene_name
from math_to_manim.schemas import (
    AnimationPackage,
    ConceptIntent,
    CurriculumPlan,
    GeneratedCode,
    KnowledgeGraph,
    KnowledgeGraphNode,
    ManimSceneSpec,
    MathPacket,
    RenderResult,
    UserRequest,
    ValidationIssue,
    ValidationReport,
    VideoReviewReport,
    VisualStoryboard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_deterministic_generated_code(scene_name: str = "TestScene") -> GeneratedCode:
    """Return a GeneratedCode whose code is valid enough for write_generated_code."""
    return GeneratedCode(
        scene_name=scene_name,
        code=(
            "from manim import *\n\n"
            f"class {scene_name}(Scene):\n"
            "    def construct(self) -> None:\n"
            "        self.wait(1)\n"
        ),
        metadata={"file_path": "generated_scene.py"},
    )


def _make_passing_validation() -> ValidationReport:
    return ValidationReport(
        status="passed",
        issues=[],
        summary="Static validation passed.",
        metadata={"ast_valid": True, "scene_found": True, "scene_classes": ["TestScene"]},
    )


def _make_failing_validation(*, messages: list[str] | None = None) -> ValidationReport:
    msgs = messages or ["syntax error near line 10"]
    return ValidationReport(
        status="failed",
        issues=[ValidationIssue(code="E001", message=m, severity="error") for m in msgs],
        summary="Static validation failed.",
        metadata={"ast_valid": False, "scene_found": False, "scene_classes": []},
    )


def _make_rendered_ok(scene_name: str = "TestScene") -> RenderResult:
    return RenderResult(
        status="succeeded",
        scene_name=scene_name,
        output_path="/fake/output.mp4",
        command=["python", "-m", "manim"],
        stdout="render ok",
        stderr=None,
        metadata={},
    )


def _make_rendered_failed(scene_name: str = "TestScene", *, stderr: str = "") -> RenderResult:
    return RenderResult(
        status="failed",
        scene_name=scene_name,
        output_path=None,
        command=[],
        stdout="",
        stderr=stderr or "Manim render crashed",
        metadata={},
    )


def _stub_pipeline_agents(pipeline: AnimationPipeline) -> None:
    """Stub every pipeline agent so ``generate()`` can run with ``deterministic=False``
    without hitting any real API or SDK calls."""
    pipeline.intent_agent.run = Mock(return_value=ConceptIntent(primary_concept="derivatives"))
    pipeline.graph_agent.run = Mock(
        return_value=KnowledgeGraph(
            nodes=[KnowledgeGraphNode(id="derivatives", label="derivatives", kind="concept")],
            edges=[],
            root_node_id="derivatives",
        )
    )
    pipeline.curriculum_agent.run = Mock(return_value=CurriculumPlan(title="test"))
    pipeline.math_agent.run = Mock(return_value=MathPacket())
    pipeline.storyboard_agent.run = Mock(return_value=VisualStoryboard(title="test"))
    pipeline.scene_spec_agent.run = Mock(
        return_value=ManimSceneSpec(
            scene_name="TestScene",
            imports=["from manim import *"],
        )
    )
    pipeline.codegen_agent.run = Mock(return_value=_make_deterministic_generated_code())
    # repair and render are configured per-test
    # video_review_agent and publisher_agent are left running their real
    # implementations because they only assemble data from previous stages.


# ---------------------------------------------------------------------------
# Static validation repair loop  (lines 122-140)
# ---------------------------------------------------------------------------


class TestStaticValidationRepairLoop:
    """Covers the ``while`` loop at runner.py lines 117-141.

    When validation fails *and* the config is non-deterministic *and* repair
    attempts remain, the pipeline should call ``codegen_agent.repair()`` and
    re-validate.
    """

    def test_repair_loop_reruns_after_failed_validation(
        self, tmp_path: Path
    ) -> None:
        """Validation fails on the first attempt and passes after one repair."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            max_static_repairs=3,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # First validation call → fail; second (after repair) → pass
        pipeline.static_review_agent.run = Mock(
            side_effect=[_make_failing_validation(), _make_passing_validation()]
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=False,
        )

        # repair was called exactly once
        pipeline.codegen_agent.repair.assert_called_once()
        # Two validation calls (first fail, second pass after repair)
        assert pipeline.static_review_agent.run.call_count == 2
        # Repair artifact was persisted
        repair_files = list(tmp_path.rglob("generated_code_repair_1.json"))
        assert len(repair_files) == 1
        # Final validation report should be "passed"
        assert package.validation_report is not None
        assert package.validation_report.status == "passed"

    def test_repair_loop_exits_after_max_attempts(self, tmp_path: Path) -> None:
        """All repair attempts fail; the loop exits after ``max_static_repairs``
        without ever getting a passing validation."""
        max_repairs = 2
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            max_static_repairs=max_repairs,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Always fail — one initial + two repair attempts = 3 calls
        pipeline.static_review_agent.run = Mock(
            return_value=_make_failing_validation()
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=False,
        )

        # repair() called max_repairs times
        assert pipeline.codegen_agent.repair.call_count == max_repairs
        # static_review.run called 1 (initial) + max_repairs (after each repair)
        assert pipeline.static_review_agent.run.call_count == 1 + max_repairs
        # Final validation is still failed
        assert package.validation_report is not None
        assert package.validation_report.status == "failed"
        # Repair artifacts persisted for each attempt
        for i in range(1, max_repairs + 1):
            assert list(tmp_path.rglob(f"generated_code_repair_{i}.json"))

    def test_repair_loop_does_not_run_when_deterministic(self, tmp_path: Path) -> None:
        """The repair loop condition requires ``not self.config.deterministic``,
        so it is skipped when ``deterministic=True`` even if validation fails."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,  # <-- blocks the repair loop
            max_static_repairs=3,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Force validation to fail so the only thing keeping the repair
        # loop from running is the ``deterministic=True`` check.
        pipeline.static_review_agent.run = Mock(
            return_value=_make_failing_validation()
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        pipeline.generate(
            prompt="test prompt",
            render=False,
        )

        # repair must NOT be called because the while-condition short-circuits
        # on ``not self.config.deterministic``.
        pipeline.codegen_agent.repair.assert_not_called()


# ---------------------------------------------------------------------------
# Render + render repair loop  (lines 143-191)
# ---------------------------------------------------------------------------


class TestRenderRepairLoop:
    """Covers the render-attempt and render-repair-loop at lines 142-194."""

    def test_render_succeeds_without_repair(self, tmp_path: Path) -> None:
        """Render succeeds on the first attempt; no render repair loop runs."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)
        pipeline.static_review_agent.run = Mock(
            return_value=_make_passing_validation()
        )
        pipeline.render_agent.run = Mock(
            return_value=_make_rendered_ok()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=True,
        )

        pipeline.render_agent.run.assert_called_once()
        assert package.render_result is not None
        assert package.render_result.status == "succeeded"

    def test_render_repair_loop_runs_after_failed_render(self, tmp_path: Path) -> None:
        """Render fails on the first attempt, then the repair loop fixes it."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            max_render_repairs=3,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Validation always passes
        pipeline.static_review_agent.run = Mock(
            return_value=_make_passing_validation()
        )
        # Render fails first, succeeds after repair
        pipeline.render_agent.run = Mock(
            side_effect=[_make_rendered_failed(stderr="NameError: x not defined"),
                         _make_rendered_ok()]
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=True,
        )

        # repair() called once (after first render failure)
        pipeline.codegen_agent.repair.assert_called_once()
        # render_agent.run called twice (fail + succeed)
        assert pipeline.render_agent.run.call_count == 2
        # Final render status is succeeded
        assert package.render_result is not None
        assert package.render_result.status == "succeeded"

    def test_render_repair_loop_exits_after_max_attempts(self, tmp_path: Path) -> None:
        """All render attempts fail; the loop exits after max_render_repairs."""
        max_repairs = 2
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            max_render_repairs=max_repairs,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Validation always passes
        pipeline.static_review_agent.run = Mock(
            return_value=_make_passing_validation()
        )
        # Render always fails
        pipeline.render_agent.run = Mock(
            return_value=_make_rendered_failed(stderr="render error")
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=True,
        )

        assert pipeline.codegen_agent.repair.call_count == max_repairs
        # Render calls: 1 initial + max_repairs (one per repair loop iteration)
        assert pipeline.render_agent.run.call_count == 1 + max_repairs
        assert package.render_result is not None
        # The last render is still failed (no successful render to break the loop)
        assert package.render_result.status == "failed"
        # Render artifacts saved
        assert list(tmp_path.rglob("render_result.json"))

    def test_render_repair_resets_validation_and_re_renders(self, tmp_path: Path) -> None:
        """When, inside the render repair loop, re-validation passes,
        the pipeline re-applies manim fixes and calls render_agent again."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            max_render_repairs=3,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Validation always passes (both initial and within repair loop)
        pipeline.static_review_agent.run = Mock(
            return_value=_make_passing_validation()
        )
        # Render fails → repair → render succeeds
        pipeline.render_agent.run = Mock(
            side_effect=[_make_rendered_failed(stderr="error"),
                         _make_rendered_ok()]
        )
        pipeline.codegen_agent.repair = Mock(
            return_value=_make_deterministic_generated_code()
        )

        pipeline.generate(
            prompt="test prompt",
            render=True,
        )

        # After repair, static_review_agent.run was called again (line 174)
        assert pipeline.static_review_agent.run.call_count >= 2

    def test_render_skipped_when_validation_fails(self, tmp_path: Path) -> None:
        """When ``render=True`` but validation is not successful, the pipeline
        does NOT attempt to render and instead produces a skipped render_result."""
        config = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
        )
        pipeline = AnimationPipeline(config)
        _stub_pipeline_agents(pipeline)

        # Validation fails permanently
        pipeline.static_review_agent.run = Mock(
            return_value=_make_failing_validation()
        )

        package = pipeline.generate(
            prompt="test prompt",
            render=True,
        )

        assert package.render_result is not None
        assert package.render_result.status == "failed"
        assert package.render_result.stderr is not None
        assert "validation did not pass" in package.render_result.stderr
        # render_agent.run should never have been called
        # (render_agent is a real object, but since we stubbed static_review
        #  to always fail, the code never reaches render_agent.run)
        assert package.validation_report is not None
        assert package.validation_report.status == "failed"


# ---------------------------------------------------------------------------
# _safe_scene_name edge case  (line 286 / line 330-332)
# ---------------------------------------------------------------------------


class TestSafeSceneName:
    """Covers the ``_safe_scene_name`` helper function."""

    def test_class_name_already_ends_with_scene(self) -> None:
        """When the constructed class_name already ends with 'Scene',
        it is returned as-is (truncated to 80 chars)."""
        result = _safe_scene_name("Scene")
        assert result == "Scene"

    def test_class_name_with_scene_suffix_preserved(self) -> None:
        """Prompt that produces a name naturally ending in 'Scene'.
        Note: ``.capitalize()`` lowercases the remainder, so "TestScene"
        becomes "Testscene", which does NOT end with "Scene", so the function
        appends "Scene" producing "TestsceneScene".
        """
        result = _safe_scene_name("TestScene")
        assert result == "TestsceneScene"

    def test_class_name_appends_scene_when_missing(self) -> None:
        """When class_name does not end with 'Scene', the function appends it."""
        result = _safe_scene_name("Derivative")
        assert result == "DerivativeScene"

    def test_class_name_truncated_at_80_chars(self) -> None:
        """The function guarantees the returned name is at most 80 characters."""
        long_prompt = "A Very Long Concept Name That Exceeds The Eighty Character Limit " * 5
        result = _safe_scene_name(long_prompt)
        assert len(result) <= 80

    def test_class_name_empty_prompt_falls_back_to_generated(self) -> None:
        """When the prompt contains no alphanumeric characters it defaults to
        'Generated'."""
        result = _safe_scene_name("!!! ### $$$")
        assert result == "GeneratedScene"


# ---------------------------------------------------------------------------
# AnimationPipeline.render_existing()  (lines 254-297)
# ---------------------------------------------------------------------------


class TestRenderExisting:
    """Covers the ``render_existing`` static method."""

    def _create_fake_run_dir(self, tmp_path: Path, scene_name: str = "ExistingScene") -> Path:
        """Populate a directory with a ``generated_code.json`` artifact."""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir(parents=True)
        code = GeneratedCode(
            scene_name=scene_name,
            code=(
                "from manim import *\n\n"
                f"class {scene_name}(Scene):\n"
                "    def construct(self) -> None:\n"
                "        self.wait(1)\n"
            ),
        )
        (run_dir / "generated_code.json").write_text(
            json.dumps(code.to_public_dict(), indent=2), encoding="utf-8"
        )
        return run_dir

    def test_render_existing_reads_code_and_writes_reports(
        self, tmp_path: Path
    ) -> None:
        """Verifies the method reads ``generated_code.json``, runs validation,
        renders, and persists ``validation_report.json`` and ``render_result.json``."""
        run_dir = self._create_fake_run_dir(tmp_path)

        cfg = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
        )

        # Patch the agents used inside render_existing
        with (
            patch.object(StaticReviewAgent, "run", return_value=_make_passing_validation()) as mock_validate,
            patch.object(RenderAgent, "run", return_value=_make_rendered_ok()) as mock_render,
            patch.object(VideoReviewAgent, "run", return_value=VideoReviewReport(approved=False, score=0.0)),
        ):
            AnimationPipeline.render_existing(run_dir, config=cfg)

        # Assert files were written
        assert (run_dir / "validation_report.json").exists()
        assert (run_dir / "render_result.json").exists()
        assert (run_dir / "review_report.json").exists()

        # Validate the content of validation_report.json
        report_data = json.loads((run_dir / "validation_report.json").read_text(encoding="utf-8"))
        assert report_data["status"] == "passed"

        # Validate the content of render_result.json
        render_data = json.loads((run_dir / "render_result.json").read_text(encoding="utf-8"))
        assert render_data["status"] == "succeeded"

        # Verify agents were called
        mock_validate.assert_called_once()
        mock_render.assert_called_once()

    def test_render_existing_skips_render_when_validation_fails(
        self, tmp_path: Path
    ) -> None:
        """When static validation fails, render_existing writes a 'skipped'
        render result instead of calling RenderAgent."""
        run_dir = self._create_fake_run_dir(tmp_path)

        cfg = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
        )

        with (
            patch.object(StaticReviewAgent, "run", return_value=_make_failing_validation()) as mock_validate,
            patch.object(RenderAgent, "run") as mock_render,
            patch.object(VideoReviewAgent, "run", return_value=VideoReviewReport(approved=False, score=0.0)),
        ):
            AnimationPipeline.render_existing(run_dir, config=cfg)

        assert (run_dir / "validation_report.json").exists()
        assert (run_dir / "render_result.json").exists()

        render_data = json.loads((run_dir / "render_result.json").read_text(encoding="utf-8"))
        assert render_data["status"] == "skipped"

        mock_validate.assert_called_once()
        # RenderAgent should NOT be called when validation fails
        mock_render.assert_not_called()

    def test_render_existing_uses_provided_config(self, tmp_path: Path) -> None:
        """The ``config`` argument is passed through to the agents created
        inside the method."""
        run_dir = self._create_fake_run_dir(tmp_path)

        cfg = RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=False,
            default_quality="h",
        )

        with (
            patch.object(StaticReviewAgent, "run", return_value=_make_passing_validation()) as mock_validate,
            patch.object(RenderAgent, "run", return_value=_make_rendered_ok()) as mock_render,
            patch.object(VideoReviewAgent, "run", return_value=VideoReviewReport(approved=False, score=0.0)),
        ):
            AnimationPipeline.render_existing(run_dir, config=cfg)

        # Verify the render agent received the quality from our config
        # RenderAgent.run takes a single tuple (generated, code_path, quality)
        # as its positional argument.
        call_args = mock_render.call_args[0]
        assert call_args[0][2] == "h"
