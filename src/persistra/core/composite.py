"""
src/persistra/core/composite.py

Composite (sub-graph) nodes and iterator (loop) nodes.

CompositeNode wraps an internal Project and exposes selected sockets and
parameters to the parent graph.

IteratorNode repeatedly executes a CompositeNode body in either
fixed-count or convergence mode.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Type

import numpy as np

from persistra.core.objects import DataWrapper, Parameter, IntParam, FloatParam, ChoiceParam
from persistra.core.project import Node, NodeState, Operation, Project, Socket
from persistra.core.types import AnyType


# ---------------------------------------------------------------------------
# Composite operation (no-op — the CompositeNode drives execution)
# ---------------------------------------------------------------------------

class CompositeOperation(Operation):
    """Placeholder operation class used by CompositeNode."""

    name = "Composite"
    description = "Encapsulates a sub-graph."
    category = "Composite"

    def execute(self, inputs, params, cancel_event=None):
        # Execution is handled by CompositeNode.compute()
        raise RuntimeError("CompositeOperation.execute() should not be called directly")


# ---------------------------------------------------------------------------
# CompositeNode (§4.4)
# ---------------------------------------------------------------------------

class CompositeNode(Node):
    """A node that contains an internal sub-graph.

    Parameters
    ----------
    sub_project : Project
        The internal graph.
    exposed_inputs : list of (internal_node, socket_name)
        Internal *input* sockets that are promoted to the composite's inputs.
    exposed_outputs : list of (internal_node, socket_name)
        Internal *output* sockets that are promoted to the composite's outputs.
    exposed_params : list of (internal_node, param_name, external_label)
        Internal parameters surfaced on the composite node.
    """

    def __init__(
        self,
        sub_project: Project,
        exposed_inputs: Optional[List[Tuple[Node, str]]] = None,
        exposed_outputs: Optional[List[Tuple[Node, str]]] = None,
        exposed_params: Optional[List[Tuple[Node, str, str]]] = None,
    ):
        # We bypass the normal Node.__init__ socket-building because we
        # generate sockets from the sub-graph's exposed definitions.
        super().__init__(operation_cls=CompositeOperation)

        self.sub_project = sub_project
        self.exposed_inputs = exposed_inputs or []
        self.exposed_outputs = exposed_outputs or []
        self.exposed_params = exposed_params or []

        # Re-build external sockets from exposed definitions
        self.input_sockets.clear()
        for internal_node, sock_name in self.exposed_inputs:
            internal_sock = internal_node.get_input_socket(sock_name)
            if internal_sock is None:
                raise KeyError(
                    f"Internal node {internal_node.operation.name} has no input '{sock_name}'"
                )
            self.input_sockets.append(
                Socket(self, sock_name, internal_sock.socket_type, is_input=True)
            )

        self.output_sockets.clear()
        for internal_node, sock_name in self.exposed_outputs:
            internal_sock = internal_node.get_output_socket(sock_name)
            if internal_sock is None:
                raise KeyError(
                    f"Internal node {internal_node.operation.name} has no output '{sock_name}'"
                )
            self.output_sockets.append(
                Socket(self, sock_name, internal_sock.socket_type, is_input=False)
            )

        # Surface internal parameters
        self.parameters = []
        for internal_node, param_name, ext_label in self.exposed_params:
            for p in internal_node.parameters:
                if p.name == param_name:
                    # Shallow copy with a new label
                    clone = type(p).__new__(type(p))
                    clone.__dict__.update(p.__dict__)
                    clone.label = ext_label
                    self.parameters.append(clone)
                    break

    # -- helpers -----------------------------------------------------------

    def set_inputs(self, values: Dict[str, Any]):
        """Push *values* into the sub-project's exposed input nodes."""
        for (internal_node, sock_name), ext_sock in zip(
            self.exposed_inputs, self.input_sockets
        ):
            if sock_name in values:
                # Inject the value directly as a cached output on a virtual
                # "source" — we set the internal node's upstream result.
                internal_node._cached_outputs[sock_name] = values[sock_name]
                internal_node._is_dirty = False
                internal_node.state = NodeState.VALID

    def invalidate_all(self):
        """Mark every node inside the sub-project as dirty."""
        for node in self.sub_project.nodes:
            node._is_dirty = True
            node._cached_outputs = {}
            node.state = NodeState.DIRTY

    def compute(self) -> Dict[str, Any]:
        """Execute the internal graph and collect exposed outputs."""
        if not self._is_dirty:
            return self._cached_outputs

        self.state = NodeState.COMPUTING

        try:
            # Feed external inputs into the sub-graph
            external_inputs: Dict[str, Any] = {}
            for sock in self.input_sockets:
                if sock.connections:
                    source_sock = sock.connections[0]
                    upstream = source_sock.node.compute()
                    if source_sock.name in upstream:
                        external_inputs[sock.name] = upstream[source_sock.name]

            self.set_inputs(external_inputs)

            # Compute all exposed output nodes
            outputs: Dict[str, Any] = {}
            for internal_node, sock_name in self.exposed_outputs:
                result = internal_node.compute()
                if sock_name in result:
                    outputs[sock_name] = result[sock_name]

            self._cached_outputs = outputs
            self._is_dirty = False
            self.state = NodeState.VALID
            return self._cached_outputs

        except Exception as exc:
            self._error = str(exc)
            self.state = NodeState.ERROR
            raise


