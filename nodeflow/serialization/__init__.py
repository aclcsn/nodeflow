"""Serialization subsystem: a pluggable registry of typed (de)serializers.

Public API::

    from nodeflow.serialization import registry, register_type, StoredArtifact

Built-in serializers (parquet, joblib, png, json, npy, html, txt) are added in
:mod:`nodeflow.serialization.builtins`, which is imported for its side effects
the first time this package is loaded.
"""

from __future__ import annotations

from .registry import (
    Serializer,
    SerializerRegistry,
    StoredArtifact,
    UnknownTypeError,
    register_type,
    registry,
)

# Register the built-in serializers (side-effecting import). Wrapped so that a
# missing optional dependency degrades gracefully rather than breaking
# ``import nodeflow.serialization`` entirely.
try:  # pragma: no cover - exercised indirectly by the rest of the suite
    from . import builtins as _builtins  # noqa: F401
except Exception as _exc:  # pragma: no cover
    import warnings

    warnings.warn(f"NodeFlow built-in serializers failed to load: {_exc}", stacklevel=2)

__all__ = [
    "Serializer",
    "SerializerRegistry",
    "StoredArtifact",
    "UnknownTypeError",
    "register_type",
    "registry",
]
