"""Output viewers: turn an :class:`ArtifactRef` into a preview QWidget.

A small registry keyed by artifact *type* makes viewers pluggable (Phase 16). A
viewer factory is ``(ArtifactRef) -> QWidget``; failures are caught and rendered
as an error label so a bad artifact never crashes the UI.

Built-ins:

    dataframe      shape + dtypes + first 100 rows (table)
    figure         the PNG, scaled to fit
    html           rendered HTML
    text           raw text
    dict / list    pretty-printed JSON
    sklearn_model  class + hyper-parameters (from metadata)
    ndarray        shape/dtype + a value preview
"""

from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nodeflow.core.artifact import ArtifactRef

ViewerFactory = Callable[[ArtifactRef], QWidget]

_VIEWERS: dict[str, ViewerFactory] = {}


def register_viewer(type_name: str, factory: ViewerFactory, *, overwrite: bool = False) -> None:
    if type_name in _VIEWERS and not overwrite:
        raise ValueError(f"viewer for {type_name!r} already registered")
    _VIEWERS[type_name] = factory


def unregister_viewer(type_name: str) -> None:
    _VIEWERS.pop(type_name, None)


def has_viewer(type_name: str) -> bool:
    return type_name in _VIEWERS


def viewer_types() -> list[str]:
    return sorted(_VIEWERS)


def _label(text: str, *, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(wrap)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return lbl


def make_viewer(ref: ArtifactRef) -> QWidget:
    """Build a preview widget for ``ref`` (never raises)."""
    factory = _VIEWERS.get(ref.type)
    try:
        if factory is None:
            return _generic_viewer(ref)
        return factory(ref)
    except Exception as exc:  # keep the UI alive on any preview failure
        return _label(f"Could not preview {ref.name} ({ref.type}):\n{exc}")


# --------------------------------------------------------------------------- #
# Built-in viewers
# --------------------------------------------------------------------------- #
def _generic_viewer(ref: ArtifactRef) -> QWidget:
    meta = json.dumps(ref.metadata, indent=2, default=str) if ref.metadata else "{}"
    return _label(f"<b>{ref.name}</b> · type <code>{ref.type}</code><br>{ref.path}<br><pre>{meta}</pre>")


def _dataframe_viewer(ref: ArtifactRef) -> QWidget:
    df = ref.load()
    container = QWidget()
    layout = QVBoxLayout(container)
    rows, cols = df.shape
    dtypes = ", ".join(f"{c}:{t}" for c, t in zip(df.columns, df.dtypes))
    layout.addWidget(_label(f"<b>shape</b> {rows} × {cols}"))
    layout.addWidget(_label(f"<b>dtypes</b> {dtypes}"))

    preview = df.head(100)
    table = QTableWidget(len(preview), cols)
    table.setHorizontalHeaderLabels([str(c) for c in df.columns])
    for r in range(len(preview)):
        for c in range(cols):
            table.setItem(r, c, QTableWidgetItem(str(preview.iat[r, c])))
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    layout.addWidget(table)
    if rows > 100:
        layout.addWidget(_label(f"(showing first 100 of {rows} rows)"))
    return container


def _figure_viewer(ref: ArtifactRef) -> QWidget:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    label = QLabel()
    label.setAlignment(Qt.AlignCenter)
    pix = QPixmap(str(ref.path))
    label.setPixmap(pix)
    scroll.setWidget(label)
    return scroll


def _html_viewer(ref: ArtifactRef) -> QWidget:
    browser = QTextBrowser()
    browser.setHtml(ref.load())
    return browser


def _text_viewer(ref: ArtifactRef) -> QWidget:
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(str(ref.load()))
    return edit


def _json_viewer(ref: ArtifactRef) -> QWidget:
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(json.dumps(ref.load(), indent=2, default=str))
    return edit


def _model_viewer(ref: ArtifactRef) -> QWidget:
    meta = ref.metadata or {}
    cls = meta.get("class", "?")
    module = meta.get("module", "")
    params = meta.get("params", {})
    lines = [f"<b>{cls}</b>", f"<i>{module}</i>", "", "<b>Parameters</b>"]
    if params:
        lines += [f"&nbsp;&nbsp;{k} = {v}" for k, v in params.items()]
    else:
        lines.append("&nbsp;&nbsp;(none recorded)")
    return _label("<br>".join(lines))


def _ndarray_viewer(ref: ArtifactRef) -> QWidget:
    arr = ref.load()
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.addWidget(_label(f"<b>shape</b> {tuple(arr.shape)} · <b>dtype</b> {arr.dtype}"))
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    text = str(arr)
    edit.setPlainText(text if len(text) < 5000 else text[:5000] + "\n…(truncated)")
    layout.addWidget(edit)
    return container


def register_builtin_viewers() -> None:
    builtins = {
        "dataframe": _dataframe_viewer,
        "figure": _figure_viewer,
        "html": _html_viewer,
        "text": _text_viewer,
        "dict": _json_viewer,
        "list": _json_viewer,
        "sklearn_model": _model_viewer,
        "ndarray": _ndarray_viewer,
    }
    for name, factory in builtins.items():
        if name not in _VIEWERS:
            _VIEWERS[name] = factory


register_builtin_viewers()
