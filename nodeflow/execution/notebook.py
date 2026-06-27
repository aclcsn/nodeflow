"""Helpers for building and writing notebooks programmatically.

Used by the execution engine's tests and by the template system (Phase 14) to
generate notebooks with the correct kernelspec and a ``parameters``-tagged cell
(so Papermill injects parameters in a predictable place).
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

#: The kernel NodeFlow notebooks run under by default (registered into the venv).
DEFAULT_KERNEL = "nodeflow"


def read_notebook(path: str | Path) -> tuple[str, list[str]]:
    """Read a notebook into ``(parameters_cell_source, [code_cell_source, ...])``.

    The ``parameters``-tagged code cell (if any) is returned separately; all other
    code cells are returned in order. Inverse of :func:`build_notebook`.
    """
    nb = nbformat.read(str(path), as_version=4)
    params = ""
    code: list[str] = []
    for cell in nb.cells:
        if cell.get("cell_type") != "code":
            continue
        tags = cell.get("metadata", {}).get("tags", []) or []
        if "parameters" in tags and not params:
            params = cell.source
        else:
            code.append(cell.source)
    return params, code


def build_notebook(
    code_cells: list[str],
    *,
    kernel_name: str = DEFAULT_KERNEL,
    parameters_cell: str = "",
    markdown_intro: str | None = None,
) -> nbformat.NotebookNode:
    """Build an nbformat notebook from a list of code-cell source strings.

    The first code cell is tagged ``parameters`` (empty by default) so Papermill
    injects parameters there rather than guessing a location.
    """
    nb = new_notebook()
    nb.metadata["kernelspec"] = {
        "name": kernel_name,
        "display_name": kernel_name,
        "language": "python",
    }
    nb.metadata["language_info"] = {"name": "python"}

    cells = []
    if markdown_intro:
        cells.append(new_markdown_cell(markdown_intro))

    params = new_code_cell(parameters_cell)
    params.metadata["tags"] = ["parameters"]
    cells.append(params)

    for src in code_cells:
        cells.append(new_code_cell(src))

    nb.cells = cells
    return nb


def write_notebook(nb: nbformat.NotebookNode, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, str(path))
    return path


def save_notebook(
    code_cells: list[str],
    path: str | Path,
    *,
    kernel_name: str = DEFAULT_KERNEL,
    parameters_cell: str = "",
    markdown_intro: str | None = None,
) -> Path:
    """Build and write a notebook in one call."""
    nb = build_notebook(
        code_cells,
        kernel_name=kernel_name,
        parameters_cell=parameters_cell,
        markdown_intro=markdown_intro,
    )
    return write_notebook(nb, path)
