"""Extended unit tests for CodexCliProvider covering uncovered paths.

Coverage targets (from codex_cli.py):
  - repair_code() method  (lines 50-64)
  - FileNotFoundError in _run_codex  (lines 80-81)
  - Non-zero returncode in _run_codex  (line 85)
  - ValidationError in _parse_generated_code  (lines 98-99)
  - _build_repair_prompt()  (line 121)
  - _extract_json_object() markdown fence stripping  (lines 140-143)
  - _extract_json_object() fallback extraction  (lines 146-151)
  - _extract_json_object() non-dict result  (line 153)
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from math_to_manim.config import RuntimeConfig
from math_to_manim.schemas import GeneratedCode, ManimSceneSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeRunner:
    """Simulates subprocess.run for a given payload dict."""

    def __init__(self, payload: dict[str, object], returncode: int = 0):
        self.payload = payload
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            self.returncode,
            stdout=json.dumps(self.payload),
            stderr="",
        )


def _make_spec(scene_name: str = "DemoScene") -> ManimSceneSpec:
    return ManimSceneSpec(scene_name=scene_name, code_requirements=["show a dot"])


def _make_generated(scene_name: str = "DemoScene") -> GeneratedCode:
    return GeneratedCode(
        scene_name=scene_name,
        code="from manim import *\nclass DemoScene(Scene):\n    def construct(self): pass\n",
        dependencies=["manim"],
        metadata={"file_path": "generated_scene.py"},
    )


VALID_PAYLOAD = {
    "scene_name": "DemoScene",
    "code": "from manim import *\nclass DemoScene(Scene):\n    def construct(self): pass\n",
    "dependencies": ["manim"],
    "metadata": {"note": "fake codex"},
}


# ===================================================================
# 1. repair_code() method  (lines 50-64)
# ===================================================================


class TestRepairCode:
    """Coverage for CodexCliProvider.repair_code()."""

    def test_repair_code_success(self):
        """Repair flow produces correct metadata and calls through."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)
        spec = _make_spec()
        generated = _make_generated()

        repaired = provider.repair_code(spec, generated, failure="NameError: x not defined")

        assert repaired.scene_name == "DemoScene"
        assert repaired.metadata["runtime"] == "codex_cli"
        assert repaired.metadata["provider"] == "codex-cli"
        assert repaired.metadata["source_agent"] == "repair"
        assert repaired.metadata["repair_of"] == "DemoScene"
        assert repaired.metadata["file_path"] == "generated_scene.py"
        # The prompt sent to the runner should mention "repair"
        assert len(runner.calls) == 1
        prompt = runner.calls[0][-1]  # last element is the prompt
        assert "repair" in prompt.lower()

    def test_repair_code_fallback_file_path(self):
        """When generated.metadata lacks file_path, default is used."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)
        spec = _make_spec()
        generated = GeneratedCode(
            scene_name="NoPathScene",
            code="...",
            dependencies=[],
            metadata={},
        )

        repaired = provider.repair_code(spec, generated, failure="err")

        assert repaired.metadata["file_path"] == "generated_scene.py"

    def test_repair_code_preserves_existing_file_path(self):
        """When generated.metadata has file_path, it is preserved."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)
        spec = _make_spec()
        generated = GeneratedCode(
            scene_name="CustomPathScene",
            code="...",
            dependencies=[],
            metadata={"file_path": "custom/scene.py"},
        )

        repaired = provider.repair_code(spec, generated, failure="err")

        assert repaired.metadata["file_path"] == "custom/scene.py"

    def test_repair_code_metadata_merges_existing(self):
        """Existing metadata from the LLM response is merged into repair output."""
        payload_with_extra = {**VALID_PAYLOAD, "metadata": {"llm_note": "original"}}
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(payload_with_extra)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)
        spec = _make_spec()
        generated = _make_generated()

        repaired = provider.repair_code(spec, generated, failure="err")

        assert repaired.metadata["llm_note"] == "original"
        assert repaired.metadata["source_agent"] == "repair"


# ===================================================================
# 2. FileNotFoundError handling in _run_codex  (lines 80-81)
# ===================================================================


