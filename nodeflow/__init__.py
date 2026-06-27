"""NodeFlow — a visual workflow system for Jupyter notebooks.

The top-level package exposes the *notebook-facing* public API:

    from nodeflow import inputs, outputs, params

These are lazily resolved so that ``import nodeflow`` stays cheap (it does not
pull in pandas, scikit-learn or Qt). Heavy subsystems live in subpackages and
are imported explicitly where needed:

    nodeflow.serialization   serializer registry
    nodeflow.core            domain models (specs, ports, graph)
    nodeflow.artifacts       immutable run + artifact storage
    nodeflow.execution       papermill execution, DAG scheduler, cache
    nodeflow.gui             desktop UI (PySide6 + NodeGraphQt)
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["inputs", "outputs", "params", "register_type", "__version__"]

# Names that are resolved lazily via ``__getattr__`` so that importing the
# package does not eagerly import the SDK / serialization machinery.
_LAZY = {
    "inputs": ("nodeflow.sdk", "inputs"),
    "outputs": ("nodeflow.sdk", "outputs"),
    "params": ("nodeflow.sdk", "params"),
    "register_type": ("nodeflow.serialization", "register_type"),
}


def __getattr__(name: str):  # noqa: D401 - module-level lazy attribute hook
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'nodeflow' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(target[0])
    return getattr(module, target[1])


def __dir__() -> list[str]:
    return sorted(__all__)
