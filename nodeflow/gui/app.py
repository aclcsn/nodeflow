"""GUI bootstrap: build the QApplication and main window, run the event loop."""

from __future__ import annotations

from pathlib import Path

from nodeflow.gui.theme import DARK_STYLESHEET
from nodeflow.library import NodeLibrary


def get_app():
    """Return the singleton QApplication, creating it if needed."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyleSheet(DARK_STYLESHEET)
    return app


def build_library(project_dir: str | Path) -> NodeLibrary:
    """Materialize the built-in templates into ``project_dir`` and load them.

    Any existing ``specs/`` directory is also loaded so user-authored node specs
    appear alongside the built-ins.
    """
    from nodeflow.templates import install_templates

    library = install_templates(project_dir)
    library.load_dir(Path(project_dir) / "specs")
    return library


def run_gui(workflow_path: str | None = None, project_dir: str | Path | None = None) -> int:
    """Launch the desktop application. Returns the Qt exit code."""
    from nodeflow.gui.main_window import MainWindow

    app = get_app()
    project_dir = Path(project_dir) if project_dir else Path.cwd()
    library = build_library(project_dir)
    window = MainWindow(project_dir=project_dir, library=library)

    # Decide which workflow to open: explicit path wins; otherwise let the user
    # choose from a startup dialog (open / new blank / browse).
    if not workflow_path:
        from nodeflow.gui.chooser import WorkflowChooserDialog

        choice, chosen = WorkflowChooserDialog.choose(project_dir)
        if choice == "open" and chosen is not None:
            workflow_path = str(chosen)

    if workflow_path:
        try:
            window.load_workflow(workflow_path)
        except Exception as exc:  # bad/missing file -> start blank, but tell the user
            window.log(f"Could not open {workflow_path}: {exc}")

    window.show()
    return app.exec()
