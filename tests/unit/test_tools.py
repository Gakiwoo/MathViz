from __future__ import annotations

import json
import subprocess
import sys

import pytest

from math_to_manim.rendering import extract_frame, make_contact_sheet, probe_video, render_manim_scene
from math_to_manim.review import (
    EvalCriterion,
    build_eval_prompt,
    parse_eval_score,
    score_video_metadata,
    weighted_score,
)
from math_to_manim.tools import (
    ArtifactStore,
    GraphCycleError,
    discover_scene_classes,
    find_primary_scene_class,
    normalize_graph,
    topological_sort,
    validate_python_source,
)


def test_normalize_graph_closes_dependencies_and_toposorts_deterministically() -> None:
    graph = {
        "render": ["scene", "assets", "scene"],
        "scene": ["plan"],
    }

    assert normalize_graph(graph) == {
        "assets": (),
        "plan": (),
        "render": ("assets", "scene"),
        "scene": ("plan",),
    }
    assert topological_sort(graph) == ["assets", "plan", "scene", "render"]


def test_topological_sort_reports_cycles() -> None:
    with pytest.raises(GraphCycleError) as exc_info:
        topological_sort({"a": ["b"], "b": ["a"]})

    assert exc_info.value.nodes == ("a", "b")


def test_artifact_store_writes_deterministic_manifest(tmp_path) -> None:
    store = ArtifactStore(tmp_path)

    artifact = store.put_text("hello", "../unsafe name.txt", kind="note", metadata={"n": 1})
    same = ArtifactStore(tmp_path).get(artifact.id)

    assert same is not None
    assert artifact.id == same.id
    assert artifact.path.read_text(encoding="utf-8") == "hello"
    assert artifact.path.name.endswith("unsafe_name.txt")
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))[artifact.id]["kind"] == "note"


def test_validate_python_source_accepts_scene_code_and_rejects_dangerous_code() -> None:
    valid = validate_python_source(
        "from manim import Scene\nclass Demo(Scene):\n    def construct(self):\n        pass\n"
    )
    invalid = validate_python_source("import os\nos.system('echo no')\n")
    syntax = validate_python_source("class Broken(:\n    pass\n")

    assert valid.ok
    assert not invalid.ok
    assert {issue.code for issue in invalid.errors} == {"forbidden-import", "forbidden-call"}
    assert not syntax.ok
    assert syntax.errors[0].code == "syntax-error"


def test_scene_discovery_uses_ast_without_importing_manim() -> None:
    source = """
class Helper:
    pass

class Opening(Scene):
    def construct(self):
        pass

class CameraMove(manim.ThreeDScene):
    pass
"""

    scenes = discover_scene_classes(source)

    assert [scene.name for scene in scenes] == ["Opening", "CameraMove"]
    assert scenes[0].has_construct is True
    assert scenes[1].bases == ("manim.ThreeDScene",)
    assert find_primary_scene_class(source).name == "Opening"


def test_optional_rendering_wrappers_skip_missing_binaries(tmp_path) -> None:
    scene_file = tmp_path / "scene.py"
    scene_file.write_text("from manim import Scene\n", encoding="utf-8")

    manim = render_manim_scene(scene_file, manim_bin="definitely-missing-manim-binary")
    probe = probe_video(tmp_path / "missing.mp4", ffprobe_bin="definitely-missing-ffprobe-binary")
    frame = extract_frame(
        tmp_path / "missing.mp4",
        tmp_path / "frame.png",
        ffmpeg_bin="definitely-missing-ffmpeg-binary",
    )
    sheet = make_contact_sheet(
        tmp_path / "missing.mp4",
        tmp_path / "contact_sheet.png",
        ffmpeg_bin="definitely-missing-ffmpeg-binary",
    )

    assert manim.skipped and not manim.ok
    assert probe.skipped and not probe.ok
    assert frame.skipped and not frame.ok
    assert sheet.skipped and not sheet.ok


