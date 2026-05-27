"""Run bundle summaries and local render helpers for the teacher console."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from math_to_manim.agents import RenderAgent, StaticReviewAgent, VideoReviewAgent
from math_to_manim.agents.codegen import write_generated_code
from math_to_manim.config import RuntimeConfig
from math_to_manim.pipeline.runner import save_json
from math_to_manim.rendering.commands import resolve_binary
from math_to_manim.schemas import GeneratedCode, RenderResult
from math_to_manim.tools.manim_fixes import fix_manim_common_issues, preview_safe_generated_code


def _latex_help_text() -> str:
    """Return platform-appropriate LaTeX installation advice."""
    if platform.system() == "Windows":
        return "Install MiKTeX: winget install MiKTeX.MiKTeX"
    if platform.system() == "Darwin":
        return "Install MacTeX, BasicTeX, or TeX Live."
    return "Install TeX Live: sudo apt-get install texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended dvisvgm"


def safe_run_dir(runs_dir: Path, run_id: str) -> Path | None:
    runs_root = runs_dir.resolve()
    candidate = (runs_root / run_id).resolve()
    try:
        candidate.relative_to(runs_root)
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def summarize_run(run_dir: Path) -> dict[str, Any]:
    request = _read_json(run_dir / "request.json")
    curriculum = _read_json(run_dir / "curriculum.json")
    graph = _read_json(run_dir / "knowledge_graph.json")
    storyboard = _read_json(run_dir / "storyboard.json")
    generated = _read_json(run_dir / "generated_code.json")
    validation = _read_json(run_dir / "validation_report.json")
    render = _read_json(run_dir / "render_result.json")
    review = _read_json(run_dir / "review_report.json")
    manifest = _read_json(run_dir / "manifest.json")

    run_id = run_dir.name
    output_path = render.get("output_path")
    integrity_passed = (review.get("metadata") or {}).get("render_integrity_passed")
    has_video = bool(
        output_path
        and Path(output_path).exists()
        and render.get("status") == "succeeded"
        and integrity_passed is not False
    )
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_at": manifest.get("created_at"),
        "prompt": request.get("prompt", ""),
        "request": {
            "audience_level": request.get("target_audience"),
            "desired_duration": request.get("duration_seconds"),
            "style": request.get("style"),
        },
        "scene_name": generated.get("scene_name"),
        "status": {
            "validation": validation.get("status"),
            "render": render.get("status"),
            "review_score": review.get("score"),
        },
        "video_url": f"/api/runs/{run_id}/video" if has_video else None,
        "video_path": output_path if has_video else None,
        "error": _error_summary(validation, render, review),
        "sections": {
            "teaching_plan": _format_curriculum(curriculum),
            "knowledge_graph": _format_graph(graph),
            "storyboard": _format_storyboard(storyboard),
            "manim_code": generated.get("code", ""),
            "run_bundle": _format_bundle(run_dir, manifest),
        },
        "artifacts": _artifact_paths(run_dir),
    }


def list_runs(runs_dir: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    if not runs_dir.exists():
        return []
    run_dirs = sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)
    return [summarize_run(path) for path in run_dirs[:limit]]


def _check_latex_compiles(latex_bin_name: str = "latex") -> dict[str, Any]:
    """Check optional LaTeX tools without triggering MiKTeX first-run installs."""
    latex_bin = _resolve_binary(latex_bin_name)
    dvisvgm_bin = _resolve_binary("dvisvgm")
    if not latex_bin:
        return {"available": False, "error": "latex binary not found", "help": _latex_help_text()}
    if not dvisvgm_bin:
        return {
            "available": False,
            "error": "dvisvgm not found",
            "help": _latex_help_text(),
        }

    return {"available": True}


def check_render_health(
    manim_bin: str = "manim",
    ffmpeg_bin: str = "ffmpeg",
    latex_bin: str = "latex",
) -> dict[str, Any]:
    latex_ok = _check_latex_compiles(latex_bin)
    latex_path = _resolve_binary(latex_bin)
    dvisvgm_path = _resolve_binary("dvisvgm")
    latex_available = latex_path is not None
    dvisvgm_available = dvisvgm_path is not None
    tools = {
        "manim": _tool_status(
            manim_bin,
            'Run ./scripts/bootstrap-render-macos.sh on macOS, .\\scripts\\bootstrap-render-windows.ps1 on Windows, or python -m pip install -e ".[render]" after system graphics libraries are installed.',
            required=True,
        ),
        "ffmpeg": _tool_status(ffmpeg_bin, "Install FFmpeg or use the platform bootstrap script.", required=True),
        "latex": {
            "binary": "latex",
            "available": latex_available,
            "path": latex_path,
            "help": latex_ok.get("help", _latex_help_text()),
            "required": False,
            "detail": "" if latex_available else latex_ok.get("error", ""),
        },
        "dvisvgm": {
            "binary": "dvisvgm",
            "available": dvisvgm_available,
            "path": dvisvgm_path,
            "help": "" if dvisvgm_available else (latex_ok.get("help", _latex_help_text())),
            "required": False,
        },
    }
    missing = [name for name, status in tools.items() if not status["available"]]
    blocking_missing = [name for name, status in tools.items() if status["required"] and not status["available"]]
    optional_missing = [name for name, status in tools.items() if not status["required"] and not status["available"]]
    return {
        "ready": not blocking_missing,
        "missing": missing,
        "blocking_missing": blocking_missing,
        "optional_missing": optional_missing,
        "tools": tools,
        "install_commands": [
            'python -m pip install -e ".[render]"',
            "./scripts/bootstrap-render-macos.sh",
            "./scripts/bootstrap-render.sh",
            ".\\scripts\\bootstrap-render-windows.ps1",
        ],
    }


def render_existing_run(run_dir: Path, config: RuntimeConfig) -> dict[str, Any]:
    try:
        generated_payload = _read_json(run_dir / "generated_code.json")
        generated = GeneratedCode.model_validate(generated_payload)
        # Fix common Manim API issues before rendering (includes Tex→Text fallback)
        generated = fix_manim_common_issues(generated)
        generated = preview_safe_generated_code(generated)
        save_json(run_dir / "generated_code.json", generated.to_public_dict())
        code_path = write_generated_code(generated, run_dir)

        validation = StaticReviewAgent(config).run((generated, code_path))
        save_json(run_dir / "validation_report.json", validation.to_public_dict())

        if validation.is_successful:
            render_result = RenderAgent(config).run((generated, code_path, config.default_quality))
        else:
            render_result = RenderResult(
                status="failed",
                scene_name=generated.scene_name,
                output_path=None,
                command=[],
                stdout="",
                stderr="static validation did not pass",
                validation_report=validation,
                metadata={"skipped": True, "reason": "static_validation_failed"},
            )
        save_json(run_dir / "render_result.json", render_result.to_public_dict())

        review = VideoReviewAgent(config).run(render_result)
        save_json(run_dir / "review_report.json", review.to_public_dict())
        return summarize_run(run_dir)
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        print(f"[render_existing_run] CRASH: {exc}\n{tb}", flush=True)
        # Write a minimal render_result so the run is not left in limbo
        save_json(
            run_dir / "render_result.json",
            {
                "status": "failed",
                "scene_name": "",
                "output_path": None,
                "command": [],
                "stdout": "",
                "stderr": f"render_existing_run crashed: {exc}",
                "metadata": {"crashed": True, "error": str(exc)[:500]},
            },
        )
        return {
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "status": {"validation": "unknown", "render": "failed", "review_score": None},
            "video_url": None,
            "error": {"stage": "render", "message": f"内部错误：{exc}", "details": tb[-1200:]},
            "sections": {
                "teaching_plan": "",
                "knowledge_graph": "",
                "storyboard": "",
                "manim_code": "",
                "run_bundle": "",
            },
        }


def _error_summary(
    validation: dict[str, Any], render: dict[str, Any], review: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if validation.get("status") == "failed":
        return {
            "stage": "static_validation",
            "message": validation.get("summary") or "Static validation failed.",
            "details": validation.get("issues") or [],
        }
    review = review or {}
    if (review.get("metadata") or {}).get("render_integrity_passed") is False:
        observations = review.get("observations") or []
        return {
            "stage": "video_review",
            "message": "低清预览视频过短或不完整，未作为有效预览展示。",
            "details": "\n".join(str(item) for item in observations),
        }
    if render.get("status") == "failed" and not render.get("metadata", {}).get("skipped"):
        stderr = str(render.get("stderr") or "")
        return {
            "stage": "render",
            "message": "Manim render failed.",
            "details": stderr[-1200:],
        }
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _resolve_binary(name: str) -> str | None:
    return resolve_binary(name)


def _tool_status(binary: str, help_text: str, *, required: bool = False) -> dict[str, Any]:
    resolved = resolve_binary(binary)
    return {
        "binary": binary,
        "available": resolved is not None,
        "path": resolved,
        "help": help_text if resolved is None else "",
        "required": required,
        "detail": "" if resolved else f"{binary} not found on PATH",
    }


def _read_artifact(run_dir: Path, name: str) -> dict[str, Any]:
    return _read_json(run_dir / f"{name}.json")


def _format_curriculum(curriculum: dict[str, Any]) -> str:
    objectives = curriculum.get("learning_objectives", [])
    modules = curriculum.get("modules", [])
    lines = [f"# {curriculum.get('title', 'Untitled')}"]
    if objectives:
        lines.append("## Objectives")
        lines.extend(f"- {obj}" for obj in objectives)
    for module in modules:
        title = module.get("title", module.get("module_title", "Module"))
        lines.append(f"## {title}")
        steps = module.get("steps", module.get("learning_steps", []))
        for step in steps:
            desc = step.get("description", step.get("step_description", ""))
            if desc:
                lines.append(f"- {desc}")
    return "\n".join(lines)


def _format_graph(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", graph.get("concepts", []))
    edges = graph.get("edges", graph.get("relations", []))
    lines = ["## Knowledge Graph"]
    for node in nodes:
        label = node.get("label", node.get("name", node.get("id", "?")))
        lines.append(f"- {label}")
    for edge in edges:
        src = edge.get("source", edge.get("from", ""))
        dst = edge.get("target", edge.get("to", ""))
        rel = edge.get("relation", edge.get("label", "related_to"))
        lines.append(f"  {src} -- {rel} --> {dst}")
    return "\n".join(lines)


def _format_storyboard(storyboard: dict[str, Any]) -> str:
    scenes = storyboard.get("scenes", [])
    lines = [f"# {storyboard.get('title', 'Storyboard')}"]
    for i, scene in enumerate(scenes, 1):
        title = scene.get("title", f"Scene {i}")
        narration = scene.get("narration", "")
        actions = scene.get("visual_actions", [])
        lines.append(f"## {i}. {title}")
        if narration:
            lines.append(f"   {narration}")
        for action in actions:
            lines.append(f"   - {action}")
    return "\n".join(lines)


def _format_bundle(run_dir: Path, manifest: dict[str, Any]) -> str:
    artifacts = manifest.get("artifacts", [])
    lines = [f"Run directory: {run_dir}"]
    lines.append(f"Artifacts ({len(artifacts)}):")
    for name in artifacts:
        fpath = run_dir / f"{name}.json"
        size = fpath.stat().st_size if fpath.exists() else 0
        lines.append(f"  - {name}.json ({size} bytes)")
    return "\n".join(lines)


def _artifact_paths(run_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in ("request", "curriculum", "generated_code", "render_result", "review_report", "manifest"):
        path = run_dir / f"{key}.json"
        if path.exists():
            result[key] = str(path)
    return result


# -- Restage support -----------------------------------------------------------

_STAGE_AGENTS: dict[str, tuple[str, str]] = {
    "intent": ("IntentAgent", "UserRequest"),
    "knowledge_graph": ("PrerequisiteGraphAgent", "ConceptIntent"),
    "curriculum": ("CurriculumAgent", "KnowledgeGraph"),
    "math_packet": ("MathAgent", "CurriculumPlan"),
    "storyboard": ("StoryboardAgent", "MathPacket"),
    "scene_spec": ("SceneSpecAgent", "VisualStoryboard"),
    "codegen": ("ManimCodeAgent", "ManimSceneSpec"),
}


def restage_run(run_dir: Path, config: RuntimeConfig, stage: str) -> dict[str, Any]:
    """Re-run a single pipeline stage for an existing run."""

    if stage not in _STAGE_AGENTS:
        valid = sorted(_STAGE_AGENTS)
        return {"error": f"Unknown stage {stage!r}. Valid stages: {', '.join(valid)}"}

    agent_cls_name, input_cls_name = _STAGE_AGENTS[stage]
    agent_cls = locals()[agent_cls_name]
    input_cls = locals()[input_cls_name]

    input_artifact = _read_artifact(run_dir, _input_artifact_for(stage))
    if not input_artifact:
        return {"error": f"Missing input artifact for stage {stage!r}"}

    parsed_input = input_cls.model_validate(input_artifact)
    agent = agent_cls(config)
    result = agent.run(parsed_input)
    save_json(run_dir / f"{stage}.json", result.to_public_dict())
    return {
        "stage": stage,
        "status": "ok",
        "run_dir": str(run_dir),
    }


def _input_artifact_for(stage: str) -> str:
    mapping = {
        "intent": "request",
        "knowledge_graph": "intent",
        "curriculum": "knowledge_graph",
        "math_packet": "curriculum",
        "storyboard": "math_packet",
        "scene_spec": "storyboard",
        "codegen": "scene_spec",
    }
    return mapping.get(stage, stage)
