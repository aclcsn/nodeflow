"""Blender-Geometry-Nodes-inspired dark theme and per-category node colors."""

from __future__ import annotations

# Category -> node header RGB (Blender-ish palette).
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "Input": (70, 120, 90),
    "Source": (70, 120, 90),
    "Data": (60, 110, 140),
    "Cleaning": (60, 110, 140),
    "Transform": (90, 100, 150),
    "Modeling": (150, 90, 70),
    "Evaluation": (150, 120, 60),
    "Explainability": (120, 80, 150),
    "Report": (110, 110, 70),
    "General": (90, 90, 100),
}

DEFAULT_NODE_COLOR = (90, 90, 100)


def color_for_category(category: str) -> tuple[int, int, int]:
    return CATEGORY_COLORS.get(category, DEFAULT_NODE_COLOR)


# Application-wide dark stylesheet.
DARK_STYLESHEET = """
QWidget { background-color: #2b2b2b; color: #d6d6d6; font-size: 12px; }
QMainWindow::separator { background: #1e1e1e; width: 3px; height: 3px; }
QDockWidget { titlebar-close-icon: none; font-weight: bold; }
QDockWidget::title { background: #383838; padding: 4px 8px; }
QTreeWidget, QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {
    background-color: #232323; border: 1px solid #1e1e1e;
}
QHeaderView::section { background-color: #383838; padding: 3px; border: none; }
QPushButton {
    background-color: #444; border: 1px solid #555; border-radius: 3px; padding: 4px 10px;
}
QPushButton:hover { background-color: #4f4f4f; }
QPushButton:pressed { background-color: #2f7fd0; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #1e1e1e; border: 1px solid #555; border-radius: 3px; padding: 2px 4px;
}
QTabBar::tab { background: #383838; padding: 5px 12px; }
QTabBar::tab:selected { background: #2f7fd0; }
QTabWidget::pane { border: 1px solid #1e1e1e; }
QStatusBar { background: #383838; }
"""
