"""Notebook-facing SDK.

Inside a notebook executed by NodeFlow you write pure functions over typed
inputs and outputs::

    from nodeflow import inputs, outputs, params

    df = inputs.train_df            # framework loads the upstream artifact
    model = train(df, max_depth=params.max_depth)
    outputs.model = model           # framework serializes & stores it

The three singletons (:data:`inputs`, :data:`outputs`, :data:`params`) are
proxies onto the *active* node execution context. The engine binds that context
before a notebook runs; tests / in-process callers bind it explicitly via
:func:`bind` or :func:`using`.
"""

from __future__ import annotations

from .context import (
    ENV_VAR,
    MANIFEST_NAME,
    InputRef,
    NodeContext,
    OutputSpec,
    RuntimeContext,
    active,
    bind,
    reset,
    using,
)
from .runtime import inputs, outputs, params

__all__ = [
    "inputs",
    "outputs",
    "params",
    "bind",
    "using",
    "reset",
    "active",
    "NodeContext",
    "RuntimeContext",
    "InputRef",
    "OutputSpec",
    "ENV_VAR",
    "MANIFEST_NAME",
]
