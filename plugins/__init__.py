"""Plugin system.

Plugins extend NodeFlow with custom object types, serializers and output
viewers. A plugin is any importable module exposing a ``register(api)`` callable;
the loader discovers plugins from a directory, a file, or a dotted module name
and hands each one a :class:`~nodeflow.plugins.api.PluginAPI`.

Example plugin::

    def register(api):
        api.register_type("geojson", _dump, _load, extension="geojson",
                          detector=_is_geojson)
        api.register_viewer("geojson", _viewer_factory)
        api.register_node_spec(my_spec)
"""

from __future__ import annotations

from .api import PluginAPI
from .loader import (
    PluginError,
    discover_plugins,
    load_plugin_file,
    load_plugin_module,
)

__all__ = [
    "PluginAPI",
    "PluginError",
    "load_plugin_module",
    "load_plugin_file",
    "discover_plugins",
]
