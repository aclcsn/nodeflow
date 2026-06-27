"""Subgraphs: group nodes, save them as a reusable unit, re-instantiate later.

A :class:`Subgraph` captures a set of nodes, their *internal* connections, and a
self-contained **interface**:

* exposed **inputs**  = internal input ports with no internal producer,
* exposed **outputs** = internal output ports with no internal consumer.

The interface is computed only from what's inside the group, so a subgraph is
portable: you can extract ``Extract → Clean → Split`` as "Preprocessing", save
it, and instantiate it into any board. Reuse is by **expansion** — the internal
nodes are recreated (with fresh ids) so the existing DAG engine runs them
natively, with no special composite-execution path.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .graph import Connection, NodeInstance, WorkflowGraph
from .spec import NodeSpec, PortSpec


class Subgraph(BaseModel):
    """A reusable group of nodes + internal connections + boundary interface."""

    name: str
    nodes: list[NodeInstance] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    inputs: dict[str, tuple[str, str]] = Field(default_factory=dict)   # exposed -> (node, port)
    outputs: dict[str, tuple[str, str]] = Field(default_factory=dict)  # exposed -> (node, port)

    # -- interface --------------------------------------------------------
    def composite_spec(self) -> NodeSpec:
        """A single-node spec representing the collapsed group (for display)."""
        by_id = {n.id: n for n in self.nodes}
        inputs = {
            name: PortSpec(type=by_id[node].spec.inputs[port].type, required=False)
            for name, (node, port) in self.inputs.items()
        }
        outputs = {
            name: PortSpec(type=by_id[node].spec.outputs[port].type)
            for name, (node, port) in self.outputs.items()
        }
        return NodeSpec(
            name=self.name,
            category="Subgraph",
            description=f"Collapsed group of {len(self.nodes)} nodes",
            inputs=inputs,
            outputs=outputs,
        )

    # -- persistence ------------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(mode="json"), indent=2))
        return path

    @classmethod
    def load(cls, path: str | Path) -> Subgraph:
        return cls.model_validate(json.loads(Path(path).read_text()))


def _compute_interface(
    nodes: list[NodeInstance], connections: list[Connection]
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    fed = {(c.target, c.target_port) for c in connections}
    consumed = {(c.source, c.source_port) for c in connections}
    inputs: dict[str, tuple[str, str]] = {}
    outputs: dict[str, tuple[str, str]] = {}
    for n in nodes:
        for port in n.spec.inputs:
            if (n.id, port) not in fed:
                inputs[f"{n.id}.{port}"] = (n.id, port)
        for port in n.spec.outputs:
            if (n.id, port) not in consumed:
                outputs[f"{n.id}.{port}"] = (n.id, port)
    return inputs, outputs


def extract_subgraph(graph: WorkflowGraph, node_ids: list[str], name: str) -> Subgraph:
    """Build a reusable :class:`Subgraph` from selected nodes of ``graph``."""
    ids = set(node_ids)
    nodes = [graph.node(i) for i in node_ids]
    internal = [
        c for c in graph.connections if c.source in ids and c.target in ids
    ]
    inputs, outputs = _compute_interface(nodes, internal)
    return Subgraph(name=name, nodes=nodes, connections=internal, inputs=inputs, outputs=outputs)


def instantiate_subgraph(
    graph: WorkflowGraph, subgraph: Subgraph, prefix: str = ""
) -> dict[str, str]:
    """Expand ``subgraph`` into ``graph`` with fresh ids. Returns old→new id map."""
    id_map: dict[str, str] = {}
    for node in subgraph.nodes:
        new_id = f"{prefix}{node.id}" if prefix else node.id
        while new_id in graph.nodes:
            new_id += "_copy"
        graph.add_node(node.model_copy(update={"id": new_id}))
        id_map[node.id] = new_id
    for c in subgraph.connections:
        graph.connect(id_map[c.source], c.source_port, id_map[c.target], c.target_port)
    return id_map
