"""Application wiring and entry point.

:mod:`nodeflow.app.main` constructs the engine + GUI and starts the Qt event
loop. Running ``python -m nodeflow.app`` is equivalent to the ``nodeflow``
console script.
"""

from __future__ import annotations

__all__ = ["main"]

from .main import main
