from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field  # noqa: F401 — Field re-exported for submodules


class ArtifactModel(BaseModel):
    """Shared Pydantic base for pipeline artifacts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for CLI/API responses."""

        return self.model_dump(mode="json")
