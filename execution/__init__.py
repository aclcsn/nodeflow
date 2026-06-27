"""Execution subsystem.

Three cooperating pieces, layered bottom-up:

* :mod:`~nodeflow.execution.engine`    Papermill-based single-node execution
  (input injection, parameter injection, output capture). Phase 6.
* :mod:`~nodeflow.execution.dag`       NetworkX DAG scheduler with run modes
  (run node / downstream / all / resume failed). Phase 7.
* :mod:`~nodeflow.execution.cache`     content-hash cache; dirty propagation.
  Phase 8.
"""

from __future__ import annotations

from .cache import CacheEngine
from .dag import DagRunner, NodeOutcome, NodeStatus, RunReport
from .engine import (
    ExecutionEngine,
    ExecutionError,
    ExecutionResult,
)
from .notebook import build_notebook, read_notebook, save_notebook, write_notebook

__all__ = [
    "ExecutionEngine",
    "ExecutionResult",
    "ExecutionError",
    "DagRunner",
    "RunReport",
    "NodeOutcome",
    "NodeStatus",
    "CacheEngine",
    "build_notebook",
    "read_notebook",
    "save_notebook",
    "write_notebook",
]
