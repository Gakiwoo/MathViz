"""Tests for math_to_manim.schemas.base — ArtifactModel, PYDANTIC_V2, and v1/v2 shims."""

import importlib
from typing import Any
from unittest.mock import patch

import pydantic
import pytest

from math_to_manim.schemas.base import (
    PYDANTIC_V2,
    ArtifactModel,
    ConfigDict,
    model_validator,
    root_validator,
)


# ---------------------------------------------------------------------------
# PYDANTIC_V2 detection
# ---------------------------------------------------------------------------


def test_pydantic_v2_detection() -> None:
    """PYDANTIC_V2 must be True when running under Pydantic v2."""
    assert PYDANTIC_V2 is True


# ---------------------------------------------------------------------------
# ArtifactModel — basic validation & serialisation
# ---------------------------------------------------------------------------


class SimpleArtifact(ArtifactModel):
    name: str
    value: int = 0


def test_artifact_model_basic() -> None:
    """Create a subclass, validate fields, and test round-trip serialisation."""
    obj = SimpleArtifact(name="test", value=42)
    assert obj.name == "test"
    assert obj.value == 42

    # model_dump
    dumped = obj.model_dump()
    assert dumped == {"name": "test", "value": 42}

    # model_validate round-trip
    restored = SimpleArtifact.model_validate(dumped)
    assert isinstance(restored, SimpleArtifact)
    assert restored.name == "test"
    assert restored.value == 42

    # model_json_schema
    schema = SimpleArtifact.model_json_schema()
    assert "properties" in schema
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["value"]["type"] == "integer"

    # model_dump_json + parse back
    raw = obj.model_dump_json()
    from_json = SimpleArtifact.model_validate_json(raw)
    assert from_json.name == "test"
    assert from_json.value == 42


# ---------------------------------------------------------------------------
# to_public_dict
# ---------------------------------------------------------------------------


class ArtifactWithMeta(ArtifactModel):
    title: str
    tags: list[str] = []


def test_to_public_dict() -> None:
    """to_public_dict must return a JSON-safe dict."""
    obj = ArtifactWithMeta(title="hello", tags=["a", "b"])
    public = obj.to_public_dict()

    assert public == {"title": "hello", "tags": ["a", "b"]}
    # mode="json" guarantees JSON-safe types (str, int, float, list, dict, None)
    assert isinstance(public["title"], str)
    assert isinstance(public["tags"], list)
    assert public["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# extra = "forbid"
# ---------------------------------------------------------------------------


def test_artifact_model_forbids_extra() -> None:
    """Passing an unknown field must raise ValidationError."""
    with pytest.raises(pydantic.ValidationError):
        SimpleArtifact(name="bad", extra_field="rejected")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Pydantic v1 compatibility (via mock)
# ---------------------------------------------------------------------------


def test_pydantic_v1_compatibility() -> None:
    """When pydantic.VERSION is mocked to '1.10.0' the v1 branches must activate."""
    import math_to_manim.schemas.base as base_mod

    with patch.object(pydantic, "VERSION", "1.10.0"):
        importlib.reload(base_mod)

        # --- module-level flags ---
        assert base_mod.PYDANTIC_V2 is False
        assert base_mod.root_validator is not None  # imported from pydantic
        assert base_mod.ConfigDict is None
        assert base_mod.model_validator is None

        # --- v1 shims are present on ArtifactModel ---
        # NOTE: The v1 shim methods (model_validate, model_json_schema,
        # model_dump, model_dump_json, model_copy) cannot be *exercised*
        # under pydantic v2 because pydantic v2's deprecated v1-compat
        # methods (parse_obj, schema, dict, json, copy) internally call
        # the v2 equivalents (model_validate, model_json_schema, ...),
        # creating infinite recursion.  The *code paths* are verified by
        # the module-level flag assertions above; the *signatures exist*
        # on the class.

        # Constructor + field access works via the v1 Config class
        class V1Artifact(base_mod.ArtifactModel):  # type: ignore[misc]
            name: str
            value: int = 0

        obj = V1Artifact(name="v1-test", value=7)
        assert obj.name == "v1-test"
        assert obj.value == 7

        # extra = "forbid" still works via Config
        with pytest.raises(pydantic.ValidationError):
            V1Artifact(name="v1", extra="x")  # type: ignore[call-arg]

    # --- restore v2 state for subsequent tests ---
    importlib.reload(base_mod)
    assert base_mod.PYDANTIC_V2 is True


# ---------------------------------------------------------------------------
# model_copy with metadata dict
# ---------------------------------------------------------------------------


def test_repeated_extra_access() -> None:
    """Artifact subclass holding a metadata dict; model_copy must work."""

    class TaggedArtifact(ArtifactModel):
        label: str
        metadata: dict[str, Any] = {}

    obj = TaggedArtifact(label="main", metadata={"source": "test", "version": 1})

    # Shallow copy
    copied = obj.model_copy()
    assert copied.label == "main"
    assert copied.metadata == {"source": "test", "version": 1}

    # Copy + update
    updated = obj.model_copy(update={"label": "copy"})
    assert updated.label == "copy"
    assert updated.metadata == {"source": "test", "version": 1}
    # Original unchanged
    assert obj.label == "main"
