"""Workflow persistence: save/restore an entire board to ``workflow.json``.

A workflow document is self-contained — each node embeds its full
:class:`NodeSpec`, so a board restores without needing the original spec files.
Stored: nodes (id, spec, parameter overrides, title, position) and connections.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .graph import Connection, NodeInstance, WorkflowGraph

WORKFLOW_VERSION = 1


class WorkflowDocument(BaseModel):
    """The serializable form of a :class:`WorkflowGraph`."""

    version: int = WORKFLOW_VERSION
    name: str = "Untitled"
    nodes: list[NodeInstance] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)

    @classmethod
    def from_graph(cls, graph: WorkflowGraph, name: str = "Untitled") -> WorkflowDocument:
        return cls(
            name=name,
            nodes=list(graph.nodes.values()),
            connections=list(graph.connections),
        )

    def to_graph(self) -> WorkflowGraph:
        graph = WorkflowGraph()
        for node in self.nodes:
            graph.add_node(node)
        for conn in self.connections:
            graph.connect(conn.source, conn.source_port, conn.target, conn.target_port)
        return graph


def save_workflow(graph: WorkflowGraph, path: str | Path, *, name: str = "Untitled") -> Path:
    """Write a workflow graph to ``path`` as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = WorkflowDocument.from_graph(graph, name=name)
    path.write_text(json.dumps(doc.model_dump(mode="json"), indent=2))
    return path


def load_workflow(path: str | Path) -> WorkflowGraph:
    """Load and rebuild a workflow graph from ``path``."""
    data = json.loads(Path(path).read_text())
    doc = WorkflowDocument.model_validate(data)
    return doc.to_graph()


def load_document(path: str | Path) -> WorkflowDocument:
    return WorkflowDocument.model_validate(json.loads(Path(path).read_text()))
