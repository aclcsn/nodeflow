"""SDK runtime proxies bound to the active node execution context.

Notebook code imports the three module-level singletons::

    from nodeflow import inputs, outputs, params

Each is a thin, *stateless* proxy: all real state lives in the active
:class:`~nodeflow.sdk.context.RuntimeContext`, resolved on every access. This is
what lets ``from nodeflow import inputs`` be evaluated once at import time yet
still reflect whichever context the engine has bound.
"""

from __future__ import annotations

from typing import Any

from . import context as _ctx


class _Inputs:
    """Lazy, read-only view of this node's upstream artifacts.

    ``inputs.train_df`` deserializes the connected artifact on first access and
    caches it. Use ``name in inputs`` / ``inputs.get(name)`` / ``inputs[name]``
    for dynamic access.
    """

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _ctx.active().load_input(name)

    def __getitem__(self, name: str) -> Any:
        return _ctx.active().load_input(name)

    def __contains__(self, name: str) -> bool:
        return _ctx.active().has_input(name)

    def get(self, name: str, default: Any = None) -> Any:
        ctx = _ctx.active()
        return ctx.load_input(name) if ctx.has_input(name) else default

    def __dir__(self) -> list[str]:
        try:
            return _ctx.active().input_names
        except RuntimeError:
            return []

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        try:
            return f"<nodeflow.inputs {_ctx.active().input_names}>"
        except RuntimeError:
            return "<nodeflow.inputs (unbound)>"


class _Outputs:
    """Write-through view of this node's outputs.

    Assigning ``outputs.model = obj`` serializes ``obj`` immediately into the
    node's run directory and records it in the manifest. Reading ``outputs.model``
    after assignment returns the :class:`StoredArtifact` *reference* (never the
    live object — artifacts are references, not in-memory values).
    """

    def __setattr__(self, name: str, value: Any) -> None:
        _ctx.active().capture_output(name, value)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _ctx.active().produced(name)

    def __setitem__(self, name: str, value: Any) -> None:
        _ctx.active().capture_output(name, value)

    def __getitem__(self, name: str) -> Any:
        return _ctx.active().produced(name)

    def __dir__(self) -> list[str]:
        try:
            return _ctx.active().declared_output_names
        except RuntimeError:
            return []

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        try:
            return f"<nodeflow.outputs declared={_ctx.active().declared_output_names}>"
        except RuntimeError:
            return "<nodeflow.outputs (unbound)>"


class _Params:
    """Read-only view of this node's injected parameters."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _ctx.active().param(name)

    def __getitem__(self, name: str) -> Any:
        return _ctx.active().param(name)

    def __contains__(self, name: str) -> bool:
        return _ctx.active().has_param(name)

    def get(self, name: str, default: Any = None) -> Any:
        ctx = _ctx.active()
        return ctx.param(name) if ctx.has_param(name) else default

    def __dir__(self) -> list[str]:
        try:
            return _ctx.active().param_names
        except RuntimeError:
            return []

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        try:
            return f"<nodeflow.params {_ctx.active().param_names}>"
        except RuntimeError:
            return "<nodeflow.params (unbound)>"


inputs = _Inputs()
outputs = _Outputs()
params = _Params()
