"""Core domain models for NodeFlow.

This package holds the framework-agnostic vocabulary shared by every other
subsystem: node specifications (parsed from YAML), ports, type-compatibility
rules, artifact references, and the workflow graph model. It depends only on
:mod:`nodeflow.serialization` and the standard library — never on the GUI or
execution layers — so it sits near the bottom of the dependency graph.
"""

from __future__ import annotations

from .artifact import ArtifactRef
from .composite import (
    collapse_nodes,
    flat_child_id,
    flatten_graph,
    has_major_nodes,
)
from .graph import (
    Connection,
    GraphError,
    NodeInstance,
    WorkflowGraph,
    types_compatible,
)
from .spec import (
    EnvironmentSpec,
    NodeSpec,
    NodeSpecError,
    ParameterSpec,
    ParameterType,
    PortSpec,
    dump_node_spec,
    load_node_spec,
    parse_node_spec,
)
from .subgraph import (
    Subgraph,
    extract_subgraph,
    instantiate_subgraph,
)
from .workflow import (
    WorkflowDocument,
    load_workflow,
    save_workflow,
)

__all__ = [
    "NodeSpec",
    "NodeSpecError",
    "PortSpec",
    "ParameterSpec",
    "ParameterType",
    "EnvironmentSpec",
    "parse_node_spec",
    "load_node_spec",
    "dump_node_spec",
    "ArtifactRef",
    "WorkflowGraph",
    "NodeInstance",
    "Connection",
    "GraphError",
    "types_compatible",
    "WorkflowDocument",
    "save_workflow",
    "load_workflow",
    "Subgraph",
    "extract_subgraph",
    "instantiate_subgraph",
    "collapse_nodes",
    "flatten_graph",
    "has_major_nodes",
    "flat_child_id",
]
