"""
src/persistra/core/engine.py

Branch-level parallel execution engine with topological planning,
cancellation support, and an auto-compute toggle.
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from persistra.core.project import Node, NodeState, Project


# ---------------------------------------------------------------------------
# Execution result container
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Encapsulates the outcome of executing a single branch."""
    success: bool
    node_id: str
    results: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    traceback: Optional[str] = None
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Execution planner — topological sort + branch detection
# ---------------------------------------------------------------------------

class ExecutionPlanner:
    """Performs topological sort on a Project graph and groups nodes into
    independent branches that can be executed in parallel."""

    @staticmethod
    def topological_sort(project: Project, dirty_only: bool = False) -> List[Node]:
        """Return nodes in execution order (upstream first).

        If *dirty_only* is ``True``, only dirty nodes and their dirty
        descendants are included.
        """
        # Build adjacency info
        in_degree: Dict[str, int] = {}
        adjacency: Dict[str, List[str]] = defaultdict(list)
        node_map: Dict[str, Node] = {}

        nodes = project.nodes
        if dirty_only:
            nodes = [n for n in nodes if n._is_dirty]

        node_ids = {n.id for n in nodes}

        for node in nodes:
            node_map[node.id] = node
            in_degree.setdefault(node.id, 0)
            for out_sock in node.output_sockets:
                for connected_input in out_sock.connections:
                    child = connected_input.node
                    if child.id in node_ids:
                        adjacency[node.id].append(child.id)
                        in_degree[child.id] = in_degree.get(child.id, 0) + 1

        # Kahn's algorithm
        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[Node] = []
        while queue:
            nid = queue.popleft()
            result.append(node_map[nid])
            for child_id in adjacency[nid]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if len(result) != len(nodes):
            raise RuntimeError("Cycle detected in graph — cannot schedule execution")

        return result

    @staticmethod
    def identify_branches(sorted_nodes: Sequence[Node]) -> List[List[Node]]:
        """Partition *sorted_nodes* into independent branches.

        Two nodes belong to the same branch if one is an ancestor/descendant
        of the other.  Branches with no shared ancestry can run in parallel.
        """
        if not sorted_nodes:
            return []

        # Map node → set of ancestor node IDs (including itself)
        ancestor_sets: Dict[str, set] = {}
        for node in sorted_nodes:
            ancestors = {node.id}
            for in_sock in node.input_sockets:
                for conn in in_sock.connections:
                    parent_id = conn.node.id
                    if parent_id in ancestor_sets:
                        ancestors |= ancestor_sets[parent_id]
            ancestor_sets[node.id] = ancestors

        # Group nodes whose ancestor sets overlap
        branches: List[List[Node]] = []
        branch_ancestors: List[set] = []

        for node in sorted_nodes:
            merged = False
            for i, b_anc in enumerate(branch_ancestors):
                if b_anc & ancestor_sets[node.id]:
                    branches[i].append(node)
                    branch_ancestors[i] |= ancestor_sets[node.id]
                    merged = True
                    break
            if not merged:
                branches.append([node])
                branch_ancestors.append(set(ancestor_sets[node.id]))

        return branches


# ---------------------------------------------------------------------------
# Branch task — executes a linear chain of nodes
# ---------------------------------------------------------------------------

class BranchTask:
    """Executes a sequence of nodes in order.

    Designed to be run in a thread.  Checks *cancel_event* between nodes
    so that the user can abort a long-running computation.
    """

    def __init__(self, nodes: List[Node], cancel_event: threading.Event):
        self.nodes = nodes
        self.cancel_event = cancel_event
        self.results: List[ExecutionResult] = []

    def run(self) -> List[ExecutionResult]:
        for node in self.nodes:
            if self.cancel_event.is_set():
                self.results.append(
                    ExecutionResult(
                        success=False,
                        node_id=node.id,
                        error="Cancelled",
                    )
                )
                node.state = NodeState.ERROR
                node._error = "Cancelled"
                break

            node.state = NodeState.COMPUTING
            start = time.monotonic()
            try:
                result = node.compute()
                elapsed = time.monotonic() - start
                self.results.append(
                    ExecutionResult(
                        success=True,
                        node_id=node.id,
                        results=result,
                        elapsed_seconds=elapsed,
                    )
                )
            except Exception as exc:
                elapsed = time.monotonic() - start
                node.state = NodeState.ERROR
                node._error = str(exc)
                self.results.append(
                    ExecutionResult(
                        success=False,
                        node_id=node.id,
                        error=str(exc),
                        traceback=traceback.format_exc(),
                        elapsed_seconds=elapsed,
                    )
                )
                # Stop the branch on error
                break

        return self.results


# ---------------------------------------------------------------------------
# Execution engine — orchestrates planning and dispatch
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """Owns worker threads, plans execution, and dispatches BranchTasks.

    Parameters
    ----------
    max_workers : int, optional
        Maximum number of parallel threads.  ``None`` means *one per branch*.
    """

    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max_workers
        self._cancel_event = threading.Event()
        self._running = False
        self._threads: List[threading.Thread] = []

    # -- public API --------------------------------------------------------

    def run(
        self,
        project: Project,
        dirty_only: bool = False,
    ) -> List[ExecutionResult]:
        """Plan and execute the graph synchronously, returning all results."""
        self._cancel_event.clear()
        self._running = True

        try:
            sorted_nodes = ExecutionPlanner.topological_sort(project, dirty_only=dirty_only)
            branches = ExecutionPlanner.identify_branches(sorted_nodes)

            if not branches:
                return []

            all_results: List[ExecutionResult] = []

            if len(branches) == 1 or self.max_workers == 1:
                # Single-branch fast path — no threads needed
                for branch in branches:
                    task = BranchTask(branch, self._cancel_event)
                    all_results.extend(task.run())
            else:
                # Parallel execution
                result_buckets: List[List[ExecutionResult]] = [[] for _ in branches]

                def _worker(idx: int, nodes: List[Node]):
                    task = BranchTask(nodes, self._cancel_event)
                    result_buckets[idx] = task.run()

                threads: List[threading.Thread] = []
                for idx, branch in enumerate(branches):
                    t = threading.Thread(target=_worker, args=(idx, branch), daemon=True)
                    threads.append(t)

                # Respect max_workers by running in batches
                batch_size = self.max_workers or len(threads)
                for batch_start in range(0, len(threads), batch_size):
                    batch = threads[batch_start : batch_start + batch_size]
                    for t in batch:
                        t.start()
                    for t in batch:
                        t.join()

                for bucket in result_buckets:
                    all_results.extend(bucket)

            return all_results

        finally:
            self._running = False

    def cancel(self):
        """Request cancellation of all running branch tasks."""
        self._cancel_event.set()

    @property
    def is_running(self) -> bool:
        return self._running
