"""Dock panels: notebook library, properties/parameters, outputs, logs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nodeflow.core.graph import NodeInstance
from nodeflow.core.spec import ParameterType
from nodeflow.gui.node_factory import NodeLibrary


class LibraryPanel(QWidget):
    """Left panel: node specs grouped by category.

    Each notebook has a ``+`` button (add it to the workflow), a ``…`` button
    (edit its template), and a ``🗑`` button (remove it from the library).
    The ``⟳`` button rescans the project for new notebooks. Right-clicking a
    category lets you pick one colour for all of its nodes.
    """

    add_requested = Signal(str)             # spec name
    edit_template_requested = Signal(str)   # spec name
    delete_requested = Signal(str)          # spec name
    refresh_requested = Signal()
    category_color_changed = Signal(str, tuple)  # category, (r, g, b)

    def __init__(self, library: NodeLibrary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Notebook Library</b>"))
        header.addStretch(1)
        refresh_btn = QToolButton()
        refresh_btn.setText("⟳")
        refresh_btn.setToolTip("Refresh — detect newly added notebooks/specs")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)
        self.refresh()

    def refresh(self) -> None:
        from nodeflow.gui.theme import color_for_category

        self.tree.clear()
        for category, specs in self.library.by_category().items():
            cat_item = QTreeWidgetItem([category])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            cat_item.setBackground(0, QBrush(QColor(*color_for_category(category))))
            self.tree.addTopLevelItem(cat_item)
            for spec in specs:
                child = QTreeWidgetItem([""])
                child.setData(0, Qt.UserRole, spec.name)
                child.setToolTip(0, spec.description or spec.name)
                cat_item.addChild(child)
                self.tree.setItemWidget(child, 0, self._row_widget(spec.name))
            cat_item.setExpanded(True)

    def _row_widget(self, spec_name: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(2)
        h.addWidget(QLabel(spec_name))
        h.addStretch(1)
        for text, tip, slot in (
            ("+", f"Add {spec_name} to the workflow",
             lambda: self.add_requested.emit(spec_name)),
            ("…", f"Edit the {spec_name} notebook template",
             lambda: self.edit_template_requested.emit(spec_name)),
            ("🗑", f"Delete {spec_name} from the library",
             lambda: self.delete_requested.emit(spec_name)),
        ):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            h.addWidget(btn)
        return row

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        spec_name = item.data(0, Qt.UserRole)
        if spec_name:
            self.add_requested.emit(spec_name)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None or item.parent() is not None:
            return  # only category (top-level) rows have a context menu
        category = item.text(0)
        menu = QMenu(self)
        menu.addAction("Set Colour…", lambda: self._pick_color(category))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _pick_color(self, category: str) -> None:
        from PySide6.QtWidgets import QColorDialog

        from nodeflow.gui.theme import color_for_category

        current = QColor(*color_for_category(category))
        color = QColorDialog.getColor(current, self, f"Colour for '{category}'")
        if color.isValid():
            self.category_color_changed.emit(category, (color.red(), color.green(), color.blue()))
            self.refresh()


class FilesPanel(QWidget):
    """Left panel (below the Library): files uploaded as source nodes.

    Files can be uploaded via the ``+`` button or the right-click menu; each
    uploaded file is listed and corresponds to a file node on the canvas.
    """

    upload_requested = Signal()
    file_activated = Signal(str)  # absolute path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Files</b>"))
        header.addStretch(1)
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("Upload a file")
        add_btn.clicked.connect(self.upload_requested.emit)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list)

    def add_file(self, path: str) -> None:
        from pathlib import Path

        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.UserRole, str(path))
        item.setToolTip(str(path))
        self.list.addItem(item)

    def clear(self) -> None:
        self.list.clear()

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Upload a file", self.upload_requested.emit)
        menu.exec(self.list.mapToGlobal(pos))

    def _on_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.file_activated.emit(path)


class PropertiesPanel(QWidget):
    """Right panel: the selected node's properties + editable parameters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignTop)
        self._title = QLabel("No node selected")
        self._title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._meta = QLabel("")
        self._meta.setWordWrap(True)
        self._layout.addWidget(self._title)
        self._layout.addWidget(self._meta)
        self._form_host: QWidget | None = None
        self._instance: NodeInstance | None = None

    def clear(self) -> None:
        self._title.setText("No node selected")
        self._meta.setText("")
        self._drop_form()
        self._instance = None

    def show_node(self, instance: NodeInstance) -> None:
        self._instance = instance
        spec = instance.spec
        self._title.setText(instance.label)
        self._meta.setText(
            f"<b>Category:</b> {spec.category}<br>"
            f"<b>Notebook:</b> {spec.notebook or '—'}<br>"
            f"<b>Inputs:</b> {', '.join(spec.inputs) or '—'}<br>"
            f"<b>Outputs:</b> {', '.join(spec.outputs) or '—'}<br>"
            f"{spec.description}"
        )
        self._drop_form()
        self._build_param_form(instance)

    def _drop_form(self) -> None:
        if self._form_host is not None:
            self._layout.removeWidget(self._form_host)
            self._form_host.deleteLater()
            self._form_host = None

    def _build_param_form(self, instance: NodeInstance) -> None:
        host = QWidget()
        form = QFormLayout(host)
        for name, pspec in instance.spec.parameters.items():
            value = instance.params.get(name, pspec.default)
            widget = self._param_widget(name, pspec, value, instance)
            form.addRow(name, widget)
        self._layout.addWidget(host)
        self._form_host = host

    def _param_widget(self, name: str, pspec, value: Any, instance: NodeInstance) -> QWidget:
        def store(v):
            instance.params[name] = v

        if pspec.type is ParameterType.INT:
            w = QSpinBox()
            w.setRange(int(pspec.min) if pspec.min is not None else -10_000_000,
                       int(pspec.max) if pspec.max is not None else 10_000_000)
            w.setValue(int(value) if value is not None else 0)
            w.valueChanged.connect(store)
            return w
        if pspec.type is ParameterType.FLOAT:
            w = QDoubleSpinBox()
            w.setDecimals(4)
            w.setRange(pspec.min if pspec.min is not None else -1e9,
                       pspec.max if pspec.max is not None else 1e9)
            w.setValue(float(value) if value is not None else 0.0)
            w.valueChanged.connect(store)
            return w
        if pspec.type is ParameterType.BOOL:
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(store)
            return w
        if pspec.type is ParameterType.CHOICE:
            w = QComboBox()
            for choice in pspec.choices or []:
                w.addItem(str(choice), choice)
            if value is not None:
                idx = w.findData(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            w.currentIndexChanged.connect(lambda i, w=w: store(w.itemData(i)))
            return w
        # str / fallback
        w = QLineEdit("" if value is None else str(value))
        w.textChanged.connect(store)
        return w


class OutputsPanel(QWidget):
    """Right panel tab: previews of the selected node's outputs.

    Renders one tab per artifact via the viewer registry
    (:mod:`nodeflow.gui.viewers`).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QStackedWidget, QTabWidget

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._stack = QStackedWidget()
        self._info = QLabel("Run a node to see its outputs here.")
        self._info.setWordWrap(True)
        self._info.setAlignment(Qt.AlignTop)
        self._tabs = QTabWidget()
        self._stack.addWidget(self._info)  # index 0
        self._stack.addWidget(self._tabs)  # index 1
        self._layout.addWidget(self._stack)

    def show_message(self, text: str) -> None:
        self._info.setText(text)
        self._stack.setCurrentIndex(0)

    def show_artifacts(self, refs: dict) -> None:
        """Render previews for ``{name: ArtifactRef}``."""
        from nodeflow.gui.viewers import make_viewer

        self._tabs.clear()
        if not refs:
            self.show_message("This node has no stored outputs yet.")
            return
        for name, ref in refs.items():
            self._tabs.addTab(make_viewer(ref), name)
        self._stack.setCurrentIndex(1)


class LogPanel(QWidget):
    """Bottom panel: execution logs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        layout.addWidget(self.view)

    def log(self, message: str) -> None:
        self.view.appendPlainText(message)
