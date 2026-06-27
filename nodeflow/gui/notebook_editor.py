"""In-app notebook editor.

Edits a node's notebook source. Saving writes a **separate per-node notebook**
(leaving the shared template untouched) and points the node at its own copy.

Cells are shown joined by a ``# %%`` separator (the common notebook-cell
convention), so multi-cell notebooks round-trip.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

CELL_SEPARATOR = "\n# %%\n"


def join_cells(code_cells: list[str]) -> str:
    return CELL_SEPARATOR.join(code_cells)


def split_cells(text: str) -> list[str]:
    parts = text.split(CELL_SEPARATOR.strip("\n"))
    cells = [p.strip("\n") for p in parts]
    return [c for c in cells if c.strip()] or [""]


class NotebookEditorDialog(QDialog):
    """Edit a node's notebook (parameters cell + code cells)."""

    def __init__(self, node_label: str, parameters_cell: str, code_cells: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Notebook — {node_label}")
        self.resize(760, 620)
        self.saved = False

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.Monospace)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Parameters</b> (injected before the code runs)"))
        self.params_edit = QPlainTextEdit(parameters_cell)
        self.params_edit.setFont(mono)
        self.params_edit.setMaximumHeight(120)
        layout.addWidget(self.params_edit)

        layout.addWidget(QLabel("<b>Code</b> (cells separated by <code># %%</code>)"))
        self.code_edit = QPlainTextEdit(join_cells(code_cells))
        self.code_edit.setFont(mono)
        layout.addWidget(self.code_edit)

        note = QLabel(
            "<i>Saving creates a separate notebook for this node "
            "(notebooks/&lt;node&gt;.ipynb); the original template is left unchanged.</i>"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        self.saved = True
        self.accept()

    def result_cells(self) -> tuple[str, list[str]]:
        """Return the edited ``(parameters_cell, code_cells)``."""
        return self.params_edit.toPlainText(), split_cells(self.code_edit.toPlainText())
