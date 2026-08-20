"""Extended tests for math_to_manim.agents.base -- uncovered paths.

Covers: load_openai_agents_sdk (second try block / both fail),
maybe_run_sdk_agent (full execution path),
run_structured_sdk_agent (return None paths / third-party provider path),
mark_sdk_metadata (provenance annotation),
StageAgent.__init__ (None config),
StageAgent.invocation (additional metadata edge cases).
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pydantic

from math_to_manim.agents.base import (
    StageAgent,
    load_openai_agents_sdk,
    mark_sdk_metadata,
    maybe_run_sdk_agent,
    run_structured_sdk_agent,
)
from math_to_manim.config import RuntimeConfig

# ── Helpers ──────────────────────────────────────────────────────────


class _Artifact(pydantic.BaseModel):
    """Minimal Pydantic artifact for mark_sdk_metadata tests."""

    metadata: dict[str, Any] | None = None
    content: str = ""


class _SdkResult:
    """Fake Runner.run_sync result."""

    def __init__(self, final_output: Any) -> None:
        self.final_output = final_output


# ── Test: StageAgent.__init__ with None config ───────────────────────


class TestStageAgentInit:
    """Cover StageAgent.__init__ calling RuntimeConfig.from_env()."""

    def test_none_config_calls_from_env(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "test_stage"

            def run(self, value: str) -> str:
                return value

        agent = TestStage(config=None)
        assert isinstance(agent.config, RuntimeConfig)

    def test_default_config_is_from_env(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "test_stage"

            def run(self, value: str) -> str:
                return value

        agent = TestStage()
        assert isinstance(agent.config, RuntimeConfig)

    def test_config_passed_through(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "test_stage"

            def run(self, value: str) -> str:
                return value

        custom = RuntimeConfig(model="custom-model")
        agent = TestStage(config=custom)
        assert agent.config is custom
        assert agent.config.model == "custom-model"


# ── Test: StageAgent.invocation ──────────────────────────────────────


class TestStageAgentInvocation:
    """Cover StageAgent.invocation metadata recording edge cases."""

    def test_empty_metadata(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "empty_stage"

            def run(self, value: str) -> str:
                return value

        agent = TestStage(config=RuntimeConfig(model="gpt-4o"))
        inv = agent.invocation(used_sdk=True)
        assert inv.agent_name == "empty_stage"
        assert inv.model == "gpt-4o"
        assert inv.used_sdk is True
        assert inv.metadata == {}

    def test_multiple_metadata_fields(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "multi_stage"

            def run(self, value: str) -> str:
                return value

        agent = TestStage(config=RuntimeConfig(model="gpt-4o-mini"))
        inv = agent.invocation(used_sdk=False, stage="render", attempt=3, tags=["a", "b"])
        assert inv.agent_name == "multi_stage"
        assert inv.model == "gpt-4o-mini"
        assert inv.used_sdk is False
        assert inv.metadata["stage"] == "render"
        assert inv.metadata["attempt"] == 3
        assert inv.metadata["tags"] == ["a", "b"]

    def test_used_sdk_defaults_to_false(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "sdk_default"

            def run(self, value: str) -> str:
                return value

        agent = TestStage(config=RuntimeConfig(model="gpt-4o"))
        inv = agent.invocation()
        assert inv.used_sdk is False
        assert inv.metadata == {}


# ── Test: load_openai_agents_sdk ────────────────────────────────────


class TestLoadOpenaiAgentsSdk:
    """Cover lines 74-90: fallback second try block."""

    def test_both_tries_fail_returns_none(self) -> None:
        """Line 90: both import attempts fail."""
        with patch("builtins.__import__", side_effect=ImportError("mocked")):
            result = load_openai_agents_sdk()
            assert result is None

    def test_first_try_fails_second_succeeds(self) -> None:
        """Lines 77-89: top-level import fails, submodule imports succeed."""
        # Remove any cached agents modules to force the import path through our mocks
        saved: dict[str, Any] = {}
        for key in list(sys.modules):
            if key == "agents" or key.startswith("agents."):
                saved[key] = sys.modules.pop(key)

        try:
            # Mock agents package without top-level symbols
            agents_pkg = types.ModuleType("agents")
            agents_pkg.__path__ = ["/mock/agents"]
            agents_pkg.__package__ = "agents"
            agents_pkg.__file__ = "/mock/agents/__init__.py"
            agents_pkg.__spec__ = MagicMock()

            # Mock submodules with the expected symbols
            agent_mod = types.ModuleType("agents.agent")
            agent_mod.Agent = "SubmoduleAgent"
            agent_mod.__package__ = "agents"
            agent_mod.__file__ = "/mock/agents/agent.py"
            agent_mod.__spec__ = MagicMock()

            handoffs_mod = types.ModuleType("agents.handoffs")
            handoffs_mod.handoff = "SubmoduleHandoff"
            handoffs_mod.__package__ = "agents"
            handoffs_mod.__file__ = "/mock/agents/handoffs.py"
            handoffs_mod.__spec__ = MagicMock()

            run_mod = types.ModuleType("agents.run")
            run_mod.Runner = "SubmoduleRunner"
            run_mod.__package__ = "agents"
            run_mod.__file__ = "/mock/agents/run.py"
            run_mod.__spec__ = MagicMock()

            tool_mod = types.ModuleType("agents.tool")
            tool_mod.function_tool = "SubmoduleFunctionTool"
            tool_mod.__package__ = "agents"
            tool_mod.__file__ = "/mock/agents/tool.py"
            tool_mod.__spec__ = MagicMock()

            sys.modules["agents"] = agents_pkg
            sys.modules["agents.agent"] = agent_mod
            sys.modules["agents.handoffs"] = handoffs_mod
            sys.modules["agents.run"] = run_mod
            sys.modules["agents.tool"] = tool_mod

            result = load_openai_agents_sdk()
            assert result is not None
            assert result["Agent"] == "SubmoduleAgent"
            assert result["Runner"] == "SubmoduleRunner"
            assert result["function_tool"] == "SubmoduleFunctionTool"
            assert result["handoff"] == "SubmoduleHandoff"
        finally:
            # Clean up mock modules
            for key in list(sys.modules):
                if key == "agents" or key.startswith("agents."):
                    del sys.modules[key]
            # Restore saved modules
            sys.modules.update(saved)


# ── Test: maybe_run_sdk_agent ────────────────────────────────────────


class TestMaybeRunSdkAgent:
    """Cover lines 107-125: full execution path with SDK available."""

    @staticmethod
    def _make_mock_sdk() -> dict[str, Any]:
        return {
            "Agent": MagicMock(),
            "Runner": MagicMock(),
            "function_tool": MagicMock(),
            "handoff": MagicMock(),
        }

    def test_string_output(self) -> None:
        """Full path with string final_output (line 123 branch)."""
        mock_sdk = self._make_mock_sdk()
        mock_sdk["Runner"].run_sync.return_value = _SdkResult("parsed_result")

        output_parser = MagicMock(return_value="final_output")

        with (
            patch("math_to_manim.agents.base.load_env_file"),
            patch("math_to_manim.agents.base.os.getenv", return_value="sk-xxx"),
            patch("math_to_manim.agents.base._ensure_tracing_disabled"),
            patch(
                "math_to_manim.agents.base.load_openai_agents_sdk",
                return_value=mock_sdk,
            ),
            patch(
                "math_to_manim.agents.base._get_model_for_provider",
                return_value="gpt-4o",
            ),
        ):
            result = maybe_run_sdk_agent(
                name="test_agent",
                instructions="Do something",
                prompt="The prompt",
                model="gpt-4o",
                output_parser=output_parser,
            )

        assert result == "final_output"
        output_parser.assert_called_once_with("parsed_result")
        mock_sdk["Runner"].run_sync.assert_called_once()

    def test_non_string_output(self) -> None:
        """Full path with non-string final_output (line 124 branch: JSON dump)."""
        mock_sdk = self._make_mock_sdk()
        mock_sdk["Runner"].run_sync.return_value = _SdkResult({"key": "value"})

        output_parser = MagicMock(return_value="parsed")

        with (
            patch("math_to_manim.agents.base.load_env_file"),
            patch("math_to_manim.agents.base.os.getenv", return_value="sk-xxx"),
            patch("math_to_manim.agents.base._ensure_tracing_disabled"),
            patch(
                "math_to_manim.agents.base.load_openai_agents_sdk",
                return_value=mock_sdk,
            ),
            patch(
                "math_to_manim.agents.base._get_model_for_provider",
                return_value="gpt-4o",
            ),
        ):
            result = maybe_run_sdk_agent(
                name="test_agent",
                instructions="Do something",
                prompt="The prompt",
                model="gpt-4o",
                output_parser=output_parser,
            )

        assert result == "parsed"
        # Non-string output gets JSON-serialized before parsing
        output_parser.assert_called_once_with(json.dumps({"key": "value"}))

    def test_result_is_final_output_when_no_final_output_attr(self) -> None:
        """When result has no final_output, getattr returns the result itself."""
        mock_sdk = self._make_mock_sdk()
        mock_sdk["Runner"].run_sync.return_value = "raw_string_output"

        output_parser = MagicMock(return_value="parsed")

        with (
            patch("math_to_manim.agents.base.load_env_file"),
            patch("math_to_manim.agents.base.os.getenv", return_value="sk-xxx"),
            patch("math_to_manim.agents.base._ensure_tracing_disabled"),
            patch(
                "math_to_manim.agents.base.load_openai_agents_sdk",
                return_value=mock_sdk,
            ),
            patch(
                "math_to_manim.agents.base._get_model_for_provider",
                return_value="gpt-4o",
            ),
        ):
            result = maybe_run_sdk_agent(
                name="test_agent",
                instructions="Do something",
                prompt="The prompt",
                model="gpt-4o",
                output_parser=output_parser,
            )

        assert result == "parsed"
        output_parser.assert_called_once_with("raw_string_output")


# ── Test: run_structured_sdk_agent ───────────────────────────────────


class TestRunStructuredSdkAgent:
    """Cover lines 145, 151, 169-181."""

    def test_no_api_key_returns_none(self) -> None:
        """Line 145: return None when OPENAI_API_KEY is not set."""
        with patch("math_to_manim.agents.base.os.getenv", return_value=None):
            result = run_structured_sdk_agent(
                name="test",
                instructions="instr",
                prompt="prompt",
                model="gpt-4o",
                output_type=MagicMock,
            )
            assert result is None

    def test_no_sdk_returns_none(self) -> None:
        """Line 151: return None when SDK is not available."""
        with (
            patch("math_to_manim.agents.base.load_env_file"),
            patch("math_to_manim.agents.base.os.getenv", return_value="sk-xxx"),
            patch("math_to_manim.agents.base.load_openai_agents_sdk", return_value=None),
        ):
            result = run_structured_sdk_agent(
                name="test",
                instructions="instr",
                prompt="prompt",
                model="gpt-4o",
                output_type=MagicMock,
            )
            assert result is None

    def test_third_party_path_returns_value(self) -> None:
        """Lines 169-181: third-party provider path."""
        mock_result = MagicMock()

        with (
            patch("math_to_manim.agents.base.load_env_file"),
            patch("math_to_manim.agents.base.os.getenv", return_value="sk-xxx"),
            patch("math_to_manim.agents.base._ensure_tracing_disabled"),
            patch(
                "math_to_manim.agents.base.load_openai_agents_sdk",
                return_value={
                    "Agent": MagicMock(),
                    "Runner": MagicMock(),
                },
            ),
            patch(
                "math_to_manim.agents.base._get_model_for_provider",
                return_value="gpt-4o",
            ),
            patch(
                "math_to_manim.agents.base._is_third_party_provider",
                return_value=True,
            ),
            patch(
                "math_to_manim.agents.base.run_third_party_structured",
                return_value=mock_result,
            ),
        ):
            result = run_structured_sdk_agent(
                name="test_agent",
                instructions="Do something",
                prompt="The prompt",
                model="gpt-4o",
                output_type=MagicMock,
            )

        assert result is mock_result


# ── Test: mark_sdk_metadata ──────────────────────────────────────────


class TestMarkSdkMetadata:
    """Cover lines 184-195: provenance metadata annotation."""

    def test_adds_metadata_to_artifact_without_metadata(self) -> None:
        """Annotate an artifact whose metadata is None."""
        artifact = _Artifact(metadata=None, content="hello")
        result = mark_sdk_metadata(artifact, agent_name="render", model="gpt-4o")

        assert result.metadata["source_agent"] == "render"
        assert result.metadata["runtime"] == "openai_agents_sdk"
        assert result.metadata["model"] == "gpt-4o"

    def test_adds_metadata_to_artifact_with_existing_metadata(self) -> None:
        """Annotate an artifact that already has metadata; existing keys preserved."""
        artifact = _Artifact(metadata={"existing": "value"}, content="hello")
        result = mark_sdk_metadata(artifact, agent_name="plan", model="gpt-4o-mini")

        assert result.metadata["existing"] == "value"
        assert result.metadata["source_agent"] == "plan"
        assert result.metadata["runtime"] == "openai_agents_sdk"
        assert result.metadata["model"] == "gpt-4o-mini"

    def test_does_not_mutate_original_artifact(self) -> None:
        """mark_sdk_metadata returns a copy; original is not mutated."""
        orig_meta: dict[str, Any] = {"existing": "value"}
        artifact = _Artifact(metadata=orig_meta, content="hello")
        result = mark_sdk_metadata(artifact, agent_name="code", model="gpt-4o")

        # Original unchanged
        assert artifact.metadata == {"existing": "value"}
        assert "source_agent" not in (artifact.metadata or {})

        # Copy has new keys
        assert result.metadata["source_agent"] == "code"
        assert result.metadata["runtime"] == "openai_agents_sdk"
        assert result.metadata["model"] == "gpt-4o"
        assert result.metadata["existing"] == "value"

    def test_empty_metadata_dict(self) -> None:
        """Artifact with empty dict metadata is annotated correctly."""
        artifact = _Artifact(metadata={}, content="world")
        result = mark_sdk_metadata(artifact, agent_name="empty", model="gpt-4o")

        assert result.metadata["source_agent"] == "empty"
        assert result.metadata["runtime"] == "openai_agents_sdk"
        assert result.metadata["model"] == "gpt-4o"
