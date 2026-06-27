"""Immutable run + artifact storage.

The :class:`~nodeflow.artifacts.manager.ArtifactManager` owns the ``runs/`` tree.
Every execution writes to a fresh, append-only run directory; nothing is ever
overwritten. Artifacts are stored by node and addressed by :class:`ArtifactRef`
(path + type + metadata), never held in memory across nodes.
"""

from __future__ import annotations

from nodeflow.core.artifact import ArtifactRef

from .manager import ArtifactManager, ArtifactStoreError, Run

__all__ = ["ArtifactManager", "Run", "ArtifactStoreError", "ArtifactRef"]
