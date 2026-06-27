"""The node library — a GUI-free catalog of available node specs.

Lives outside :mod:`nodeflow.gui` so it can be used headlessly (templates,
tests, automation) without importing Qt. The GUI re-exports it.
"""

from __future__ import annotations

from pathlib import Path

from nodeflow.core.spec import NodeSpec, load_node_spec


class NodeLibrary:
    """A catalog of available node specs, grouped by category."""

    def __init__(self) -> None:
        self._specs: dict[str, NodeSpec] = {}

    def add(self, spec: NodeSpec) -> None:
        self._specs[spec.name] = spec

    def add_from_file(self, path: str | Path) -> NodeSpec:
        spec = load_node_spec(path)
        self.add(spec)
        return spec

    def load_dir(self, directory: str | Path) -> int:
        """Load every ``*.yaml`` node spec in a directory. Returns the count."""
        directory = Path(directory)
        count = 0
        if directory.is_dir():
            for path in sorted(directory.glob("*.yaml")):
                try:
                    self.add_from_file(path)
                    count += 1
                except Exception:  # skip malformed specs, keep loading the rest
                    continue
        return count

    def get(self, name: str) -> NodeSpec:
        return self._specs[name]

    def names(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[NodeSpec]:
        return [self._specs[n] for n in self.names()]

    def by_category(self) -> dict[str, list[NodeSpec]]:
        groups: dict[str, list[NodeSpec]] = {}
        for spec in self.specs():
            groups.setdefault(spec.category, []).append(spec)
        return dict(sorted(groups.items()))

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: str) -> bool:
        return name in self._specs