@pytest.mark.skipif(sys.platform == "win32", reason="Unix shebang script is not a valid Windows executable")
def test_probe_video_falls_back_to_ffmpeg_metadata(tmp_path) -> None:
    video_file = tmp_path / "demo.mp4"
    video_file.write_bytes(b"placeholder")
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text(
        "#!/bin/sh\n"
        "cat >&2 <<'EOF'\n"
        "Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'demo.mp4':\n"
        "  Duration: 00:00:04.20, start: 0.000000, bitrate: 120 kb/s\n"
        "  Stream #0:0: Video: h264, yuv420p, 854x480, 15 fps\n"
        "EOF\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_ffmpeg.chmod(0o755)

    probe = probe_video(
        video_file,
        ffprobe_bin="definitely-missing-ffprobe-binary",
        ffmpeg_bin=str(fake_ffmpeg),
    )

    assert probe.ok
    assert probe.duration_seconds == pytest.approx(4.2)
    assert probe.width == 854
    assert probe.height == 480


def test_probe_video_decodes_utf8_metadata_with_non_ascii_paths(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from math_to_manim.rendering import ffmpeg as ffmpeg_module

    video_file = tmp_path / "demo.mp4"
    video_file.write_bytes(b"placeholder")
    raw = {
        "streams": [
            {
                "codec_type": "video",
                "duration": "11.4",
                "width": 854,
                "height": 480,
                "avg_frame_rate": "15/1",
                "nb_frames": "171",
            }
        ],
        "format": {"filename": "E:/中文路径/demo.mp4", "duration": "11.4"},
    }

    def fake_run(command, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(raw, ensure_ascii=False), stderr="")

    monkeypatch.setattr(ffmpeg_module, "resolve_binary", lambda binary: "ffprobe")
    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    probe = ffmpeg_module.probe_video(video_file)

    assert probe.ok
    assert probe.duration_seconds == pytest.approx(11.4)
    assert probe.width == 854
    assert probe.height == 480


def test_manim_render_skips_latex_required_scene_when_latex_missing(tmp_path) -> None:
    scene_file = tmp_path / "scene.py"
    scene_file.write_text(
        "from manim import *\n\nclass Demo(Scene):\n    def construct(self):\n        self.add(MathTex(r'x^2'))\n",
        encoding="utf-8",
    )
    fake_manim = tmp_path / "manim"
    fake_manim.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    fake_manim.chmod(0o755)

    result = render_manim_scene(
        scene_file,
        manim_bin=str(fake_manim),
        latex_bin="definitely-missing-latex-binary",
    )

    assert result.skipped and not result.ok
    assert result.returncode is None
    assert result.metadata["missing_tool"] == "latex"
    assert result.metadata["latex_required"] is True
    assert "LaTeX" in str(result.reason)


@pytest.mark.skipif(sys.platform == "win32", reason="subprocess cannot run a bare text file as executable on Windows")
def test_manim_render_does_not_return_partial_movie_on_failure(tmp_path) -> None:
    scene_file = tmp_path / "scene.py"
    scene_file.write_text(
        "from manim import Scene\nclass Demo(Scene):\n    def construct(self):\n        pass\n", encoding="utf-8"
    )
    media_dir = tmp_path / "media"
    partial_dir = media_dir / "videos" / "scene" / "480p15" / "partial_movie_files" / "Demo"
    partial_dir.mkdir(parents=True)
    partial = partial_dir / "partial.mp4"
    partial.write_bytes(b"not a final render")
    fake_manim = tmp_path / "manim"
    fake_manim.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_manim.chmod(0o755)

    result = render_manim_scene(scene_file, scene_name="Demo", output_dir=media_dir, manim_bin=str(fake_manim))

    assert not result.ok
    assert result.returncode == 1
    assert result.output_path is None


def test_manim_binary_resolves_next_to_python_interpreter(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from math_to_manim.rendering import manim as manim_module

    bin_dir = tmp_path / "venv" / "Scripts"
    bin_dir.mkdir(parents=True)
    fake_manim = bin_dir / "m2m2-test-resolve.exe"
    fake_manim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    monkeypatch.setattr(manim_module.sys, "executable", str(bin_dir / "python.exe"))
    monkeypatch.setattr(manim_module.sys, "prefix", str(tmp_path / "venv"))

    assert manim_module._resolve_tool_binary("m2m2-test-resolve") == str(fake_manim)


def test_video_scoring_is_weighted_and_deterministic() -> None:
    good = score_video_metadata(duration_seconds=2.0, width=1280, height=720, file_size_bytes=10)
    weak = score_video_metadata(duration_seconds=0.25, width=320, height=180, file_size_bytes=0)

    assert good.score == pytest.approx(1.0)
    assert good.passed
    assert weak.score < good.score
    assert not weak.passed


def test_eval_prompt_helpers_parse_json_and_weight_scores() -> None:
    prompt = build_eval_prompt(
        criteria=[EvalCriterion("Accuracy", "Matches the requested math.", 2.0), "Visual clarity"],
        reference="Show x^2.",
        candidate="A parabola animation.",
    )
    parsed = parse_eval_score('{"score": 4, "max_score": 5, "explanation": "clear"}')

    assert "Accuracy (weight 2)" in prompt
    assert "Candidate:\n\nA parabola animation." in prompt
    assert parsed.ok
    assert parsed.normalized_score == pytest.approx(0.8)
    assert weighted_score([parsed, 1.0], weights=[1.0, 3.0]) == pytest.approx(0.95)
