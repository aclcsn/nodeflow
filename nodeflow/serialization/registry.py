"""The serializer registry.

A *serializer* knows how to write one logical type (``dataframe``,
``sklearn_model``, ...) to a single file and read it back. The registry is the
extension point: built-in types are registered at import time (see
:mod:`nodeflow.serialization.builtins`) and plugins add more via
:func:`register_type`.

This module is a *leaf*: it depends on nothing else in NodeFlow, so it can be
imported from anywhere (SDK, artifact manager, GUI) without cycles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SerializeFn = Callable[[Any, Path], "dict[str, Any] | None"]
DeserializeFn = Callable[[Path], Any]
DetectFn = Callable[[Any], bool]


@dataclass(frozen=True)
class Serializer:
    """A registered (de)serialization handler for one logical type."""

    name: str
    extension: str  # without leading dot, e.g. "parquet"
    serialize: SerializeFn
    deserialize: DeserializeFn
    detector: DetectFn | None = None
    description: str = ""

    def filename_for(self, basename: str) -> str:
        return f"{basename}.{self.extension.lstrip('.')}"


@dataclass(frozen=True)
class StoredArtifact:
    """Result of writing an object to disk via the registry."""

    type: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


class UnknownTypeError(KeyError):
    """Raised when a type name is not present in the registry."""


class SerializerRegistry:
    """A mutable collection of :class:`Serializer` keyed by type name."""

    def __init__(self) -> None:
        self._by_name: dict[str, Serializer] = {}

    # -- registration -----------------------------------------------------
    def register(
        self,
        name: str,
        serialize: SerializeFn,
        deserialize: DeserializeFn,
        extension: str,
        *,
        detector: DetectFn | None = None,
        description: str = "",
        overwrite: bool = False,
    ) -> Serializer:
        """Register a (de)serializer for ``name``.

        Returns the created :class:`Serializer`. Raises ``ValueError`` if the
        type already exists and ``overwrite`` is False.
        """
        if not name or not isinstance(name, str):
            raise ValueError("serializer name must be a non-empty string")
        if name in self._by_name and not overwrite:
            raise ValueError(
                f"type {name!r} is already registered; pass overwrite=True to replace it"
            )
        serializer = Serializer(
            name=name,
            extension=extension.lstrip("."),
            serialize=serialize,
            deserialize=deserialize,
            detector=detector,
            description=description,
        )
        self._by_name[name] = serializer
        return serializer

    def unregister(self, name: str) -> None:
        self._by_name.pop(name, None)

    # -- lookup -----------------------------------------------------------
    def has(self, name: str) -> bool:
        return name in self._by_name

    def get(self, name: str) -> Serializer:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise UnknownTypeError(
                f"no serializer registered for type {name!r}; "
                f"known types: {', '.join(sorted(self._by_name)) or '<none>'}"
            ) from exc

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def detect(self, obj: Any) -> str | None:
        """Return the registered type name matching ``obj``, or None.

        Detectors are consulted in registration order; the first match wins.
        """
        for serializer in self._by_name.values():
            det = serializer.detector
            if det is not None:
                try:
                    if det(obj):
                        return serializer.name
                except Exception:
                    # A misbehaving detector must never break detection.
                    continue
        return None

    # -- I/O --------------------------------------------------------------
    def write(self, type_name: str, obj: Any, directory: Path, basename: str) -> StoredArtifact:
        """Serialize ``obj`` into ``directory`` as ``basename.<ext>``."""
        serializer = self.get(type_name)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / serializer.filename_for(basename)
        result = serializer.serialize(obj, path)
        # The serialize contract is ``-> dict | None``. Be permissive: a handler
        # that returns anything else (e.g. ``return path.write_text(...)``, which
        # yields an int) simply contributes no metadata rather than crashing.
        metadata = dict(result) if isinstance(result, dict) else {}
        if not path.exists():
            raise RuntimeError(
                f"serializer for {type_name!r} did not produce a file at {path}"
            )
        return StoredArtifact(type=type_name, path=path, metadata=metadata)

    def read(self, type_name: str, path: Path) -> Any:
        """Deserialize the object stored at ``path`` for ``type_name``."""
        serializer = self.get(type_name)
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"artifact file does not exist: {path}")
        return serializer.deserialize(path)


# The process-wide default registry.
registry = SerializerRegistry()


def register_type(
    name: str,
    serialize: SerializeFn,
    deserialize: DeserializeFn,
    extension: str,
    *,
    detector: DetectFn | None = None,
    description: str = "",
    overwrite: bool = False,
) -> Serializer:
    """Register a custom type on the process-wide registry.

    Example::

        from nodeflow import register_type
        register_type("geojson", _dump, _load, extension="geojson")
    """
    return registry.register(
        name,
        serialize,
        deserialize,
        extension,
        detector=detector,
        description=description,
        overwrite=overwrite,
    )
