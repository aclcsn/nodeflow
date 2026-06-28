"""Single-node execution via Papermill.

The engine turns a (spec, run, node, inputs, params) tuple into one immutable
node execution:

1. Build a :class:`NodeContext` (inputs as references, merged params, declared
   output types) and write it next to the node's outputs.
2. Point the kernel at that context via the ``NODEFLOW_CONTEXT`` env var and run
   the notebook with Papermill — parameters are *also* injected as notebook
   variables for transparency.
3. The notebook (pure function) reads ``inputs``/``params`` and assigns
   ``outputs``; the SDK serializes each output immediately into the node dir.
4. Read the node's manifest back into :class:`ArtifactRef` objects.

Notebook code contains **no file paths** — everything flows through the context.
"""

from __future__ import annotations

import os
import re
import time
import traceback as _tb
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nodeflow.artifacts.manager import ArtifactManager, Run
from nodeflow.core.artifact import ArtifactRef
from nodeflow.core.spec import NodeSpec
from nodeflow.sdk.context import ENV_VAR, InputRef, NodeContext, OutputSpec
from nodeflow.serialization.registry import SerializerRegistry

CONTEXT_NAME = "_context.json"
EXECUTED_NOTEBOOK_NAME = "executed.ipynb"

# Kernel tracebacks come back with ANSI colour codes; strip them so the stored
# error/traceback reads cleanly in logs.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", text)


class ExecutionError(RuntimeError):
    """Raised for *setup* failures (missing notebook, bad spec). Notebook
    runtime failures are reported via :class:`ExecutionResult`, not raised."""


@dataclass
class ExecutionResult:
    """The outcome of executing one node."""

    node_id: str
    run_id: str
    success: bool
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    executed_notebook: Path | None = None
    context_path: Path | None = None
    duration_s: float = 0.0
    error: str | None = None
    traceback: str | None = None

    def __bool__(self) -> bool:
        return self.success


class ExecutionEngine:
    """Executes individual nodes' notebooks with Papermill."""

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        *,
        base_dir: str | Path | None = None,
        kernel_name: str = "nodeflow",
        timeout: int = 600,
        registry: SerializerRegistry | None = None,
    ) -> None:
        self.artifacts = artifact_manager
        self.base_dir = Path(base_dir) if base_dir else None
        self.kernel_name = kernel_name
        self.timeout = timeout
        self.registry = registry or artifact_manager.registry

    # -- helpers ----------------------------------------------------------
    def resolve_notebook(self, spec: NodeSpec) -> Path:
        if not spec.notebook:
            raise ExecutionError(f"node spec {spec.name!r} has no 'notebook' to execute")
        nb = Path(spec.notebook)
        if not nb.is_absolute() and self.base_dir is not None:
            nb = self.base_dir / nb
        if not nb.exists():
            raise ExecutionError(f"notebook not found for node {spec.name!r}: {nb}")
        return nb

    def build_context(
        self,
        spec: NodeSpec,
        node_dir: Path,
        node_id: str,
        inputs: dict[str, ArtifactRef],
        params: dict[str, Any],
    ) -> NodeContext:
        return NodeContext(
            node_id=node_id,
            node_name=spec.name,
            run_dir=str(node_dir),
            inputs={name: InputRef(**ref.as_input()) for name, ref in inputs.items()},
            params=params,
            outputs={name: OutputSpec(type=port.type) for name, port in spec.outputs.items()},
        )

    # -- execution --------------------------------------------------------
    def execute_node(
        self,
        spec: NodeSpec,
        run: Run,
        node_id: str,
        inputs: dict[str, ArtifactRef] | None = None,
        params: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        import papermill as pm
        from papermill.exceptions import PapermillExecutionError

        inputs = inputs or {}
        merged_params = {**spec.default_params(), **(params or {})}
        self._check_required_inputs(spec, inputs)

        nb_in = self.resolve_notebook(spec)
        node_dir = run.node_dir(node_id)
        ctx = self.build_context(spec, node_dir, node_id, inputs, merged_params)
        ctx_path = node_dir / CONTEXT_NAME
        ctx.to_file(ctx_path)
        nb_out = node_dir / EXECUTED_NOTEBOOK_NAME

        previous_env = os.environ.get(ENV_VAR)
        os.environ[ENV_VAR] = str(ctx_path)
        start = time.perf_counter()
        success, error, tb = True, None, None
        try:
            pm.execute_notebook(
                str(nb_in),
                str(nb_out),
                parameters=merged_params,
                kernel_name=self.kernel_name,
                progress_bar=False,
                log_output=False,
                execution_timeout=self.timeout,
                cwd=str(node_dir),
            )
        except PapermillExecutionError as exc:
            success = False
            error = _clean(f"{exc.ename}: {exc.evalue}")
            raw_tb = "\n".join(exc.traceback) if getattr(exc, "traceback", None) else str(exc)
            tb = _clean(raw_tb)
        except Exception as exc:  # kernel start failure, timeout, etc.
            success = False
            error = _clean(str(exc))
            tb = _clean(_tb.format_exc())
        finally:
            duration = time.perf_counter() - start
            if previous_env is None:
                os.environ.pop(ENV_VAR, None)
            else:
                os.environ[ENV_VAR] = previous_env

        # Manifested outputs exist whether or not the run fully succeeded
        # (partial outputs survive a mid-notebook error).
        artifacts = run.artifacts(node_id)
        return ExecutionResult(
            node_id=node_id,
            run_id=run.run_id,
            success=success,
            artifacts=artifacts,
            executed_notebook=nb_out if nb_out.exists() else None,
            context_path=ctx_path,
            duration_s=duration,
            error=error,
            traceback=tb,
        )

    @staticmethod
    def _check_required_inputs(spec: NodeSpec, inputs: dict[str, ArtifactRef]) -> None:
        missing = [name for name in spec.required_inputs() if name not in inputs]
        if missing:
            raise ExecutionError(
                f"node {spec.name!r} is missing required inputs: {', '.join(missing)}"
            )
