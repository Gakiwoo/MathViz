"""Tests for math_to_manim.schemas.base — ArtifactModel shared base."""

from __future__ import annotations

from typing import Any

import pydantic
import pytest

from math_to_manim.schemas.base import ArtifactModel


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


def test_artifact_model_forbids_extra() -> None:
    """Passing an unknown field must raise ValidationError."""
    with pytest.raises(pydantic.ValidationError):
        SimpleArtifact(name="bad", extra_field="rejected")  # type: ignore[call-arg]
    with pytest.raises(pydantic.ValidationError):
        SimpleArtifact.model_validate({"name": "bad", "extra_field": "rejected"})


def test_artifact_model_validates_assignment() -> None:
    """Assigning an invalid value to an existing field must raise."""
    obj = SimpleArtifact(name="test", value=1)
    with pytest.raises(pydantic.ValidationError):
        obj.value = "not-an-int"  # type: ignore[assignment]


def test_artifact_model_uses_field_names() -> None:
    """populate_by_name allows constructing with field names directly."""

    class AliasedArtifact(ArtifactModel):
        display_name: str

    obj = AliasedArtifact(display_name="main")
    assert obj.display_name == "main"


def test_model_copy_with_metadata_dict() -> None:
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