# ---------------------------------------------------------------------------
# Iterator operation (placeholder)
# ---------------------------------------------------------------------------

class IteratorOperation(Operation):
    """Placeholder operation class used by IteratorNode."""

    name = "Iterator"
    description = "Repeatedly executes a sub-graph."
    category = "Composite"

    def execute(self, inputs, params, cancel_event=None):
        raise RuntimeError("IteratorOperation.execute() should not be called directly")


# ---------------------------------------------------------------------------
# IteratorNode (§4.3)
# ---------------------------------------------------------------------------

class IteratorNode(Node):
    """A node that repeatedly executes an internal sub-graph.

    Parameters
    ----------
    body : CompositeNode
        The loop body (sub-graph) to execute on each iteration.
    max_iter : int
        Maximum number of iterations.
    tolerance : float
        Convergence tolerance (used when *mode* is ``"converge"``).
    mode : str
        ``"fixed_count"`` or ``"converge"``.
    """

    def __init__(
        self,
        body: CompositeNode,
        max_iter: int = 100,
        tolerance: float = 1e-6,
        mode: str = "fixed_count",
    ):
        super().__init__(operation_cls=IteratorOperation)

        self.body = body
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.mode = mode

        # Mirror the body's exposed sockets
        self.input_sockets = list(body.input_sockets)
        self.output_sockets = list(body.output_sockets)

        # Expose iteration control as parameters
        self.parameters = [
            IntParam("max_iterations", "Max Iterations", default=max_iter, min_val=1, max_val=10000),
            FloatParam("convergence_tolerance", "Tolerance", default=tolerance, min_val=0.0, max_val=1.0),
            ChoiceParam("mode", "Mode", options=["fixed_count", "converge"], default=mode),
        ]

    # -- convergence check -------------------------------------------------

    @staticmethod
    def _has_converged(
        prev: Dict[str, Any], curr: Dict[str, Any], tolerance: float
    ) -> bool:
        """Return True if every output value changed by less than *tolerance*."""
        for key in curr:
            p_val = prev.get(key)
            c_val = curr.get(key)
            if p_val is None or c_val is None:
                return False
            # Support DataWrapper and raw numpy arrays
            p_data = p_val.data if isinstance(p_val, DataWrapper) else p_val
            c_data = c_val.data if isinstance(c_val, DataWrapper) else c_val
            try:
                delta = float(np.linalg.norm(np.asarray(c_data) - np.asarray(p_data)))
                if delta >= tolerance:
                    return False
            except (TypeError, ValueError):
                # Non-numeric data — cannot measure delta; don't converge
                return False
        return True

    # -- execution ---------------------------------------------------------

    def _gather_inputs(self) -> Dict[str, Any]:
        """Collect data from upstream connections into a dict."""
        values: Dict[str, Any] = {}
        for sock in self.input_sockets:
            if sock.connections:
                source_sock = sock.connections[0]
                upstream = source_sock.node.compute()
                if source_sock.name in upstream:
                    values[sock.name] = upstream[source_sock.name]
        return values

    def compute(self) -> Dict[str, Any]:
        if not self._is_dirty:
            return self._cached_outputs

        self.state = NodeState.COMPUTING

        try:
            external_inputs = self._gather_inputs()

            # Read runtime parameter overrides
            param_vals = {p.name: p.value for p in self.parameters}
            max_iter = int(param_vals.get("max_iterations", self.max_iter))
            tol = float(param_vals.get("convergence_tolerance", self.tolerance))
            mode = param_vals.get("mode", self.mode)

            prev_output = None
            result: Dict[str, Any] = {}

            for _i in range(max_iter):
                self.body.set_inputs(external_inputs if prev_output is None else prev_output)
                self.body.invalidate_all()
                result = self.body.compute()

                if mode == "converge" and prev_output is not None:
                    if self._has_converged(prev_output, result, tol):
                        break
                prev_output = result

            self._cached_outputs = result
            self._is_dirty = False
            self.state = NodeState.VALID
            return self._cached_outputs

        except Exception as exc:
            self._error = str(exc)
            self.state = NodeState.ERROR
            raise
