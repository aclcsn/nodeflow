"""Immutable run + artifact storage.

Layout::

    runs/
      run_001/
        run.json            # run metadata
        Extract/
          _outputs.json     # manifest written by the SDK / store()
          raw.parquet
        Split/
          train_df.parquet
          test_df.parquet
        RF/
          model.joblib
          metrics.parquet

**Immutability:** a run directory is created once and never reused. Allocating a
run id that already exists raises. Within a run, each node owns its own
subdirectory; the SDK (during execution) or :meth:`Run.store` (for tests /
non-notebook nodes) writes artifacts there and maintains the per-node
``_outputs.json`` manifest, which is the single source of truth for restoration.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nodeflow.core.artifact import ArtifactRef
from nodeflow.sdk.context import MANIFEST_NAME
from nodeflow.serialization import registry as default_registry
from nodeflow.serialization.registry import SerializerRegistry

RUN_META_NAME = "run.json"
_RUN_ID_RE = re.compile(r"^run_(\d+)$")


class ArtifactStoreError(RuntimeError):
    """Raised on immutability violations or missing artifacts."""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Run:
    """A single immutable execution directory."""

    def __init__(self, root: Path, registry: SerializerRegistry) -> None:
        self.root = Path(root)
        self.run_id = self.root.name
        self.registry = registry

    # -- node directories -------------------------------------------------
    def node_dir(self, node_id: str, *, create: bool = True) -> Path:
        d = self.root / node_id
        if create:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def has_node(self, node_id: str) -> bool:
        return (self.root / node_id).is_dir()

    def node_ids(self) -> list[str]:
        return sorted(
            p.name
            for p in self.root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    # -- writing ----------------------------------------------------------
    def store(
        self,
        node_id: str,
        name: str,
        value: Any,
        type_name: str | None = None,
        *,
        node_name: str = "",
    ) -> ArtifactRef:
        """Serialize ``value`` into the node dir and update its manifest.

        Mirrors what the SDK does during a notebook run, for tests and for
        nodes that are produced outside a notebook.
        """
        if type_name is None:
            type_name = self.registry.detect(value)
        if type_name is None:
            raise ArtifactStoreError(
                f"cannot determine a serializer for artifact {name!r} "
                f"(type {type(value).__name__}); pass type_name=..."
            )
        nd = self.node_dir(node_id)
        stored = self.registry.write(type_name, value, nd, name)
        self._update_manifest(node_id, name, stored.type, stored.path, stored.metadata, node_name)
        return ArtifactRef(
            node_id=node_id,
            name=name,
            type=stored.type,
            path=str(stored.path),
            metadata=stored.metadata,
        )

    def _update_manifest(
        self,
        node_id: str,
        name: str,
        type_name: str,
        path: Path,
        metadata: dict,
        node_name: str,
    ) -> None:
        nd = self.node_dir(node_id)
        mf = nd / MANIFEST_NAME
        data = json.loads(mf.read_text()) if mf.exists() else {}
        data.setdefault("node_id", node_id)
        if node_name:
            data["node_name"] = node_name
        outputs = data.setdefault("outputs", {})
        outputs[name] = {
            "type": type_name,
            "path": str(Path(path).relative_to(nd)),
            "metadata": metadata,
        }
        mf.write_text(json.dumps(data, indent=2, default=str))

    # -- reading / restoration -------------------------------------------
    def manifest(self, node_id: str) -> dict[str, Any] | None:
        mf = self.root / node_id / MANIFEST_NAME
        return json.loads(mf.read_text()) if mf.exists() else None

    def artifacts(self, node_id: str) -> dict[str, ArtifactRef]:
        """ArtifactRefs for one node, reconstructed from its manifest."""
        data = self.manifest(node_id)
        if not data:
            return {}
        nd = self.root / node_id
        refs: dict[str, ArtifactRef] = {}
        for name, info in data.get("outputs", {}).items():
            refs[name] = ArtifactRef(
                node_id=node_id,
                name=name,
                type=info["type"],
                path=str((nd / info["path"]).resolve()),
                metadata=info.get("metadata", {}),
            )
        return refs

    def artifact(self, node_id: str, name: str) -> ArtifactRef:
        refs = self.artifacts(node_id)
        if name not in refs:
            raise ArtifactStoreError(
                f"no artifact {name!r} for node {node_id!r} in run {self.run_id!r}"
            )
        return refs[name]

    def all_artifacts(self) -> dict[str, dict[str, ArtifactRef]]:
        return {nid: self.artifacts(nid) for nid in self.node_ids() if self.artifacts(nid)}

    def load(self, node_id: str, name: str) -> Any:
        return self.artifact(node_id, name).load(self.registry)

    # -- metadata ---------------------------------------------------------
    def meta(self) -> dict[str, Any]:
        mf = self.root / RUN_META_NAME
        return json.loads(mf.read_text()) if mf.exists() else {}

    def _write_meta(self, **extra: Any) -> None:
        data = self.meta()
        data.update(extra)
        (self.root / RUN_META_NAME).write_text(json.dumps(data, indent=2, default=str))

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Run {self.run_id} ({len(self.node_ids())} nodes)>"


class ArtifactManager:
    """Owns the ``runs/`` tree and allocates immutable runs."""

    def __init__(
        self,
        runs_root: str | Path = "runs",
        registry: SerializerRegistry | None = None,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or default_registry

    # -- run lifecycle ----------------------------------------------------
    def _next_run_id(self) -> str:
        nums = [
            int(m.group(1))
            for p in self.runs_root.iterdir()
            if p.is_dir() and (m := _RUN_ID_RE.match(p.name))
        ]
        return f"run_{(max(nums) + 1) if nums else 1:03d}"

    def create_run(self, run_id: str | None = None) -> Run:
        run_id = run_id or self._next_run_id()
        path = self.runs_root / run_id
        if path.exists():
            raise ArtifactStoreError(
                f"run {run_id!r} already exists; runs are immutable and cannot be reused"
            )
        path.mkdir(parents=True)
        run = Run(path, self.registry)
        run._write_meta(run_id=run_id, created_at=_utcnow())
        return run

    def open_run(self, run_id: str) -> Run:
        path = self.runs_root / run_id
        if not path.is_dir():
            raise ArtifactStoreError(f"no such run: {run_id!r}")
        return Run(path, self.registry)

    def list_runs(self) -> list[str]:
        return sorted(
            p.name for p in self.runs_root.iterdir() if p.is_dir() and _RUN_ID_RE.match(p.name)
        )

    def latest_run(self) -> Run | None:
        runs = self.list_runs()
        return self.open_run(runs[-1]) if runs else None

    def load(self, ref: ArtifactRef) -> Any:
        return ref.load(self.registry)
