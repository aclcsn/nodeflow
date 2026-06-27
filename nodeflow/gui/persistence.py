"""GUI-side workflow persistence: save/restore the whole board."""

from __future__ import annotations

from pathlib import Path

from nodeflow.core.workflow import load_workflow, save_workflow


def save_window(window, path: str | Path, *, name: str | None = None) -> Path:
    """Persist the window's board to ``path`` (capturing current node positions)."""
    window.canvas.sync_positions()
    return save_workflow(
        window.canvas.model, path, name=name or Path(path).stem
    )


def load_into_window(window, path: str | Path) -> None:
    """Restore a board from ``path`` into the window's canvas + library."""
    model = load_workflow(path)
    # Make restored node specs available in the library too.
    for instance in model.nodes.values():
        window.library.add(instance.spec)
    window.library_panel.refresh()
    window.canvas.load_model(model)
    window.log(f"Loaded workflow: {path} ({len(model)} nodes)")
