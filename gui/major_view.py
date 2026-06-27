"""Drill-down view for a major node.

Expanding a major node opens this window, which shows **only the subnodes inside
it and their outputs**. The main board stays untouched; closing returns you to it.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
)

from nodeflow.core.graph import NodeInstance, WorkflowGraph
from nodeflow.gui.canvas import Canvas
from nodeflow.gui.panels import OutputsPanel
from nodeflow.library import NodeLibrary


class MajorNodeView(QMainWindow):
    """A focused canvas showing one major node's subnodes + their outputs."""

    def __init__(self, major: NodeInstance, artifacts, parent=None) -> None:
        super().__init__(parent)
        self.major = major
        self.artifacts = artifacts
        self.prefix = f"{major.id}/"  # subnode flat-id prefix used for output lookup
        self.setWindowTitle(f"Major Node — {major.label}")
        self.resize(1100, 760)

        # Build the inner graph from the major node's children.
        self.inner = WorkflowGraph()
        for child in major.children:
            self.inner.add_node(child)
        self.inner.connections = list(major.child_connections)

        self.canvas = Canvas(NodeLibrary())
        self.canvas.load_model(self.inner)
        self.setCentralWidget(self.canvas.widget)

        breadcrumb = QDockWidget("Location", self)
        breadcrumb.setWidget(
            QLabel(f"  ‹ Board  /  <b>{major.label}</b>  ({len(major.children)} subnodes)")
        )
        from PySide6.QtCore import Qt

        self.addDockWidget(Qt.TopDockWidgetArea, breadcrumb)

        self.outputs_panel = OutputsPanel()
        out_dock = QDockWidget("Subnode Outputs", self)
        out_dock.setWidget(self.outputs_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, out_dock)

        self._connect_selection()
        self.statusBar().showMessage(
            f"Subnodes of {major.label}. Outputs reflect the latest run."
        )

    def _connect_selection(self) -> None:
        graph = self.canvas.graph
        for sig_name in ("node_selection_changed", "node_selected"):
            sig = getattr(graph, sig_name, None)
            if sig is not None:
                try:
                    sig.connect(lambda *a: self._on_selection())
                    return
                except Exception:
                    continue

    def _on_selection(self) -> None:
        ids = self.canvas.selected_node_ids()
        if not ids:
            self.outputs_panel.show_message("Select a subnode to see its outputs.")
            return
        self.show_subnode_outputs(ids[0])

    def show_subnode_outputs(self, child_id: str) -> None:
        """Show the latest-run artifacts for a subnode (via its flattened id)."""
        run = self.artifacts.latest_run() if self.artifacts else None
        refs = run.artifacts(f"{self.prefix}{child_id}") if run else {}
        self.outputs_panel.show_artifacts(refs)
