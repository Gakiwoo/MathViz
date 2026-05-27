from __future__ import annotations

import json

from math_to_manim.config import RuntimeConfig
from math_to_manim.pipeline.runner import AnimationPipeline


def test_pipeline_generates_no_render_vertical_slice(tmp_path) -> None:
    pipeline = AnimationPipeline(
        RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,
            trace_enabled=True,
        )
    )

    package = pipeline.generate(
        prompt="Explain why derivatives are slopes",
        audience_level="high_school",
        desired_duration=45,
        style="cinematic",
        render=False,
    )

    run_dir = next(tmp_path.iterdir())
    assert package.validation_report is not None
    assert package.validation_report.status == "passed"
    assert package.render_result is not None
    assert package.render_result.metadata["skipped"] is True
    assert (run_dir / "request.json").exists()
    assert (run_dir / "knowledge_graph.json").exists()
    assert (run_dir / "generated_scene.py").exists()
    assert (run_dir / "manifest.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["render_requested"] is False
    assert "knowledge_graph" in manifest["artifacts"]


def test_deterministic_pipeline_uses_text_for_formula_labels(tmp_path) -> None:
    pipeline = AnimationPipeline(
        RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,
            trace_enabled=False,
        )
    )

    pipeline.generate(
        prompt="Explain why derivatives are slopes",
        audience_level="high_school",
        desired_duration=45,
        style="cinematic",
        render=False,
    )

    run_dir = next(tmp_path.iterdir())
    generated_code = (run_dir / "generated_scene.py").read_text(encoding="utf-8")
    scene_spec = json.loads((run_dir / "scene_spec.json").read_text(encoding="utf-8"))

    # Deterministic codegen uses Text (not MathTex) to avoid LaTeX dependency
    assert "MathTex" not in generated_code
    assert "Text" in generated_code
    assert "derivatives" in scene_spec["scene_name"].lower()


def test_pipeline_preserves_long_prompt_for_codegen_with_safe_scene_name(tmp_path) -> None:
    long_prompt = " ".join(["Explain GRPO semantic manifolds with LaTeX zooms"] * 20)
    pipeline = AnimationPipeline(
        RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,
            trace_enabled=False,
        )
    )

    pipeline.generate(
        prompt=long_prompt,
        audience_level="advanced",
        desired_duration=240,
        style="cinematic 3D",
        render=False,
    )

    run_dir = next(tmp_path.iterdir())
    scene_spec = json.loads((run_dir / "scene_spec.json").read_text(encoding="utf-8"))
    assert scene_spec["scene_name"].endswith("Scene")
    assert len(scene_spec["scene_name"]) <= 80
    assert scene_spec["metadata"]["original_prompt"] == long_prompt
    assert scene_spec["metadata"]["requested_duration_seconds"] == 240
    assert scene_spec["metadata"]["render_command"].endswith(f"generated_scene.py {scene_spec['scene_name']}")
    assert long_prompt not in scene_spec["metadata"]["render_command"]


def test_deterministic_pipeline_renders_math_diagram_not_prompt_card(tmp_path) -> None:
    prompt = "\u753b\u4e00\u4e2a\u5e73\u884c\u4e0e\u76f8\u4ea4\u7684\u56fe\u793a\uff0c\u9002\u5408\u521d\u4e2d\u751f\u7406\u89e3\u3002"
    pipeline = AnimationPipeline(
        RuntimeConfig(
            runs_dir=tmp_path,
            deterministic=True,
            trace_enabled=False,
        )
    )

    pipeline.generate(
        prompt=prompt,
        audience_level="middle_school",
        desired_duration=30,
        style="clean classroom",
        render=False,
    )

    run_dir = next(tmp_path.iterdir())
    generated_code = (run_dir / "generated_scene.py").read_text(encoding="utf-8")

    assert prompt not in generated_code
    assert "\u4f7f\u7528 AI \u6df1\u5ea6\u751f\u6210" not in generated_code
    assert "\u6570\u5b66\u52a8\u753b\u6559\u5b66" not in generated_code
    assert "Line(" in generated_code
    assert "NumberPlane" in generated_code
