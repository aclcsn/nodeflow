"""Desktop GUI (PySide6 + NodeGraphQt).

Imported lazily by :mod:`nodeflow.app.main` so the headless engine and its tests
never require Qt. Nothing in this package may be imported by the core /
execution / artifacts layers — the dependency arrow points *into* the GUI.

Public entry: :func:`nodeflow.gui.app.run_gui`.
"""

from __future__ import annotations

__all__ = ["run_gui", "MainWindow", "Canvas", "NodeLibrary"]


def __getattr__(name: str):
    # Lazy so that merely importing the package doesn't require Qt at module load.
    if name == "run_gui":
        from .app import run_gui

        return run_gui
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    if name == "Canvas":
        from .canvas import Canvas

        return Canvas
    if name == "NodeLibrary":
        from .node_factory import NodeLibrary

        return NodeLibrary
    raise AttributeError(f"module 'nodeflow.gui' has no attribute {name!r}")
