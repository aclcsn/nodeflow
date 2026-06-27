"""The node canvas: NodeGraphQt view kept in sync with a `WorkflowGraph` model.

NodeGraphQt owns the *visual* graph; NodeFlow owns the *canonical* graph
(:class:`~nodeflow.core.graph.WorkflowGraph`) used for execution, caching and
persistence. The canvas keeps the two in step and routes **interactive** port
connections through the model's type checks — an incompatible drag is rejected
live (the visual link is removed and `connection_rejected` is emitted).
"""

from __future__ import annotations

from NodeGraphQt import NodeGraph
from PySide6.QtCore import QObject, Signal

from nodeflow.core.graph import GraphError, NodeInstance, WorkflowGraph
from nodeflow.core.spec import NodeSpec
from nodeflow.gui.node_factory import NodeLibrary, make_node_class, node_type_id


class Canvas(QObject):
    """Owns a NodeGraphQt graph and mirrors it into a `WorkflowGraph`."""

    connection_rejected = Signal(str)
    graph_changed = Signal()

    def __init__(self, library: NodeLibrary | None = None) -> None:
        super().__init__()
        self.graph = NodeGraph()
        self.library = library or NodeLibrary()
        self.model = WorkflowGraph()
        self._registered: set[str] = set()
        self._counters: dict[str, int] = {}
        self._ng_by_id: dict[str, object] = {}   # node_id -> NodeGraphQt node
        self._id_by_ng: dict[str, str] = {}        # ngnode.id -> node_id
        self._syncing = False

        self.graph.port_connected.connect(self._on_port_connected)
        self.graph.port_disconnected.connect(self._on_port_disconnected)

    @property
    def widget(self):
        return self.graph.widget

    # -- registration -----------------------------------------------------
    def _ensure_registered(self, spec: NodeSpec) -> None:
        type_id = node_type_id(spec)
        if type_id not in self._registered:
            self.graph.register_node(make_node_class(spec))
            self._registered.add(type_id)

    def _new_node_id(self, spec: NodeSpec) -> str:
        base = spec.name.replace(" ", "")
        self._counters[base] = self._counters.get(base, 0) + 1
        node_id = f"{base}_{self._counters[base]}"
        while node_id in self.model.nodes:
            self._counters[base] += 1
            node_id = f"{base}_{self._counters[base]}"
        return node_id

    # -- node lifecycle ---------------------------------------------------
    def add_node(
        self,
        spec_name: str,
        pos: tuple[float, float] = (0.0, 0.0),
        node_id: str | None = None,
        params: dict | None = None,
    ) -> str:
        spec = self.library.get(spec_name)
        self._ensure_registered(spec)
        ng = self.graph.create_node(node_type_id(spec), pos=list(pos))
        node_id = node_id or self._new_node_id(spec)
        ng.set_name(node_id)
        instance = NodeInstance(
            id=node_id,
            spec=spec,
            params={**spec.default_params(), **(params or {})},
            position=tuple(pos),
        )
        self.model.add_node(instance)
        self._ng_by_id[node_id] = ng
        self._id_by_ng[ng.id] = node_id
        return node_id

    def add_instance(self, instance: NodeInstance) -> str:
        """Add a node from an existing :class:`NodeInstance` (preserving id/params/pos)."""
        self._ensure_registered(instance.spec)
        ng = self.graph.create_node(node_type_id(instance.spec), pos=list(instance.position))
        ng.set_name(instance.id)
        self.model.add_node(instance)
        self._ng_by_id[instance.id] = ng
        self._id_by_ng[ng.id] = instance.id
        return instance.id

    def sync_positions(self) -> None:
        """Copy current visual positions back into the model (before saving)."""
        for node_id, ng in self._ng_by_id.items():
            try:
                x, y = ng.pos()
                self.model.node(node_id).position = (float(x), float(y))
            except Exception:
                continue

    def clear(self) -> None:
        for node_id in list(self._ng_by_id):
            self.remove_node(node_id)

    def load_model(self, model: WorkflowGraph) -> None:
        """Replace the displayed graph with ``model`` and rebuild the view."""
        self.model = model
        self.rebuild_view()

    def rebuild_view(self) -> None:
        """Re-sync the NodeGraphQt visuals to match ``self.model`` in place.

        Unlike :meth:`load_model` this does **not** create a new model — it is the
        primitive used after the model is mutated directly (e.g. by collapsing
        nodes into a major node).
        """
        self._syncing = True
        try:
            for ng in list(self._ng_by_id.values()):
                self.graph.delete_node(ng)
            self._ng_by_id.clear()
            self._id_by_ng.clear()
            for inst in self.model.nodes.values():
                self._ensure_registered(inst.spec)
                ng = self.graph.create_node(node_type_id(inst.spec), pos=list(inst.position))
                ng.set_name(inst.id)
                self._ng_by_id[inst.id] = ng
                self._id_by_ng[ng.id] = inst.id
            for c in self.model.connections:
                self._ng_by_id[c.source].outputs()[c.source_port].connect_to(
                    self._ng_by_id[c.target].inputs()[c.target_port]
                )
        finally:
            self._syncing = False
        self.graph_changed.emit()

    def remove_node(self, node_id: str) -> None:
        ng = self._ng_by_id.pop(node_id, None)
        if ng is not None:
            self._id_by_ng.pop(ng.id, None)
            self._syncing = True
            try:
                self.graph.delete_node(ng)
            finally:
                self._syncing = False
        self.model.remove_node(node_id)

    # -- connections ------------------------------------------------------
    def connect(self, source: str, source_port: str, target: str, target_port: str) -> bool:
        """Programmatic connect with type checking. Returns False on mismatch."""
        try:
            self.model.connect(source, source_port, target, target_port)
        except GraphError:
            return False
        self._syncing = True
        try:
            self._ng_by_id[source].outputs()[source_port].connect_to(
                self._ng_by_id[target].inputs()[target_port]
            )
        finally:
            self._syncing = False
        self.graph_changed.emit()
        return True

    def _on_port_connected(self, input_port, output_port) -> None:
        if self._syncing:
            return
        src_id = self._id_by_ng.get(output_port.node().id)
        dst_id = self._id_by_ng.get(input_port.node().id)
        if src_id is None or dst_id is None:
            return
        try:
            self.model.connect(src_id, output_port.name(), dst_id, input_port.name())
        except GraphError as exc:
            # Undo the visual connection the user just made.
            self._syncing = True
            try:
                input_port.disconnect_from(output_port)
            finally:
                self._syncing = False
            self.connection_rejected.emit(str(exc))
            return
        self.graph_changed.emit()

    def _on_port_disconnected(self, input_port, output_port) -> None:
        if self._syncing:
            return
        dst_id = self._id_by_ng.get(input_port.node().id)
        if dst_id is None:
            return
        self.model.disconnect(dst_id, input_port.name())
        self.graph_changed.emit()

    # -- subgraphs --------------------------------------------------------
    def insert_subgraph(self, subgraph, prefix: str = "", offset: tuple[float, float] = (0.0, 0.0)) -> dict:
        """Expand a :class:`Subgraph` onto the canvas with fresh ids."""
        id_map: dict[str, str] = {}
        for node in subgraph.nodes:
            new_id = f"{prefix}{node.id}" if prefix else node.id
            while new_id in self.model.nodes:
                new_id += "_copy"
            pos = (node.position[0] + offset[0], node.position[1] + offset[1])
            self.add_instance(node.model_copy(update={"id": new_id, "position": pos}))
            id_map[node.id] = new_id
        for c in subgraph.connections:
            self.connect(id_map[c.source], c.source_port, id_map[c.target], c.target_port)
        self.graph_changed.emit()
        return id_map

    # -- selection / lookup ----------------------------------------------
    def node_id_for(self, ng_node) -> str | None:
        return self._id_by_ng.get(ng_node.id)

    def instance(self, node_id: str) -> NodeInstance:
        return self.model.node(node_id)

    def selected_node_ids(self) -> list[str]:
        return [
            self._id_by_ng[n.id]
            for n in self.graph.selected_nodes()
            if n.id in self._id_by_ng
        ]
