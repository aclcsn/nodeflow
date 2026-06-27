"""The plugin registration API.

A plugin is any module exposing ``register(api)``; the loader hands it a
:class:`PluginAPI` through which it can extend NodeFlow with:

* **custom object types + serializers** (``api.register_type``),
* **custom output viewers** (``api.register_viewer`` — GUI-optional),
* **custom node specs** (``api.register_node_spec``).

The API targets explicit registries so plugins can be loaded into an isolated
context (used by tests) instead of always mutating process globals.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from nodeflow.core.spec import NodeSpec
from nodeflow.library import NodeLibrary
from nodeflow.serialization import registry as global_registry
from nodeflow.serialization.registry import SerializerRegistry


class PluginAPI:
    def __init__(
        self,
        serializers: SerializerRegistry | None = None,
        library: NodeLibrary | None = None,
        *,
        viewers: bool = True,
    ) -> None:
        self.serializers = serializers or global_registry
        self.library = library
        self._use_viewers = viewers
        self.registered_types: list[str] = []
        self.registered_viewers: list[str] = []
        self.registered_nodes: list[str] = []

    def register_type(
        self,
        name: str,
        serialize: Callable[[Any, Any], Any],
        deserialize: Callable[[Any], Any],
        extension: str,
        *,
        detector: Callable[[Any], bool] | None = None,
        description: str = "",
    ) -> None:
        self.serializers.register(
            name, serialize, deserialize, extension,
            detector=detector, description=description, overwrite=True,
        )
        self.registered_types.append(name)

    def register_viewer(self, type_name: str, factory: Callable) -> None:
        if not self._use_viewers:
            return
        try:
            from nodeflow.gui.viewers import register_viewer

            register_viewer(type_name, factory, overwrite=True)
            self.registered_viewers.append(type_name)
        except Exception as exc:  # GUI not available
            warnings.warn(f"viewer for {type_name!r} not registered: {exc}", stacklevel=2)

    def register_node_spec(self, spec: NodeSpec) -> None:
        if self.library is not None:
            self.library.add(spec)
        self.registered_nodes.append(spec.name)

    def summary(self) -> dict[str, list[str]]:
        return {
            "types": list(self.registered_types),
            "viewers": list(self.registered_viewers),
            "nodes": list(self.registered_nodes),
        }
