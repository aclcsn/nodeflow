"""The workflow graph model.

A workflow is a directed acyclic graph of :class:`NodeInstance` objects connected
by :class:`Connection` edges. Each node is an *instance* of a notebook (via its
:class:`~nodeflow.core.spec.NodeSpec`); several instances may share one notebook.

Topology is backed by NetworkX. The model enforces the structural rules the rest
of the system relies on:

* edges reference existing nodes and ports,
* an input port receives **at most one** connection (outputs may fan out),
* connected ports are **type-compatible**,
* the graph is **acyclic**.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

from .spec import NodeSpec


def types_compatible(source_type: str, target_type: str) -> bool:
    """Whether an output of ``source_type`` may feed an input of ``target_type``.

    Currently exact-match; a coercion table can extend this later without
    changing call sites.
    """
    return source_type == target_type


class Connection(BaseModel):
    """A directed edge from one node's output port to another's input port."""

    source: str
    source_port: str
    target: str
    target_port: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.source, self.source_port, self.target, self.target_port)


class NodeInstance(BaseModel):
    """One node on the canvas: a notebook spec + per-instance overrides.

    A node may also be a **major node** that *contains* subnodes. When
    ``children`` is non-empty the node is a group: ``children`` +
    ``child_connections`` describe the inner graph, and the interface maps the
    major node's outer ports to inner subnode ports:

    * ``interface_inputs[outer_port]``  → list of ``(child_id, child_port)`` the
      incoming artifact is delivered to (one outer input may be *shared* across
      several subnodes),
    * ``interface_outputs[outer_port]`` → the single ``(child_id, child_port)``
      the outgoing artifact comes from.
    """

    id: str
    spec: NodeSpec
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    position: tuple[float, float] = (0.0, 0.0)

    # -- major-node (subnode container) fields ----------------------------
    children: list[NodeInstance] = Field(default_factory=list)
    child_connections: list[Connection] = Field(default_factory=list)
    interface_inputs: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)
    interface_outputs: dict[str, tuple[str, str]] = Field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.title or self.spec.name

    @property
    def is_major(self) -> bool:
        return bool(self.children)


NodeInstance.model_rebuild()  # resolve the self-referential ``children`` field


class GraphError(ValueError):
    """Raised on structural violations (bad ports, cycles, type mismatch)."""


class WorkflowGraph:
    """A mutable collection of nodes + connections with validation helpers."""

    def __init__(self) -> None:
        self.nodes: dict[str, NodeInstance] = {}
        self.connections: list[Connection] = []

    # -- construction -----------------------------------------------------
    def add_node(self, node: NodeInstance) -> NodeInstance:
        if node.id in self.nodes:
            raise GraphError(f"duplicate node id: {node.id!r}")
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.connections = [
            c for c in self.connections if c.source != node_id and c.target != node_id
        ]

    def connect(
        self, source: str, source_port: str, target: str, target_port: str
    ) -> Connection:
        conn = Connection(
            source=source, source_port=source_port, target=target, target_port=target_port
        )
        self._validate_connection(conn)
        # An input port accepts a single source: replace any existing edge.
        self.connections = [
            c
            for c in self.connections
            if not (c.target == target and c.target_port == target_port)
        ]
        self.connections.append(conn)
        self._check_acyclic()
        return conn

    def disconnect(self, target: str, target_port: str) -> None:
        self.connections = [
            c
            for c in self.connections
            if not (c.target == target and c.target_port == target_port)
        ]

    # -- validation -------------------------------------------------------
    def _validate_connection(self, conn: Connection) -> None:
        if conn.source not in self.nodes:
            raise GraphError(f"unknown source node {conn.source!r}")
        if conn.target not in self.nodes:
            raise GraphError(f"unknown target node {conn.target!r}")
        if conn.source == conn.target:
            raise GraphError(f"node {conn.source!r} cannot connect to itself")
        src_spec = self.nodes[conn.source].spec
        dst_spec = self.nodes[conn.target].spec
        if conn.source_port not in src_spec.outputs:
            raise GraphError(
                f"node {conn.source!r} has no output port {conn.source_port!r}"
            )
        if conn.target_port not in dst_spec.inputs:
            raise GraphError(
                f"node {conn.target!r} has no input port {conn.target_port!r}"
            )
        s_type = src_spec.output_type(conn.source_port)
        t_type = dst_spec.input_type(conn.target_port)
        if not types_compatible(s_type, t_type):
            raise GraphError(
                f"incompatible types on {conn.source}.{conn.source_port} -> "
                f"{conn.target}.{conn.target_port}: {s_type!r} != {t_type!r}"
            )

    def _check_acyclic(self) -> None:
        g = self.to_networkx()
        if not nx.is_directed_acyclic_graph(g):
            cycle = nx.find_cycle(g)
            raise GraphError(f"connection would create a cycle: {cycle}")

    def validate(self) -> None:
        """Full structural validation of the whole graph."""
        for conn in self.connections:
            self._validate_connection(conn)
        self._check_acyclic()
        # Required inputs must be satisfied by some connection.
        for node_id, node in self.nodes.items():
            connected = {c.target_port for c in self.connections if c.target == node_id}
            missing = [p for p in node.spec.required_inputs() if p not in connected]
            if missing:
                raise GraphError(
                    f"node {node_id!r} has unconnected required inputs: {', '.join(missing)}"
                )

    # -- topology ---------------------------------------------------------
    def to_networkx(self) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_nodes_from(self.nodes)
        for c in self.connections:
            g.add_edge(c.source, c.target)
        return g

    def topological_order(self) -> list[str]:
        return list(nx.topological_sort(self.to_networkx()))

    def ancestors(self, node_id: str) -> set[str]:
        return nx.ancestors(self.to_networkx(), node_id)

    def descendants(self, node_id: str) -> set[str]:
        return nx.descendants(self.to_networkx(), node_id)

    def upstream(self, node_id: str) -> dict[str, tuple[str, str]]:
        """Map each connected input port -> (source_node, source_port)."""
        return {
            c.target_port: (c.source, c.source_port)
            for c in self.connections
            if c.target == node_id
        }

    def predecessors(self, node_id: str) -> set[str]:
        return {c.source for c in self.connections if c.target == node_id}

    # -- misc -------------------------------------------------------------
    def node(self, node_id: str) -> NodeInstance:
        if node_id not in self.nodes:
            raise GraphError(f"no such node: {node_id!r}")
        return self.nodes[node_id]

    def subset_order(self, selected: Iterable[str]) -> list[str]:
        sel = set(selected)
        return [n for n in self.topological_order() if n in sel]

    def __len__(self) -> int:
        return len(self.nodes)