class TestRunCodexFileNotFound:
    """Coverage for the FileNotFoundError branch."""

    def test_file_not_found_raises_runtime_error(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        def failing_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("codex not found")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_command="nonexistent"),
            runner=failing_runner,
        )
        with pytest.raises(RuntimeError, match="Codex CLI command not found"):
            provider._run_codex("some prompt")

    def test_file_not_found_through_generate_code(self):
        """FileNotFoundError surfaces through the public generate_code method."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        def failing_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("no such file or directory: 'codex'")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_command="codex"),
            runner=failing_runner,
        )
        with pytest.raises(RuntimeError, match="Codex CLI command not found"):
            provider.generate_code(_make_spec())

    def test_file_not_found_through_repair_code(self):
        """FileNotFoundError surfaces through the public repair_code method."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        def failing_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("codex not found")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_command="codex"),
            runner=failing_runner,
        )
        with pytest.raises(RuntimeError, match="Codex CLI command not found"):
            provider.repair_code(_make_spec(), _make_generated(), failure="err")


# ===================================================================
# 3. Non-zero returncode in _run_codex  (line 85)
# ===================================================================


class TestRunCodexNonZeroReturn:
    """Coverage for the completed.returncode != 0 branch."""

    def test_nonzero_returncode_raises_runtime_error(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        class FailRunner:
            def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(cmd, 1, stdout="some output", stderr="error info")

        provider = CodexCliProvider(config=RuntimeConfig(), runner=FailRunner())
        with pytest.raises(RuntimeError, match="Codex CLI generation failed"):
            provider._run_codex("prompt")

    def test_nonzero_returncode_through_generate_code(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        class FailRunner:
            def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="boom")

        provider = CodexCliProvider(config=RuntimeConfig(), runner=FailRunner())
        with pytest.raises(RuntimeError, match="Codex CLI generation failed"):
            provider.generate_code(_make_spec())

    def test_nonzero_returncode_through_repair_code(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        class FailRunner:
            def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="repair failure")

        provider = CodexCliProvider(config=RuntimeConfig(), runner=FailRunner())
        with pytest.raises(RuntimeError, match="Codex CLI generation failed"):
            provider.repair_code(_make_spec(), _make_generated(), failure="err")


# ===================================================================
# 4. ValidationError in _parse_generated_code  (lines 98-99)
# ===================================================================


class TestParseGeneratedCodeValidationError:
    """Coverage for the ValidationError branch in _parse_generated_code."""

    def test_validation_error_raises_runtime_error(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        # Valid JSON but missing required field 'scene_name'
        invalid_payload = json.dumps({"code": "missing scene_name"})
        with patch.object(CodexCliProvider, "_run_codex", return_value=invalid_payload):
            provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
            with pytest.raises(RuntimeError, match="Codex CLI returned JSON that did not match GeneratedCode"):
                provider.generate_code(_make_spec())

    def test_validation_error_invalid_type_for_field(self):
        """scene_name must be a string; sending a number triggers ValidationError."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        payload = json.dumps(
            {
                "scene_name": 42,
                "code": "from manim import *\nclass S(Scene): pass\n",
                "dependencies": [],
                "metadata": {},
            }
        )
        with patch.object(CodexCliProvider, "_run_codex", return_value=payload):
            provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
            with pytest.raises(RuntimeError, match="Codex CLI returned JSON that did not match GeneratedCode"):
                provider.generate_code(_make_spec())

    def test_validation_error_through_repair_code(self):
        """ValidationError from LLM output is caught in repair_code too."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        invalid_payload = json.dumps({"code": "only code"})
        with patch.object(CodexCliProvider, "_run_codex", return_value=invalid_payload):
            provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
            with pytest.raises(RuntimeError, match="Codex CLI returned JSON that did not match GeneratedCode"):
                provider.repair_code(_make_spec(), _make_generated(), failure="err")


# ===================================================================
# 5. _build_repair_prompt()  (line 121)
# ===================================================================


class TestBuildRepairPrompt:
    """Coverage for the _build_repair_prompt method."""

    def test_repair_prompt_includes_failure(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
        spec = _make_spec("RepairScene")
        generated = _make_generated("RepairScene")
        failure_text = "ZeroDivisionError: division by zero"

        prompt = provider._build_repair_prompt(spec, generated, failure_text)

        assert "Repair" in prompt
        assert "repair" in prompt.lower()
        assert failure_text in prompt
        assert "RepairScene" in prompt
        assert "ZeroDivisionError" in prompt

    def test_repair_prompt_contains_failure_truncated(self):
        """Only the last 8000 chars of failure are included."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
        long_failure = "A" * 10_000
        prompt = provider._build_repair_prompt(_make_spec(), _make_generated(), long_failure)

        assert "A" * 8000 in prompt
        # The remaining 2000 chars are truncated
        assert len(long_failure) > 8000

    def test_repair_prompt_contains_generated_code(self):
        from math_to_manim.providers.codex_cli import CodexCliProvider

        provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
        spec = _make_spec()
        generated = _make_generated()
        prompt = provider._build_repair_prompt(spec, generated, "error")

        assert "scene_spec" in prompt
        assert "generated_code" in prompt
        assert "failure" in prompt
        assert generated.to_public_dict()["scene_name"] in prompt


# ===================================================================
# 6. _extract_json_object()  (lines 140-143)
# ===================================================================


class TestExtractJsonObjectMarkdownCodeFence:
    """Coverage for markdown code fence stripping in _extract_json_object."""

    def test_code_fence_with_json_lang(self):
        """```json ... ``` fence is stripped."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = '```json\n{"scene_name": "S", "code": "..."}\n```'
        result = _extract_json_object(text)
        assert result == {"scene_name": "S", "code": "..."}

    def test_code_fence_without_lang(self):
        """``` ... ``` fence (no language tag) is stripped."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = '```\n{"key": "value"}\n```'
        result = _extract_json_object(text)
        assert result == {"key": "value"}

    def test_code_fence_with_trailing_content(self):
        """Extra whitespace after stripping fence is handled."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = '  ```json   \n  {"a": 1}\n  ```  '
        result = _extract_json_object(text)
        assert result == {"a": 1}

    def test_extra_text_after_fence_fallback(self):
        """When extra text appears after the closing fence, fallback extraction still succeeds."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = '```json\n{"key": "value"}\n```\nSome explanation after the code block.'
        result = _extract_json_object(text)
        assert result == {"key": "value"}


# ===================================================================
# 7. _extract_json_object() fallback extraction  (lines 146-151)
# ===================================================================


class TestExtractJsonObjectFallback:
    """Coverage for JSON decode failure and fallback to {{ ... }} extraction."""

    def test_fallback_extraction_from_surrounding_text(self):
        """When initial json.loads fails, fallback extracts first { ... } block."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = 'Here is the result:\n{"scene_name": "Fallback", "code": "..."}\nEnd.'
        result = _extract_json_object(text)
        assert result == {"scene_name": "Fallback", "code": "..."}

    def test_fallback_with_multiline_object(self):
        """Fallback works with multi-line JSON objects."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        text = 'Explanation...\n{\n  "scene_name": "Multi",\n  "code": "line1\\nline2"\n}\nMore text.'
        result = _extract_json_object(text)
        assert result == {"scene_name": "Multi", "code": "line1\nline2"}

    def test_fallback_raises_when_no_braces(self):
        """Fallback raises RuntimeError if no { } braces found."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI did not return a JSON object"):
            _extract_json_object("just plain text without braces")

    def test_fallback_raises_when_braces_incomplete(self):
        """Fallback raises RuntimeError if start > end (malformed braces)."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI did not return a JSON object"):
            _extract_json_object("some text { only opening brace")

    def test_fallback_raises_when_end_before_start(self):
        """Fallback raises RuntimeError if } appears before {."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI did not return a JSON object"):
            _extract_json_object("some text } brace then later { again")


# ===================================================================
# 8. _extract_json_object() non-dict result  (line 153)
# ===================================================================


class TestExtractJsonObjectNonDict:
    """Coverage for the isinstance(parsed, dict) check."""

    def test_parsed_list_raises(self):
        """A JSON array raises RuntimeError."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI returned JSON, but it was not an object"):
            _extract_json_object("[1, 2, 3]")

    def test_parsed_string_raises(self):
        """A plain JSON string raises RuntimeError."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI returned JSON, but it was not an object"):
            _extract_json_object('"just a string"')

    def test_parsed_number_raises(self):
        """A JSON number raises RuntimeError."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI returned JSON, but it was not an object"):
            _extract_json_object("42")

    def test_parsed_null_raises(self):
        """JSON null raises RuntimeError."""
        from math_to_manim.providers.codex_cli import _extract_json_object

        with pytest.raises(RuntimeError, match="Codex CLI returned JSON, but it was not an object"):
            _extract_json_object("null")


# ===================================================================
# 9. generate_code() edge cases with mock runner
# ===================================================================


class TestGenerateCodeEdgeCases:
    """Additional generate_code() scenarios."""

    def test_generate_code_with_full_auto_flag(self):
        """When codex_full_auto is True, --full-auto is passed to runner."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(
            config=RuntimeConfig(codex_full_auto=True),
            runner=runner,
        )

        provider.generate_code(_make_spec())

        assert len(runner.calls) == 1
        assert "--full-auto" in runner.calls[0]

    def test_generate_code_without_full_auto(self):
        """When codex_full_auto is False, --full-auto is NOT passed."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(
            config=RuntimeConfig(codex_full_auto=False),
            runner=runner,
        )

        provider.generate_code(_make_spec())

        assert len(runner.calls) == 1
        assert "--full-auto" not in runner.calls[0]

    def test_generate_code_passes_workdir_when_set(self):
        """When codex_workdir is set, cwd is passed to runner."""
        from pathlib import Path

        from math_to_manim.providers.codex_cli import CodexCliProvider

        calls: list[dict[str, object]] = []

        def capture_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(VALID_PAYLOAD), stderr="")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_workdir=Path("/tmp/codex_work")),
            runner=capture_runner,
        )

        provider.generate_code(_make_spec())

        assert len(calls) == 1
        assert calls[0]["cwd"] == "/tmp/codex_work"

    def test_generate_code_no_workdir(self):
        """When codex_workdir is None, cwd is None."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        calls: list[dict[str, object]] = []

        def capture_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(VALID_PAYLOAD), stderr="")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_workdir=None),
            runner=capture_runner,
        )

        provider.generate_code(_make_spec())

        assert len(calls) == 1
        assert calls[0].get("cwd") is None

    def test_generate_code_sets_timeout_from_config(self):
        """The timeout kwarg is passed from config."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        calls: list[dict[str, object]] = []

        def capture_runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(VALID_PAYLOAD), stderr="")

        provider = CodexCliProvider(
            config=RuntimeConfig(codex_timeout_seconds=300.0),
            runner=capture_runner,
        )

        provider.generate_code(_make_spec())

        assert len(calls) == 1
        assert calls[0]["timeout"] == 300.0

    def test_generate_code_propagates_custom_codex_command(self):
        """The codex_command config value is used as the command."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(
            config=RuntimeConfig(codex_command="my-codex"),
            runner=runner,
        )

        provider.generate_code(_make_spec())

        assert len(runner.calls) == 1
        assert runner.calls[0][0] == "my-codex"

    def test_generate_code_with_markdown_code_fence_output(self):
        """When LLM wraps JSON in ```json ... ```, it's handled."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        fence_output = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
        with patch.object(CodexCliProvider, "_run_codex", return_value=fence_output):
            provider = CodexCliProvider(config=RuntimeConfig(), runner=lambda *a, **kw: None)
            generated = provider.generate_code(_make_spec())
            assert generated.scene_name == "DemoScene"

    def test_generate_code_with_extra_metadata(self):
        """LLM-supplied metadata is merged with the standard fields."""
        payload_with_extra = {
            **VALID_PAYLOAD,
            "metadata": {"custom_tag": "hello", "original_key": "keep"},
        }
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(payload_with_extra)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)

        generated = provider.generate_code(_make_spec())

        assert generated.metadata["custom_tag"] == "hello"
        assert generated.metadata["original_key"] == "keep"
        assert generated.metadata["runtime"] == "codex_cli"
        assert generated.metadata["provider"] == "codex-cli"

    def test_codex_full_auto_true_adds_flag(self):
        """_run_codex includes --full-auto when config has it set."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        class CaptureRunner:
            def __init__(self):
                self.cmd = None

            def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.cmd = cmd
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(VALID_PAYLOAD), stderr="")

        cap = CaptureRunner()
        provider = CodexCliProvider(
            config=RuntimeConfig(codex_full_auto=True),
            runner=cap,
        )
        provider._run_codex("some prompt")
        assert "--full-auto" in cap.cmd
        assert cap.cmd[-1] == "some prompt"

    def test_repair_code_with_empty_failure(self):
        """Empty failure string is handled without crash."""
        from math_to_manim.providers.codex_cli import CodexCliProvider

        runner = FakeRunner(VALID_PAYLOAD)
        provider = CodexCliProvider(config=RuntimeConfig(), runner=runner)

        repaired = provider.repair_code(_make_spec(), _make_generated(), failure="")

        assert repaired.scene_name == "DemoScene"
        assert repaired.metadata["source_agent"] == "repair"
