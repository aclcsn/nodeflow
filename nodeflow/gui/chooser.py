"""Startup workflow chooser.

When NodeFlow launches without an explicit workflow path, this dialog lets the
user pick which saved workflow to open (or start a blank board / browse).
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


def _looks_like_workflow(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    return isinstance(data, dict) and "nodes" in data and "connections" in data


def find_workflows(search_dirs: list[str | Path]) -> list[Path]:
    """Return saved workflow ``*.json`` files found under the given directories."""
    seen: dict[Path, None] = {}
    for d in search_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            rp = path.resolve()
            if rp not in seen and _looks_like_workflow(rp):
                seen[rp] = None
    return list(seen)


def _workflow_label(path: Path) -> str:
    try:
        data = json.loads(path.read_text())
        name = data.get("name") or path.stem
        n = len(data.get("nodes", []))
        return f"{name}   ({n} nodes · {path.name})"
    except Exception:
        return path.name


class WorkflowChooserDialog(QDialog):
    """Pick a workflow to open at startup.

    After ``exec()`` (or a simulated choice), the outcome is available as
    ``self.choice`` — one of ``"open"`` / ``"new"`` / ``"cancel"`` — and, when
    ``"open"``, ``self.selected_path``.
    """

    def __init__(self, project_dir: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NodeFlow — Open Workflow")
        self.resize(560, 420)
        self.project_dir = Path(project_dir)
        self.choice: str = "cancel"
        self.selected_path: Path | None = None

        layout = QVBoxLayout(self)
        header = QLabel("<b>Choose a workflow to open</b>")
        layout.addWidget(header)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._open_selected())
        layout.addWidget(self.list)

        self._workflows = find_workflows([self.project_dir, self.project_dir / "workflows"])
        if self._workflows:
            for path in self._workflows:
                item = QListWidgetItem(_workflow_label(path))
                item.setData(Qt.UserRole, str(path))
                self.list.addItem(item)
            self.list.setCurrentRow(0)
        else:
            layout.addWidget(QLabel("No saved workflows found in this project."))

        buttons = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.setEnabled(bool(self._workflows))
        self.open_btn.clicked.connect(self._open_selected)
        self.new_btn = QPushButton("New Blank Workflow")
        self.new_btn.clicked.connect(self._new_blank)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        for b in (self.open_btn, self.new_btn, self.browse_btn, cancel_btn):
            buttons.addWidget(b)
        layout.addLayout(buttons)

    # -- handlers (also callable directly from tests) ---------------------
    def _open_selected(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.choice = "open"
        self.selected_path = Path(item.data(Qt.UserRole))
        self.accept()

    def _new_blank(self) -> None:
        self.choice = "new"
        self.selected_path = None
        self.accept()

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Open Workflow", str(self.project_dir), "Workflow (*.json)"
        )
        if path:
            self.choice = "open"
            self.selected_path = Path(path)
            self.accept()

    @classmethod
    def choose(cls, project_dir: str | Path, parent=None) -> tuple[str, Path | None]:
        """Show the dialog and return ``(choice, path)``."""
        dlg = cls(project_dir, parent)
        dlg.exec()
        return dlg.choice, dlg.selected_path
