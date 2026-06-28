"""Bridge between NodeFlow :class:`NodeSpec`s and NodeGraphQt node classes.

A :class:`NodeLibrary` holds the available node specs (loaded from YAML). The
factory turns each spec into a dynamically-generated ``BaseNode`` subclass whose
ports mirror the spec's inputs/outputs and whose header color comes from its
category.
"""

from __future__ import annotations

import hashlib
import json
import re

from NodeGraphQt import BaseNode, NodeBaseWidget
from PySide6.QtWidgets import QPushButton

from nodeflow.core.spec import NodeSpec
from nodeflow.gui.theme import color_for_category
from nodeflow.library import NodeLibrary  # re-exported for backwards compatibility

__all__ = ["NodeLibrary", "make_node_class", "node_type_id", "class_name_for", "NODE_IDENTIFIER"]

NODE_IDENTIFIER = "nodeflow.nodes"


class _RemoveButtonWidget(NodeBaseWidget):
    """A small ``✕`` button embedded in a node that deletes the node when clicked.

    NodeGraphQt renders nodes itself, so the button sits in the node body rather
    than a literal title-bar corner; deleting goes through ``NodeGraph.delete_node``
    which emits ``nodes_deleted`` so the canvas keeps its model in sync.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.set_name("nf_remove")
        button = QPushButton("✕")  # ✕
        button.setToolTip("Remove this node")
        button.setFixedSize(20, 20)
        button.clicked.connect(self._on_clicked)
        self.set_custom_widget(button)

    def get_value(self):  # required by NodeBaseWidget
        return ""

    def set_value(self, value):  # required by NodeBaseWidget
        pass

    def _on_clicked(self) -> None:
        try:
            node = self.node
            node.graph.delete_node(node)
        except Exception:
            pass


def _structure_hash(spec: NodeSpec) -> str:
    """A short hash of a spec's ports/params.

    Two specs with the same name but different inputs/outputs/parameters hash
    differently, so an edited spec produces a *new* node class instead of reusing
    the cached one (which is what made port edits not show up after a refresh).
    """
    payload = {
        "inputs": [[n, p.type, p.required] for n, p in spec.inputs.items()],
        "outputs": [[n, p.type] for n, p in spec.outputs.items()],
        "params": [[n, str(p.type)] for n, p in spec.parameters.items()],
    }
    blob = json.dumps(payload)  # insertion order preserved, so re-ordering also counts
    return hashlib.md5(blob.encode()).hexdigest()[:8]


def class_name_for(spec: NodeSpec) -> str:
    """A valid Python class name derived from the spec name and its structure."""
    cleaned = re.sub(r"\W+", "_", spec.name).strip("_") or "Node"
    if cleaned[0].isdigit():
        cleaned = f"N_{cleaned}"
    return f"NF_{cleaned}_{_structure_hash(spec)}"


def node_type_id(spec: NodeSpec) -> str:
    return f"{NODE_IDENTIFIER}.{class_name_for(spec)}"


def make_node_class(spec: NodeSpec) -> type[BaseNode]:
    """Dynamically build a NodeGraphQt node class for ``spec``."""

    def __init__(self):  # noqa: N807
        BaseNode.__init__(self)
        for name in spec.inputs:
            self.add_input(name, multi_input=False)
        for name in spec.outputs:
            self.add_output(name, multi_output=True)
        self.set_color(*color_for_category(spec.category))
        try:
            self.add_custom_widget(_RemoveButtonWidget())
        except Exception:
            # The remove button is a convenience; never let it break node creation.
            pass

    return type(
        class_name_for(spec),
        (BaseNode,),
        {
            "__identifier__": NODE_IDENTIFIER,
            "NODE_NAME": spec.name,
            "__init__": __init__,
            "nodeflow_spec": spec,
        },
    )
