"""Tests for math_to_manim.agents.base — SDK-agnostic pure functions."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from math_to_manim.agents.base import (
    AgentInvocation,
    StageAgent,
)
from math_to_manim.config import RuntimeConfig
from math_to_manim.providers.llm_helpers import (
    _is_third_party_provider,
    _repair_truncated_json,
    _strip_nulls,
    _summarize_schema_props,
)


class TestAgentInvocation:
    def test_basic_fields(self) -> None:
        inv = AgentInvocation(agent_name="test", model="gpt-4", used_sdk=True)
        assert inv.agent_name == "test"
        assert inv.model == "gpt-4"
        assert inv.used_sdk is True
        assert inv.metadata == {}

    def test_with_metadata(self) -> None:
        inv = AgentInvocation(agent_name="a", model="m", used_sdk=False, metadata={"key": "val"})
        assert inv.metadata["key"] == "val"

    def test_dataclass_serializable(self) -> None:
        inv = AgentInvocation(agent_name="x", model="y", used_sdk=True)
        d = asdict(inv)
        assert d["agent_name"] == "x"
        assert d["model"] == "y"
        assert d["used_sdk"] is True
        json.dumps(d)  # should not raise


class TestStageAgent:
    def test_invocation_returns_agent_invocation(self) -> None:
        class TestStage(StageAgent[str, str]):
            name = "test_stage"

            def run(self, value: str) -> str:
                return value

        config = RuntimeConfig(model="test-model")
        agent = TestStage(config=config)
        inv = agent.invocation(used_sdk=True, extra="info")
        assert isinstance(inv, AgentInvocation)
        assert inv.agent_name == "test_stage"
        assert inv.model == "test-model"
        assert inv.used_sdk is True
        assert inv.metadata.get("extra") == "info"

    def test_run_raises_not_implemented(self) -> None:
        agent = StageAgent()
        with pytest.raises(NotImplementedError):
            agent.run("anything")


class TestRepairTruncatedJson:
    def test_valid_json_passes_through(self) -> None:
        assert _repair_truncated_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

    def test_empty_input_returns_none(self) -> None:
        assert _repair_truncated_json("") is None
        assert _repair_truncated_json(None) is None  # type: ignore[arg-type]

    def test_trailing_comma_removed(self) -> None:
        result = _repair_truncated_json('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_in_nested(self) -> None:
        result = _repair_truncated_json('{"a": [1, 2,], "b": {"c": 3,}}')
        assert result == {"a": [1, 2], "b": {"c": 3}}

    def test_unclosed_brackets_repaired(self) -> None:
        result = _repair_truncated_json('{"a": [1, 2, 3')
        assert result == {"a": [1, 2, 3]}

    def test_unclosed_brace_and_bracket(self) -> None:
        result = _repair_truncated_json('{"a": {"b": [1, 2')
        assert result == {"a": {"b": [1, 2]}}

    def test_truncated_mid_string(self) -> None:
        result = _repair_truncated_json('{"a": "hello wo')
        assert result is not None
        assert result["a"].startswith("hello")

    def test_malformed_returns_none(self) -> None:
        result = _repair_truncated_json("definitely not json {{{")
        assert result is None

    def test_last_valid_object_extraction(self) -> None:
        result = _repair_truncated_json('{"a": 1} garbage')
        assert result == {"a": 1}


class TestStripNulls:
    def test_strip_top_level_null(self) -> None:
        result = _strip_nulls({"a": 1, "b": None, "c": "hello"})
        assert result == {"a": 1, "c": "hello"}

    def test_nested_null_removed(self) -> None:
        result = _strip_nulls({"a": {"b": None, "c": 2}})
        assert result == {"a": {"c": 2}}

    def test_null_in_list_preserved(self) -> None:
        """_strip_nulls filters null dict values, not list items."""
        result = _strip_nulls({"a": [1, None, 3]})
        assert result == {"a": [1, None, 3]}  # list items not filtered

    def test_deeply_nested(self) -> None:
        """Null dict values are removed; list nulls are preserved."""
        data = {"x": {"y": [{"z": None, "w": 1}, None]}, "v": None}
        result = _strip_nulls(data)
        assert result == {"x": {"y": [{"w": 1}, None]}}

    def test_non_dict_list_passthrough(self) -> None:
        result = _strip_nulls("hello")
        assert result == "hello"

    def test_integer_passthrough(self) -> None:
        result = _strip_nulls(42)
        assert result == 42

    def test_empty_dict_unchanged(self) -> None:
        result = _strip_nulls({})
        assert result == {}

    def test_empty_list_unchanged(self) -> None:
        result = _strip_nulls([])
        assert result == []


class TestIsThirdPartyProvider:
    def test_default_is_not_third_party(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        assert _is_third_party_provider() is False

    def test_openai_com_url_is_not_third_party(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        assert _is_third_party_provider() is False

    def test_custom_url_is_third_party(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom-provider.com/v1")
        assert _is_third_party_provider() is True

    def test_empty_url_is_not_third_party(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "")
        assert _is_third_party_provider() is False


class TestSummarizeSchemaProps:
    def test_empty_schema(self) -> None:
        result = _summarize_schema_props({})
        assert result == "(any valid JSON)"

    def test_simple_properties(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        result = _summarize_schema_props(schema)
        assert '- "name": string (REQUIRED)' in result
        assert '- "age": integer' in result

    def test_with_enum(self) -> None:
        schema = {
            "properties": {
                "color": {"type": "string", "enum": ["red", "blue"]},
            },
        }
        result = _summarize_schema_props(schema)
        assert "one of" in result
        assert "red" in result
        assert "blue" in result

    def test_array_of_strings(self) -> None:
        schema = {
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = _summarize_schema_props(schema)
        assert "array of string" in result
        assert "tags" in result

    def test_ref_object(self) -> None:
        schema = {
            "properties": {
                "meta": {"$ref": "#/$defs/Metadata"},
            },
            "$defs": {
                "Metadata": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                    },
                },
            },
        }
        result = _summarize_schema_props(schema)
        assert "meta" in result
        assert "Metadata" in result
        assert "version" in result

    def test_indent(self) -> None:
        schema = {
            "properties": {
                "name": {"type": "string"},
            },
        }
        result = _summarize_schema_props(schema, indent=2)
        lines = result.split("\n")
        assert all(line.startswith("    ") for line in lines if line.strip())

    def test_nested_object(self) -> None:
        schema = {
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                    },
                },
            },
        }
        result = _summarize_schema_props(schema)
        assert "config" in result
        assert "enabled" in result
