"""Plugin discovery and loading.

Plugins are plain Python modules with a ``register(api)`` function. They can be
loaded from a dotted module name, a ``.py`` file path, or every ``.py`` file in
a directory.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

from .api import PluginAPI


class PluginError(RuntimeError):
    """Raised when a plugin cannot be loaded or lacks ``register``."""


def _invoke(module: ModuleType, api: PluginAPI, source: str) -> None:
    register = getattr(module, "register", None)
    if not callable(register):
        raise PluginError(f"plugin {source!r} has no callable 'register(api)'")
    register(api)


def load_plugin_module(dotted_name: str, api: PluginAPI) -> ModuleType:
    """Load a plugin given an importable dotted module name."""
    try:
        module = importlib.import_module(dotted_name)
    except Exception as exc:
        raise PluginError(f"could not import plugin {dotted_name!r}: {exc}") from exc
    _invoke(module, api, dotted_name)
    return module


def load_plugin_file(path: str | Path, api: PluginAPI) -> ModuleType:
    """Load a plugin from a ``.py`` file path."""
    path = Path(path)
    if not path.exists():
        raise PluginError(f"plugin file not found: {path}")
    name = f"nodeflow_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PluginError(f"could not load plugin file: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginError(f"error executing plugin {path}: {exc}") from exc
    _invoke(module, api, str(path))
    return module


def discover_plugins(directory: str | Path, api: PluginAPI) -> list[str]:
    """Load every ``*.py`` plugin in ``directory``. Returns loaded file stems."""
    directory = Path(directory)
    loaded: list[str] = []
    if not directory.is_dir():
        return loaded
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        load_plugin_file(path, api)
        loaded.append(path.stem)
    return loaded
