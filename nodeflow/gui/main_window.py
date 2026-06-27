"""The NodeFlow main window: Blender-style docked layout.

Layout:

    ┌──────────┬───────────────────────────┬───────────────┐
    │ Library  │                           │ Properties /  │
    │ (left)   │      Node canvas          │ Outputs (right)│
    │          │      (center)             │               │
    ├──────────┴───────────────────────────┴───────────────┤
    │                     Logs (bottom)                      │
    └────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QSplitter,
    QTabWidget,
)

from nodeflow.artifacts import ArtifactManager
from nodeflow.execution import CacheEngine, DagRunner, ExecutionEngine, RunReport
from nodeflow.gui.canvas import Canvas
from nodeflow.gui.node_factory import NodeLibrary
from nodeflow.gui.panels import FilesPanel, LibraryPanel, LogPanel, OutputsPanel, PropertiesPanel


class ExecutionWorker(QThread):
    """Runs a DAG callable off the UI thread."""

    finished_report = Signal(object)
    failed = Signal(str)

    def __init__(self, run_callable) -> None:
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            report = self._run_callable()
            self.finished_report.emit(report)
        except Exception as exc:  # surface to the UI rather than crashing the thread
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(
        self,
        project_dir: str | Path | None = None,
        library: NodeLibrary | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("NodeFlow")
        self.resize(1400, 880)

        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.library = library or NodeLibrary()

        self.artifacts = ArtifactManager(self.project_dir / "runs")
        self.engine = ExecutionEngine(self.artifacts, base_dir=self.project_dir)

        # Center: canvas
        self.canvas = Canvas(self.library)
        self.setCentralWidget(self.canvas.widget)

        # Panels
        self.library_panel = LibraryPanel(self.library)
        self.files_panel = FilesPanel()
        self.properties_panel = PropertiesPanel()
        self.outputs_panel = OutputsPanel()
        self.log_panel = LogPanel()
        self._build_docks()
        self._build_menu()

        # Signals
        self.library_panel.add_requested.connect(self.add_node)
        self.library_panel.edit_template_requested.connect(self.edit_template)
        self.files_panel.upload_requested.connect(self.upload_files)
        self.files_panel.file_activated.connect(self._add_file_node)
        self.canvas.connection_rejected.connect(
            lambda msg: self.log(f"Connection rejected: {msg}")
        )
        self._connect_selection_signal()
        self._setup_node_menu()
        self._setup_shortcuts()
        self._place_offset = 0
        self._worker: ExecutionWorker | None = None
        self._major_views: list = []  # keep references to open drill-down windows

        self.statusBar().showMessage("Ready")
        self.log(f"NodeFlow ready · project: {self.project_dir}")

    # -- construction -----------------------------------------------------
    def _build_docks(self) -> None:
        left = QDockWidget("Library", self)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.library_panel)
        split.addWidget(self.files_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        left.setWidget(split)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)

        right = QDockWidget("Inspector", self)
        tabs = QTabWidget()
        tabs.addTab(self.properties_panel, "Properties")
        tabs.addTab(self.outputs_panel, "Outputs")
        right.setWidget(tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, right)
        self._right_tabs = tabs

        bottom = QDockWidget("Logs", self)
        bottom.setWidget(self.log_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom)

    def _build_menu(self) -> None:
        run_menu = self.menuBar().addMenu("&Run")
        run_menu.addAction("Run All", self.run_all)
        run_menu.addAction("Run Downstream of Selected", self.run_downstream_selected)
        run_menu.addAction("Run Selected Node", self.run_selected_node)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("Open Workflow…", self.open_workflow_dialog)
        file_menu.addAction("Save Workflow…", self.save_workflow_dialog)
        file_menu.addSeparator()
        file_menu.addAction("Upload a File…", lambda: self.upload_files())
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        node_menu = self.menuBar().addMenu("&Node")
        node_menu.addAction("Rename…", self.rename_selected)
        node_menu.addAction("Edit Notebook…", self.edit_selected_notebook)
        node_menu.addAction("Expand Major Node", self.expand_selected_major)
        node_menu.addSeparator()
        node_menu.addAction("Delete", self.delete_selected)

        graph_menu = self.menuBar().addMenu("Grap&h")
        graph_menu.addAction("Group Selected into Major Node…", self.group_into_major_dialog)
        graph_menu.addSeparator()
        graph_menu.addAction("Group Selected → Save Subgraph…", self.save_subgraph_dialog)
        graph_menu.addAction("Insert Subgraph…", self.insert_subgraph_dialog)

        git_menu = self.menuBar().addMenu("&Git")
        git_menu.addAction("Commit…", self.git_commit_dialog)
        git_menu.addAction("Pull", self.git_pull)
        git_menu.addAction("Push", self.git_push)
        git_menu.addAction("Branch…", self.git_branch_dialog)
        git_menu.addAction("History", self.git_show_history)

    def _connect_selection_signal(self) -> None:
        graph = self.canvas.graph
        for sig_name in ("node_selection_changed", "node_selected"):
            sig = getattr(graph, sig_name, None)
            if sig is not None:
                try:
                    sig.connect(lambda *a: self._on_selection_changed())
                    return
                except Exception:
                    continue

    def _setup_shortcuts(self) -> None:
        """Delete / Backspace remove the selected node(s) when the canvas has focus."""
        self._shortcuts = []
        for key in (Qt.Key_Delete, Qt.Key_Backspace):
            sc = QShortcut(QKeySequence(key), self.canvas.widget)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self.delete_selected)
            self._shortcuts.append(sc)

    # -- actions ----------------------------------------------------------
    def add_node(self, spec_name: str) -> str:
        self._place_offset += 40
        node_id = self.canvas.add_node(spec_name, pos=(self._place_offset, self._place_offset))
        self._ensure_node_menu()
        self.log(f"Added node {node_id} ({spec_name})")
        return node_id

    def _on_selection_changed(self) -> None:
        ids = self.canvas.selected_node_ids()
        if ids:
            self.properties_panel.show_node(self.canvas.instance(ids[0]))
            self._refresh_outputs(ids[0])
        else:
            self.properties_panel.clear()
            self.outputs_panel.show_message("Select a node to see its outputs.")

    def _refresh_outputs(self, node_id: str) -> None:
        """Show the most recent run's artifacts for ``node_id``, if any.

        For a major node, the interface outputs are pulled from the flattened
        subnode artifacts.
        """
        run = self.artifacts.latest_run()
        if run is None:
            self.outputs_panel.show_artifacts({})
            return
        inst = self.canvas.model.nodes.get(node_id)
        if inst is not None and inst.is_major:
            refs = {}
            for outer, (child, port) in inst.interface_outputs.items():
                child_refs = run.artifacts(f"{node_id}/{child}")
                if port in child_refs:
                    refs[outer] = child_refs[port]
            self.outputs_panel.show_artifacts(refs)
        else:
            self.outputs_panel.show_artifacts(run.artifacts(node_id))

    def log(self, message: str) -> None:
        self.log_panel.log(message)

    # -- per-node "⋯" actions ---------------------------------------------
    def _setup_node_menu(self) -> None:
        """Initialize tracking for the per-node right-click ``⋯`` actions.

        NodeGraphQt's node context menu is keyed by node *type*, so commands are
        registered lazily for each type as it appears (see :meth:`_ensure_node_menu`).
        The same actions are always reachable from the menubar **Node** menu.
        """
        self._node_menu_types: set[str] = set()
        self._ensure_node_menu()

    def _node_command(self, handler):
        def _command(graph, node):  # NodeGraphQt passes (graph, node)
            node_id = self.canvas.node_id_for(node)
            if node_id is not None:
                handler(node_id)
        return _command

    def _ensure_node_menu(self) -> None:
        """Register the ``⋯`` right-click commands for any new node types."""
        try:
            menu = self.canvas.graph.get_context_menu("nodes")
        except Exception:
            return
        for type_id in list(getattr(self.canvas, "_registered", set())):
            if type_id in self._node_menu_types:
                continue
            try:
                menu.add_command(
                    "⋯ Rename…", self._node_command(self.rename_dialog), node_type=type_id
                )
                menu.add_command(
                    "⋯ Edit Notebook…", self._node_command(self.open_notebook_editor),
                    node_type=type_id,
                )
                menu.add_command(
                    "⋯ Expand (Major Node)", self._node_command(self.expand_major_node),
                    node_type=type_id,
                )
                menu.add_command(
                    "⋯ Delete", self._node_command(self.delete_node), node_type=type_id
                )
            except Exception:
                continue
            self._node_menu_types.add(type_id)

    def edit_selected_notebook(self) -> None:
        ids = self.canvas.selected_node_ids()
        if ids:
            self.open_notebook_editor(ids[0])
        else:
            self.log("Select a node to edit its notebook.")

    def expand_selected_major(self) -> None:
        ids = self.canvas.selected_node_ids()
        if ids:
            self.expand_major_node(ids[0])
        else:
            self.log("Select a major node to expand.")

    # -- remove / rename nodes (Feature 1 & 3) ----------------------------
    def delete_node(self, node_id: str) -> None:
        self.canvas.remove_node(node_id)
        if not self.canvas.selected_node_ids():
            self.properties_panel.clear()
            self.outputs_panel.show_message("Select a node to see its outputs.")
        self.log(f"Deleted node {node_id!r}")

    def delete_selected(self) -> None:
        ids = self.canvas.selected_node_ids()
        if not ids:
            self.log("Select a node to delete.")
            return
        for node_id in ids:
            self.canvas.remove_node(node_id)
        self.properties_panel.clear()
        self.outputs_panel.show_message("Select a node to see its outputs.")
        self.log(f"Deleted {len(ids)} node(s).")

    def rename_node(self, node_id: str, new_name: str) -> None:
        self.canvas.rename(node_id, new_name)
        if self.canvas.selected_node_ids() == [node_id]:
            self.properties_panel.show_node(self.canvas.instance(node_id))
        self.log(f"Renamed {node_id} to {new_name!r}")

    def rename_dialog(self, node_id: str) -> None:
        from PySide6.QtWidgets import QInputDialog

        inst = self.canvas.instance(node_id)
        name, ok = QInputDialog.getText(self, "Rename Node", "New name:", text=inst.label)
        if ok and name:
            self.rename_node(node_id, name)

    def rename_selected(self) -> None:
        ids = self.canvas.selected_node_ids()
        if ids:
            self.rename_dialog(ids[0])
        else:
            self.log("Select a node to rename.")

    # -- file inputs (Feature 2) ------------------------------------------
    def upload_files(self, paths: list[str] | None = None) -> list[str]:
        """Copy files into the project and add a source node for each."""
        import shutil

        if paths is None:
            from PySide6.QtWidgets import QFileDialog

            paths, _ = QFileDialog.getOpenFileNames(
                self, "Upload Files", str(self.project_dir), "All Files (*)"
            )
        if not paths:
            return []
        files_dir = self.project_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        added: list[str] = []
        for src in paths:
            src = Path(src)
            dest = files_dir / src.name
            try:
                if src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
            except Exception as exc:
                self.log(f"Could not copy {src.name}: {exc}")
                continue
            self.files_panel.add_file(str(dest))
            added.append(self._add_file_node(str(dest)))
        if added:
            self.log(f"Uploaded {len(added)} file(s).")
        return added

    def _ensure_loader_notebooks(self) -> None:
        from nodeflow.execution.notebook import save_notebook

        nb_dir = self.project_dir / "notebooks"
        csv_nb = nb_dir / "_load_csv.ipynb"
        if not csv_nb.exists():
            save_notebook(
                ["import pandas as pd\nfrom nodeflow import outputs, params\n"
                 "outputs.data = pd.read_csv(params.path)"],
                csv_nb, parameters_cell='path = ""',
            )
        text_nb = nb_dir / "_load_text.ipynb"
        if not text_nb.exists():
            save_notebook(
                ["from nodeflow import outputs, params\n"
                 "with open(params.path, encoding='utf-8', errors='replace') as fh:\n"
                 "    outputs.text = fh.read()"],
                text_nb, parameters_cell='path = ""',
            )

    def _add_file_node(self, file_path: str) -> str:
        from nodeflow.core.graph import NodeInstance
        from nodeflow.core.spec import NodeSpec, ParameterSpec, ParameterType, PortSpec

        self._ensure_loader_notebooks()
        path = Path(file_path)
        if path.suffix.lower() == ".csv":
            spec = NodeSpec(
                name=path.name, category="Files", notebook="notebooks/_load_csv.ipynb",
                description=f"CSV file: {path.name}",
                outputs={"data": PortSpec(type="dataframe")},
                parameters={"path": ParameterSpec(type=ParameterType.STR, default=str(path))},
            )
        else:
            spec = NodeSpec(
                name=path.name, category="Files", notebook="notebooks/_load_text.ipynb",
                description=f"Text/script file: {path.name}",
                outputs={"text": PortSpec(type="text")},
                parameters={"path": ParameterSpec(type=ParameterType.STR, default=str(path))},
            )
        self._place_offset += 40
        node_id = self.canvas.unique_node_id(path.stem)
        inst = NodeInstance(
            id=node_id, spec=spec, params={"path": str(path)},
            position=(self._place_offset, self._place_offset),
        )
        self.canvas.add_instance(inst)
        self.canvas.rename(node_id, path.name)
        self._ensure_node_menu()
        self.log(f"Added file node {path.name}")
        return node_id

    # -- edit a library template (Feature 4 ⋯ button) ---------------------
    def edit_template(self, spec_name: str) -> None:
        from nodeflow.execution.notebook import read_notebook, save_notebook
        from nodeflow.gui.notebook_editor import NotebookEditorDialog

        spec = self.library.get(spec_name)
        if not spec.notebook:
            self.log(f"{spec_name} has no notebook template to edit.")
            return
        nb_path = self.project_dir / spec.notebook
        if not nb_path.exists():
            self.log(f"Template notebook not found: {nb_path}")
            return
        params, code = read_notebook(nb_path)
        dlg = NotebookEditorDialog(f"{spec_name} (template)", params, code, self)
        if dlg.exec() and dlg.saved:
            p, c = dlg.result_cells()
            save_notebook(c, nb_path, parameters_cell=p)
            self.log(f"Updated template notebook for {spec_name!r}")

    # -- editable notebooks (Feature 2) -----------------------------------
    def _resolve_notebook(self, inst):
        if not inst.spec.notebook:
            return None
        p = Path(inst.spec.notebook)
        return p if p.is_absolute() else self.project_dir / p

    def open_notebook_editor(self, node_id: str) -> None:
        from nodeflow.execution.notebook import read_notebook
        from nodeflow.gui.notebook_editor import NotebookEditorDialog

        inst = self.canvas.instance(node_id)
        nb_path = self._resolve_notebook(inst)
        if nb_path is None or not nb_path.exists():
            self.log(f"Node {node_id} has no notebook to edit.")
            return
        params, code = read_notebook(nb_path)
        dlg = NotebookEditorDialog(inst.label, params, code, self)
        if dlg.exec() and dlg.saved:
            p, c = dlg.result_cells()
            self.edit_node_notebook(node_id, p, c)

    def edit_node_notebook(self, node_id: str, parameters_cell: str, code_cells: list[str]):
        """Write an edited, per-node notebook and point the node at it."""
        from nodeflow.execution.notebook import save_notebook

        inst = self.canvas.instance(node_id)
        new_rel = f"notebooks/{node_id}.ipynb"
        out = save_notebook(
            code_cells, self.project_dir / new_rel, parameters_cell=parameters_cell
        )
        # Replace this node's spec with an independent copy pointing at its own
        # notebook, so the shared template / sibling instances are untouched.
        inst.spec = inst.spec.model_copy(update={"notebook": new_rel})
        self.log(f"Saved edited notebook for {node_id} → {new_rel}")
        if self.canvas.selected_node_ids() == [node_id]:
            self.properties_panel.show_node(inst)
        return out

    # -- major nodes / subnodes (Feature 1) -------------------------------
    def group_into_major(self, node_ids: list[str], name: str) -> str:
        """Collapse selected board nodes into a single major node."""
        from nodeflow.core import collapse_nodes

        major_id = collapse_nodes(self.canvas.model, list(node_ids), name)
        self.canvas.rebuild_view()
        self.log(f"Grouped {len(node_ids)} nodes into major node {major_id!r}")
        return major_id

    def group_into_major_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        ids = self.canvas.selected_node_ids()
        if len(ids) < 2:
            self.log("Select two or more nodes to group into a major node.")
            return
        name, ok = QInputDialog.getText(self, "Major Node", "Name:", text="Group")
        if ok and name:
            self.group_into_major(ids, name)

    def expand_major_node(self, node_id: str):
        """Open the drill-down view showing a major node's subnodes + outputs."""
        inst = self.canvas.model.nodes.get(node_id)
        if inst is None or not inst.is_major:
            self.log(f"{node_id} is not a major node (nothing to expand).")
            return None
        from nodeflow.gui.major_view import MajorNodeView

        view = MajorNodeView(inst, self.artifacts, parent=self)
        view.show()
        self._major_views.append(view)
        self.log(f"Expanded major node {node_id!r} ({len(inst.children)} subnodes)")
        return view

    # -- execution --------------------------------------------------------
    def _make_runner(self):
        """Build a runner over the board, flattening major nodes for execution."""
        from nodeflow.core import flatten_graph, has_major_nodes

        board = self.canvas.model
        exec_graph = flatten_graph(board) if has_major_nodes(board) else board
        cache = CacheEngine(exec_graph, base_dir=self.project_dir)
        return DagRunner(exec_graph, self.engine, self.artifacts, cache=cache), exec_graph

    def _flat_seeds(self, board_id: str, exec_graph) -> set[str]:
        if board_id in exec_graph.nodes:
            return {board_id}
        prefix = f"{board_id}/"  # a major node -> all of its flattened subnodes
        return {nid for nid in exec_graph.nodes if nid.startswith(prefix)}

    def _start(self, run_callable) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.log("A run is already in progress.")
            return
        self.statusBar().showMessage("Running…")
        worker = ExecutionWorker(run_callable)
        worker.finished_report.connect(self._on_run_finished)
        worker.failed.connect(self._on_run_failed)
        self._worker = worker
        worker.start()

    def run_all(self) -> None:
        runner, _ = self._make_runner()
        self.log("Running all nodes…")
        self._start(lambda: runner.run_all(use_cache=True))

    def run_downstream_selected(self) -> None:
        ids = self.canvas.selected_node_ids()
        if not ids:
            self.log("No node selected.")
            return
        runner, exec_graph = self._make_runner()
        run = self.artifacts.latest_run() or self.artifacts.create_run()
        seeds = self._flat_seeds(ids[0], exec_graph)
        self.log(f"Running downstream of {ids[0]}…")
        self._start(
            lambda: runner.run_selection(seeds, run, use_cache=True, with_descendants=True)
        )

    def run_selected_node(self) -> None:
        ids = self.canvas.selected_node_ids()
        if not ids:
            self.log("No node selected.")
            return
        runner, exec_graph = self._make_runner()
        run = self.artifacts.latest_run() or self.artifacts.create_run()
        seeds = self._flat_seeds(ids[0], exec_graph)
        self.log(f"Running node {ids[0]}…")
        self._start(lambda: runner.run_selection(seeds, run))

    def _on_run_finished(self, report: RunReport) -> None:
        self.statusBar().showMessage("Done")
        summary = (
            f"Run {report.run_id}: "
            f"{len(report.succeeded)} ran, {len(report.cached)} cached, "
            f"{len(report.failed)} failed, {len(report.skipped)} skipped"
        )
        self.log(summary)
        for nid in report.failed:
            outcome = report.outcomes[nid]
            err = outcome.result.error if outcome.result else "unknown error"
            self.log(f"  ✗ {nid}: {err}")
        # Refresh the outputs panel for the currently selected node.
        ids = self.canvas.selected_node_ids()
        if ids:
            self._refresh_outputs(ids[0])

    def _on_run_failed(self, message: str) -> None:
        self.statusBar().showMessage("Error")
        self.log(f"Run error: {message}")

    # -- persistence ------------------------------------------------------
    def save_workflow(self, path) -> None:
        from nodeflow.gui.persistence import save_window

        save_window(self, path)
        self.log(f"Saved workflow: {path}")

    def load_workflow(self, path) -> None:
        from nodeflow.gui.persistence import load_into_window

        load_into_window(self, path)

    def save_workflow_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Workflow", str(self.project_dir / "workflow.json"), "Workflow (*.json)"
        )
        if path:
            self.save_workflow(path)

    def open_workflow_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Open Workflow", str(self.project_dir), "Workflow (*.json)"
        )
        if path:
            self.load_workflow(path)

    # -- git --------------------------------------------------------------
    @property
    def git(self):
        from nodeflow.vcs import GitManager

        if getattr(self, "_git", None) is None:
            self._git = GitManager(self.project_dir)
        return self._git

    def git_init(self):
        from nodeflow.vcs import GitManager

        self._git = GitManager.init(self.project_dir)
        self.log(f"Initialized Git repository at {self.project_dir}")
        return self._git

    def git_commit(self, message: str) -> str | None:
        from nodeflow.vcs import GitError

        try:
            sha = self.git.commit(message)
            self.log(f"Committed {sha[:8]}: {message}")
            return sha
        except GitError as exc:
            self.log(f"Commit failed: {exc}")
            return None

    def git_pull(self) -> None:
        from nodeflow.vcs import GitError

        try:
            self.git.pull()
            self.log("Pulled from origin.")
        except GitError as exc:
            self.log(f"Pull failed: {exc}")

    def git_push(self) -> None:
        from nodeflow.vcs import GitError

        try:
            self.git.push()
            self.log("Pushed to origin.")
        except GitError as exc:
            self.log(f"Push failed: {exc}")

    def git_create_branch(self, name: str) -> None:
        from nodeflow.vcs import GitError

        try:
            self.git.create_branch(name)
            self.log(f"Created and switched to branch {name!r}.")
        except GitError as exc:
            self.log(f"Branch failed: {exc}")

    def git_show_history(self) -> None:
        from nodeflow.vcs import GitError

        try:
            for c in self.git.history(limit=20):
                self.log(f"  {c.short_sha}  {c.date[:10]}  {c.author}: {c.message.splitlines()[0]}")
        except GitError as exc:
            self.log(f"History failed: {exc}")

    def git_commit_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        if not self.git.is_repo():
            self.git_init()
        message, ok = QInputDialog.getText(self, "Commit", "Commit message:")
        if ok and message:
            self.git_commit(message)

    def git_branch_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New Branch", "Branch name:")
        if ok and name:
            self.git_create_branch(name)

    # -- subgraphs --------------------------------------------------------
    def save_subgraph(self, node_ids, path, name: str = "Subgraph"):
        from nodeflow.core.subgraph import extract_subgraph

        sg = extract_subgraph(self.canvas.model, list(node_ids), name)
        sg.save(path)
        self.log(f"Saved subgraph {name!r} ({len(sg.nodes)} nodes) → {path}")
        return sg

    def insert_subgraph(self, path, prefix: str = ""):
        from nodeflow.core.subgraph import Subgraph

        sg = Subgraph.load(path)
        # Make embedded specs available in the library.
        for node in sg.nodes:
            self.library.add(node.spec)
        self.library_panel.refresh()
        id_map = self.canvas.insert_subgraph(sg, prefix=prefix)
        self.log(f"Inserted subgraph {sg.name!r} ({len(id_map)} nodes)")
        return id_map

    def save_subgraph_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QInputDialog

        ids = self.canvas.selected_node_ids()
        if not ids:
            self.log("Select nodes to group into a subgraph.")
            return
        name, ok = QInputDialog.getText(self, "Subgraph name", "Name:", text="Preprocessing")
        if not ok or not name:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Subgraph", str(self.project_dir / f"{name}.subgraph.json"), "Subgraph (*.json)"
        )
        if path:
            self.save_subgraph(ids, path, name)

    def insert_subgraph_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Subgraph", str(self.project_dir), "Subgraph (*.json)"
        )
        if path:
            self.insert_subgraph(path)
