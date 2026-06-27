"""Content-hash cache with automatic downstream dirty-propagation.

Each node gets a **Merkle-style key**:

    key(n) = H( notebook_bytes(n) + params(n) + { key(src) for each upstream src } )

Because a node's key embeds its upstream nodes' keys, changing any node's
notebook or parameters changes that node's key *and* the key of everything
downstream — so dirty nodes propagate without any explicit traversal.

A run records the key of each node it executed (`_cache.json`). On a cached run,
a node is skipped iff its current key matches the recorded key **and** its
declared outputs are still present on disk.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nodeflow.artifacts.manager import Run
from nodeflow.core.graph import WorkflowGraph

CACHE_FILE = "_cache.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CacheEngine:
    """Computes node cache keys and tracks per-run recorded keys."""

    def __init__(self, graph: WorkflowGraph, base_dir: str | Path | None = None) -> None:
        self.graph = graph
        self.base_dir = Path(base_dir) if base_dir else None

    # -- components -------------------------------------------------------
    def _resolve_notebook(self, node_id: str) -> Path | None:
        spec = self.graph.node(node_id).spec
        if not spec.notebook:
            return None
        nb = Path(spec.notebook)
        if not nb.is_absolute() and self.base_dir is not None:
            nb = self.base_dir / nb
        return nb

    def notebook_hash(self, node_id: str) -> str:
        nb = self._resolve_notebook(node_id)
        if nb is None or not nb.exists():
            return "no-notebook"
        return _sha(nb.read_bytes())

    def params_hash(self, node_id: str) -> str:
        node = self.graph.node(node_id)
        merged = {**node.spec.default_params(), **node.params}
        return _sha(json.dumps(merged, sort_keys=True, default=str).encode())

    # -- merkle key -------------------------------------------------------
    def node_key(self, node_id: str, _memo: dict[str, str] | None = None) -> str:
        memo = _memo if _memo is not None else {}
        if node_id in memo:
            return memo[node_id]
        parts = [self.notebook_hash(node_id), self.params_hash(node_id)]
        for in_port, (src, src_port) in sorted(self.graph.upstream(node_id).items()):
            parts.append(f"{in_port}={self.node_key(src, memo)}:{src_port}")
        key = _sha("|".join(parts).encode())
        memo[node_id] = key
        return key

    def all_keys(self) -> dict[str, str]:
        memo: dict[str, str] = {}
        return {n: self.node_key(n, memo) for n in self.graph.nodes}

    # -- persistence ------------------------------------------------------
    def load_recorded(self, run: Run) -> dict[str, str]:
        f = run.root / CACHE_FILE
        return json.loads(f.read_text()) if f.exists() else {}

    def save_recorded(self, run: Run, recorded: dict[str, str]) -> None:
        (run.root / CACHE_FILE).write_text(json.dumps(recorded, indent=2))

    # -- dirtiness --------------------------------------------------------
    def artifacts_present(self, node_id: str, run: Run) -> bool:
        declared = set(self.graph.node(node_id).spec.outputs)
        if not declared:
            return False  # nothing to reuse; treat as needing a run
        produced = set(run.artifacts(node_id))
        return declared.issubset(produced)

    def is_clean(self, node_id: str, run: Run, recorded: dict[str, str], current: dict[str, str]) -> bool:
        return recorded.get(node_id) == current[node_id] and self.artifacts_present(node_id, run)

    def dirty_nodes(self, run: Run, selected: set[str] | None = None) -> set[str]:
        recorded = self.load_recorded(run)
        current = self.all_keys()
        nodes = selected if selected is not None else set(self.graph.nodes)
        return {n for n in nodes if not self.is_clean(n, run, recorded, current)}
