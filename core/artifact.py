"""Artifact references — the currency passed between nodes.

A node never hands a live object to the next node; it hands an
:class:`ArtifactRef` (node + name + type + on-disk path + metadata). The
downstream node deserializes it on demand. This keeps memory bounded and makes
every run reproducible from disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nodeflow.serialization import registry as default_registry
from nodeflow.serialization.registry import SerializerRegistry


class ArtifactRef(BaseModel):
    """A reference to one serialized artifact on disk."""

    node_id: str
    name: str
    type: str
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def load(self, registry: SerializerRegistry | None = None) -> Any:
        """Deserialize the referenced object."""
        reg = registry or default_registry
        return reg.read(self.type, Path(self.path))

    def as_input(self) -> dict[str, Any]:
        """Project to the SDK ``InputRef`` shape (``type``/``path``/``metadata``)."""
        return {"type": self.type, "path": self.path, "metadata": dict(self.metadata)}

    def exists(self) -> bool:
        return Path(self.path).exists()
