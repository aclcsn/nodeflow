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


def _upgrade_file_nodes(model) -> int:
    """Add the ``path`` output to file nodes saved before it existed.

    Returns the number of nodes upgraded. Runs before the canvas registers the
    node classes, so the upgraded spec yields both the original output and a
    ``path`` output (matching newly uploaded files).
    """
    from nodeflow.core.spec import PortSpec

    upgraded = 0
    for instance in model.nodes.values():
        spec = instance.spec
        if spec.category == "Files" and "path" not in spec.outputs:
            outputs = dict(spec.outputs)
            outputs["path"] = PortSpec(type="path")
            instance.spec = spec.model_copy(update={"outputs": outputs})
            upgraded += 1
    return upgraded


def load_into_window(window, path: str | Path) -> None:
    """Restore a board from ``path`` into the window's canvas + library."""
    model = load_workflow(path)
    upgraded = _upgrade_file_nodes(model)
    if upgraded and hasattr(window, "_ensure_loader_notebooks"):
        # Regenerate the loaders so a re-run actually produces the path artifact.
        window._ensure_loader_notebooks()
    # Make restored node specs available in the library too.
    for instance in model.nodes.values():
        window.library.add(instance.spec)
    window.library_panel.refresh()
    window.canvas.load_model(model)
    msg = f"Loaded workflow: {path} ({len(model)} nodes)"
    if upgraded:
        msg += f" — added a path output to {upgraded} existing file node(s)"
    window.log(msg)
