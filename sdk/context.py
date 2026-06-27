"""The node execution context — the contract between the engine and a notebook.

The engine describes one node's run as a small, serializable :class:`NodeContext`
(inputs, params, declared outputs, run directory). It writes that to a JSON file
and points the kernel at it via the ``NODEFLOW_CONTEXT`` environment variable.

Inside the notebook, the SDK proxies (``inputs`` / ``outputs`` / ``params``)
resolve the *active* :class:`RuntimeContext`, which:

* lazily deserializes an input artifact on first access,
* serializes an output **immediately** on assignment and records it in a manifest,
* exposes injected parameters.

The context can also be bound programmatically (used by tests and by in-process
execution) via :func:`bind` / :func:`using`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nodeflow.serialization import StoredArtifact
from nodeflow.serialization import registry as default_registry
from nodeflow.serialization.registry import SerializerRegistry

#: Environment variable holding the path to the active context JSON file.
ENV_VAR = "NODEFLOW_CONTEXT"

#: Manifest filename written into each node's run directory.
MANIFEST_NAME = "_outputs.json"


# --------------------------------------------------------------------------- #
# Serializable spec
# --------------------------------------------------------------------------- #
class InputRef(BaseModel):
    """A reference to one upstream artifact this node consumes."""

    type: str
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutputSpec(BaseModel):
    """Declared output. ``type`` may be omitted to auto-detect on capture."""

    type: str | None = None


class NodeContext(BaseModel):
    """Everything a notebook needs to run as a pure function."""

    node_id: str
    node_name: str = ""
    run_dir: str
    inputs: dict[str, InputRef] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, OutputSpec] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> NodeContext:
        data = json.loads(Path(path).read_text())
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(), indent=2, default=str))
        return path


# --------------------------------------------------------------------------- #
# Runtime wrapper
# --------------------------------------------------------------------------- #
class RuntimeContext:
    """Live state for one node execution: input cache + produced artifacts."""

    def __init__(self, spec: NodeContext, registry: SerializerRegistry | None = None) -> None:
        self.spec = spec
        self.registry = registry or default_registry
        self.run_dir = Path(spec.run_dir)
        self._input_cache: dict[str, Any] = {}
        self._produced: dict[str, StoredArtifact] = {}

    # -- inputs -----------------------------------------------------------
    @property
    def input_names(self) -> list[str]:
        return list(self.spec.inputs)

    def has_input(self, name: str) -> bool:
        return name in self.spec.inputs

    def load_input(self, name: str) -> Any:
        if name not in self.spec.inputs:
            available = ", ".join(self.input_names) or "<none>"
            raise AttributeError(
                f"input {name!r} is not connected for node {self.spec.node_id!r}; "
                f"available inputs: {available}"
            )
        if name not in self._input_cache:
            ref = self.spec.inputs[name]
            self._input_cache[name] = self.registry.read(ref.type, Path(ref.path))
        return self._input_cache[name]

    # -- params -----------------------------------------------------------
    @property
    def param_names(self) -> list[str]:
        return list(self.spec.params)

    def has_param(self, name: str) -> bool:
        return name in self.spec.params

    def param(self, name: str) -> Any:
        if name not in self.spec.params:
            available = ", ".join(self.param_names) or "<none>"
            raise AttributeError(
                f"parameter {name!r} is not defined for node {self.spec.node_id!r}; "
                f"available parameters: {available}"
            )
        return self.spec.params[name]

    # -- outputs ----------------------------------------------------------
    @property
    def declared_output_names(self) -> list[str]:
        return list(self.spec.outputs)

    def capture_output(self, name: str, value: Any) -> StoredArtifact:
        """Serialize ``value`` immediately and record it in the manifest."""
        declared = self.spec.outputs.get(name)
        type_name = declared.type if declared and declared.type else None
        if type_name is None:
            type_name = self.registry.detect(value)
        if type_name is None:
            raise TypeError(
                f"cannot determine a serializer for output {name!r} "
                f"(value of type {type(value).__name__}). Declare its type in the node "
                f"spec or register one with nodeflow.register_type(...)."
            )
        stored = self.registry.write(type_name, value, self.run_dir, name)
        self._produced[name] = stored
        self._write_manifest()
        return stored

    def produced(self, name: str) -> StoredArtifact:
        if name not in self._produced:
            raise AttributeError(f"output {name!r} has not been produced yet")
        return self._produced[name]

    def manifest(self) -> dict[str, Any]:
        return {
            "node_id": self.spec.node_id,
            "node_name": self.spec.node_name,
            "outputs": {
                name: {
                    "type": art.type,
                    "path": _relativize(art.path, self.run_dir),
                    "metadata": art.metadata,
                }
                for name, art in self._produced.items()
            },
        }

    def _write_manifest(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / MANIFEST_NAME).write_text(
            json.dumps(self.manifest(), indent=2, default=str)
        )


def _relativize(path: Path, base: Path) -> str:
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #
# Active-context management
# --------------------------------------------------------------------------- #
_active: RuntimeContext | None = None


def _coerce(
    context: NodeContext | RuntimeContext | dict | str | Path,
    registry: SerializerRegistry | None,
) -> RuntimeContext:
    if isinstance(context, RuntimeContext):
        return context
    if isinstance(context, NodeContext):
        return RuntimeContext(context, registry)
    if isinstance(context, dict):
        return RuntimeContext(NodeContext.model_validate(context), registry)
    if isinstance(context, (str, Path)):
        return RuntimeContext(NodeContext.from_file(context), registry)
    raise TypeError(f"cannot bind context of type {type(context).__name__}")


def bind(
    context: NodeContext | RuntimeContext | dict | str | Path,
    registry: SerializerRegistry | None = None,
) -> RuntimeContext:
    """Set the process-wide active context. Returns the bound RuntimeContext."""
    global _active
    _active = _coerce(context, registry)
    return _active


def reset() -> None:
    """Clear the active context."""
    global _active
    _active = None


def active() -> RuntimeContext:
    """Return the active context, auto-loading from ``NODEFLOW_CONTEXT`` if needed."""
    global _active
    if _active is None:
        env_path = os.environ.get(ENV_VAR)
        if env_path:
            _active = RuntimeContext(NodeContext.from_file(env_path))
        else:
            raise RuntimeError(
                "no active NodeFlow context. The SDK (inputs/outputs/params) is only "
                "usable inside a notebook run by NodeFlow, or after calling "
                "nodeflow.sdk.bind(...)."
            )
    return _active


@contextmanager
def using(
    context: NodeContext | RuntimeContext | dict | str | Path,
    registry: SerializerRegistry | None = None,
) -> Iterator[RuntimeContext]:
    """Temporarily bind a context (restores the previous one on exit)."""
    global _active
    previous = _active
    try:
        yield bind(context, registry)
    finally:
        _active = previous
