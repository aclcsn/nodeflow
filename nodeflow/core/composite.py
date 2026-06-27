"""Major nodes: collapse subnodes into a container, and flatten for execution.

* :func:`collapse_nodes` groups selected nodes of a board into a single **major
  node**. Its interface is derived from the connections crossing the group
  boundary — crucially, when one external source fed *several* internal nodes,
  those become **one shared** major-node input.
* :func:`flatten_graph` expands every major node back into its subnodes (rewiring
  through the interface) so the existing DAG engine can run the board unchanged.
  Nesting is supported (major nodes inside major nodes).
"""

from __future__ import annotations

from .graph import NodeInstance, WorkflowGraph
from .spec import NodeSpec, PortSpec


def _unique(name: str, taken: set[str]) -> str:
    candidate = name
    i = 1
    while candidate in taken:
        i += 1
        candidate = f"{name}_{i}"
    taken.add(candidate)
    return candidate


def collapse_nodes(graph: WorkflowGraph, node_ids: list[str], name: str) -> str:
    """Collapse ``node_ids`` into a single major node. Returns its id.

    The major node replaces the selected nodes in ``graph``; boundary connections
    are rewired to the new node's interface ports.
    """
    ids = set(node_ids)
    if len(ids) < 1:
        raise ValueError("collapse requires at least one node")
    children = [graph.node(i) for i in node_ids]

    internal = [c for c in graph.connections if c.source in ids and c.target in ids]
    inbound = [c for c in graph.connections if c.target in ids and c.source not in ids]
    outbound = [c for c in graph.connections if c.source in ids and c.target not in ids]
    child_specs = {c.id: c.spec for c in children}

    taken_ports: set[str] = set()
    interface_inputs: dict[str, list[tuple[str, str]]] = {}
    inbound_wires: list[tuple[str, str, str]] = []  # (ext_src, ext_src_port, outer_port)

    # 1) Inbound external edges grouped by source -> one shared outer input.
    src_to_port: dict[tuple[str, str], str] = {}
    for c in inbound:
        key = (c.source, c.source_port)
        if key not in src_to_port:
            outer = _unique(f"{c.source}.{c.source_port}", taken_ports)
            src_to_port[key] = outer
            interface_inputs[outer] = []
            inbound_wires.append((c.source, c.source_port, outer))
        interface_inputs[src_to_port[key]].append((c.target, c.target_port))

    # 2) Internal inputs with no producer (still exposed so they can be wired later).
    fed = {(c.target, c.target_port) for c in internal} | {(c.target, c.target_port) for c in inbound}
    for child in children:
        for port in child.spec.inputs:
            if (child.id, port) not in fed:
                outer = _unique(f"{child.id}.{port}", taken_ports)
                interface_inputs[outer] = [(child.id, port)]

    # 3) Outputs: internal sources that feed outside, plus terminal outputs.
    interface_outputs: dict[str, tuple[str, str]] = {}
    outbound_wires: list[tuple[str, str, str]] = []  # (outer_port, ext_target, ext_target_port)
    out_taken: set[str] = set()
    src_out_port: dict[tuple[str, str], str] = {}
    for c in outbound:
        key = (c.source, c.source_port)
        if key not in src_out_port:
            outer = _unique(f"{c.source}.{c.source_port}", out_taken)
            src_out_port[key] = outer
            interface_outputs[outer] = (c.source, c.source_port)
        outbound_wires.append((src_out_port[key], c.target, c.target_port))

    consumed = {(c.source, c.source_port) for c in internal} | {(c.source, c.source_port) for c in outbound}
    for child in children:
        for port in child.spec.outputs:
            if (child.id, port) not in consumed:
                outer = _unique(f"{child.id}.{port}", out_taken)
                interface_outputs[outer] = (child.id, port)

    # Build the composite display spec (typed from inner ports).
    spec = NodeSpec(
        name=name,
        category="Group",
        description=f"Major node containing {len(children)} subnode(s)",
        inputs={
            outer: PortSpec(type=child_specs[t[0][0]].inputs[t[0][1]].type, required=False)
            for outer, t in interface_inputs.items()
        },
        outputs={
            outer: PortSpec(type=child_specs[node].outputs[port].type)
            for outer, (node, port) in interface_outputs.items()
        },
    )

    avg_x = sum(c.position[0] for c in children) / len(children)
    avg_y = sum(c.position[1] for c in children) / len(children)
    major_id = _unique(name.replace(" ", ""), set(graph.nodes))
    major = NodeInstance(
        id=major_id,
        spec=spec,
        position=(avg_x, avg_y),
        children=[c.model_copy(deep=True) for c in children],
        child_connections=[c.model_copy(deep=True) for c in internal],
        interface_inputs=interface_inputs,
        interface_outputs=interface_outputs,
    )

    # Mutate the graph: drop the originals, add the major node, rewire boundary.
    for nid in node_ids:
        graph.remove_node(nid)
    graph.add_node(major)
    for ext_src, ext_port, outer in inbound_wires:
        graph.connect(ext_src, ext_port, major_id, outer)
    for outer, ext_target, ext_port in outbound_wires:
        graph.connect(major_id, outer, ext_target, ext_port)
    return major_id


def _flatten(graph: WorkflowGraph, prefix: str):
    """Recursive flatten. Returns (flat_graph, in_map, out_map) for this level."""
    flat = WorkflowGraph()
    in_map: dict[tuple[str, str], list[tuple[str, str]]] = {}
    out_map: dict[tuple[str, str], tuple[str, str]] = {}

    for node in graph.nodes.values():
        nid = f"{prefix}{node.id}"
        if not node.is_major:
            flat.add_node(
                node.model_copy(
                    update={
                        "id": nid,
                        "children": [],
                        "child_connections": [],
                        "interface_inputs": {},
                        "interface_outputs": {},
                    }
                )
            )
            for p in node.spec.inputs:
                in_map[(node.id, p)] = [(nid, p)]
            for p in node.spec.outputs:
                out_map[(node.id, p)] = (nid, p)
        else:
            inner = WorkflowGraph()
            for child in node.children:
                inner.add_node(child)
            inner.connections = list(node.child_connections)
            sub_flat, sub_in, sub_out = _flatten(inner, prefix=f"{nid}/")
            for n in sub_flat.nodes.values():
                flat.add_node(n)
            flat.connections.extend(sub_flat.connections)
            for outer, targets in node.interface_inputs.items():
                resolved: list[tuple[str, str]] = []
                for child_id, child_port in targets:
                    resolved.extend(sub_in[(child_id, child_port)])
                in_map[(node.id, outer)] = resolved
            for outer, (child_id, child_port) in node.interface_outputs.items():
                out_map[(node.id, outer)] = sub_out[(child_id, child_port)]

    for c in graph.connections:
        src = out_map[(c.source, c.source_port)]
        for dst in in_map[(c.target, c.target_port)]:
            flat.connect(src[0], src[1], dst[0], dst[1])

    return flat, in_map, out_map


def flatten_graph(graph: WorkflowGraph) -> WorkflowGraph:
    """Expand all major nodes into their subnodes for execution."""
    flat, _, _ = _flatten(graph, prefix="")
    return flat


def has_major_nodes(graph: WorkflowGraph) -> bool:
    return any(n.is_major for n in graph.nodes.values())


def flat_child_id(major_id: str, child_id: str) -> str:
    """The flattened id of a subnode (matches :func:`flatten_graph`)."""
    return f"{major_id}/{child_id}"
