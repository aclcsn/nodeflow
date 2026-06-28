"""DAG scheduler.

Drives the :class:`~nodeflow.execution.engine.ExecutionEngine` over a
:class:`~nodeflow.core.graph.WorkflowGraph`, gathering each node's inputs from
the artifacts its upstream nodes produced in the current run.

Run modes:

* **run all** — every node, in topological order, into a fresh run.
* **run downstream** — a node and all its descendants (reusing upstream artifacts
  already present in the run).
* **run node** — a single node (its upstream artifacts must already exist).
* **resume failed** — re-run nodes that did not succeed in a run, plus their
  descendants, reusing successful artifacts.

Failure isolation: when a node fails (or its inputs are unavailable), only its
descendants are skipped; independent branches still run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nodeflow.artifacts.manager import ArtifactManager, Run
from nodeflow.core.artifact import ArtifactRef
from nodeflow.core.graph import WorkflowGraph
from nodeflow.execution.cache import CacheEngine
from nodeflow.execution.engine import ExecutionEngine, ExecutionError, ExecutionResult


class NodeStatus(str, Enum):
    SUCCESS = "success"
    CACHED = "cached"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class NodeOutcome:
    node_id: str
    status: NodeStatus
    result: ExecutionResult | None = None
    reason: str | None = None


@dataclass
class RunReport:
    run_id: str
    outcomes: dict[str, NodeOutcome] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def record(self, outcome: NodeOutcome) -> None:
        self.outcomes[outcome.node_id] = outcome
        self.order.append(outcome.node_id)

    @property
    def success(self) -> bool:
        return all(
            o.status in (NodeStatus.SUCCESS, NodeStatus.CACHED)
            for o in self.outcomes.values()
        )

    def by_status(self, status: NodeStatus) -> list[str]:
        return [nid for nid, o in self.outcomes.items() if o.status is status]

    @property
    def failed(self) -> list[str]:
        return self.by_status(NodeStatus.FAILED)

    @property
    def skipped(self) -> list[str]:
        return self.by_status(NodeStatus.SKIPPED)

    @property
    def succeeded(self) -> list[str]:
        return self.by_status(NodeStatus.SUCCESS)

    @property
    def cached(self) -> list[str]:
        return self.by_status(NodeStatus.CACHED)


class DagRunner:
    """Schedules execution of a workflow graph."""

    def __init__(
        self,
        graph: WorkflowGraph,
        engine: ExecutionEngine,
        artifact_manager: ArtifactManager | None = None,
        cache: CacheEngine | None = None,
    ) -> None:
        self.graph = graph
        self.engine = engine
        self.artifacts = artifact_manager or engine.artifacts
        self.cache = cache

    # -- public run modes -------------------------------------------------
    def run_all(self, run: Run | None = None, use_cache: bool = False) -> RunReport:
        self.graph.validate()
        run = run or self.artifacts.create_run()
        return self._execute(set(self.graph.nodes), run, use_cache=use_cache)

    def run_downstream(
        self, node_id: str, run: Run, use_cache: bool = False
    ) -> RunReport:
        self.graph.validate()
        selected = {node_id} | self.graph.descendants(node_id)
        return self._execute(selected, run, use_cache=use_cache)

    def run_node(self, node_id: str, run: Run) -> RunReport:
        selected = {node_id}
        return self._execute(selected, run)

    def run_selection(
        self, node_ids: set[str], run: Run, use_cache: bool = False, with_descendants: bool = False
    ) -> RunReport:
        """Run an explicit set of nodes (optionally including their descendants)."""
        selected = set(node_ids)
        if with_descendants:
            for nid in list(node_ids):
                selected |= self.graph.descendants(nid)
        return self._execute(selected, run, use_cache=use_cache)

    def resume_failed(self, run: Run, previous: RunReport) -> RunReport:
        # Re-run anything that did not succeed, plus everything downstream of it.
        not_succeeded = {
            nid
            for nid, o in previous.outcomes.items()
            if o.status is not NodeStatus.SUCCESS
        }
        selected: set[str] = set()
        for nid in not_succeeded:
            selected.add(nid)
            selected |= self.graph.descendants(nid)
        return self._execute(selected, run, prior=previous)

    # -- core scheduler ---------------------------------------------------
    def _execute(
        self,
        selected: set[str],
        run: Run,
        prior: RunReport | None = None,
        use_cache: bool = False,
    ) -> RunReport:
        report = RunReport(run_id=run.run_id)
        # Carry forward successful outcomes from a prior report (resume).
        if prior is not None:
            for nid, o in prior.outcomes.items():
                if nid not in selected and o.status is NodeStatus.SUCCESS:
                    report.outcomes[nid] = o

        caching = use_cache and self.cache is not None
        recorded = self.cache.load_recorded(run) if caching else {}
        current_keys = self.cache.all_keys() if caching else {}

        blocked: set[str] = set()
        for node_id in self.graph.subset_order(selected):
            if node_id in blocked:
                report.record(
                    NodeOutcome(node_id, NodeStatus.SKIPPED, reason="upstream failed/skipped")
                )
                blocked |= self.graph.descendants(node_id)
                continue

            # Cache hit: key unchanged and outputs still on disk -> reuse.
            if caching and self.cache.is_clean(node_id, run, recorded, current_keys):
                report.record(NodeOutcome(node_id, NodeStatus.CACHED, reason="up to date"))
                continue

            inputs, missing = self._gather_inputs(node_id, run)
            if missing:
                report.record(
                    NodeOutcome(
                        node_id,
                        NodeStatus.SKIPPED,
                        reason=f"missing upstream artifact(s): {', '.join(missing)}",
                    )
                )
                blocked |= self.graph.descendants(node_id)
                continue

            node = self.graph.node(node_id)
            try:
                result = self.engine.execute_node(
                    node.spec, run, node_id, inputs=inputs, params=node.params
                )
            except ExecutionError as exc:
                # Setup failures (missing notebook, missing required inputs) become a
                # FAILED outcome carrying the message instead of crashing the run.
                result = ExecutionResult(
                    node_id=node_id, run_id=run.run_id, success=False, error=str(exc)
                )
            status = NodeStatus.SUCCESS if result.success else NodeStatus.FAILED
            report.record(NodeOutcome(node_id, status, result=result))
            if result.success:
                if caching:
                    recorded[node_id] = current_keys[node_id]
            else:
                blocked |= self.graph.descendants(node_id)

        if caching:
            self.cache.save_recorded(run, recorded)
        return report

    def _gather_inputs(
        self, node_id: str, run: Run
    ) -> tuple[dict[str, ArtifactRef], list[str]]:
        """Collect ArtifactRefs feeding each connected input port.

        Returns (inputs, missing). ``missing`` lists connected ports whose
        upstream artifact is not present in this run.
        """
        inputs: dict[str, ArtifactRef] = {}
        missing: list[str] = []
        for in_port, (src_node, src_port) in self.graph.upstream(node_id).items():
            refs = run.artifacts(src_node)
            if src_port in refs:
                inputs[in_port] = refs[src_port]
            else:
                missing.append(f"{src_node}.{src_port}")
        return inputs, missing
