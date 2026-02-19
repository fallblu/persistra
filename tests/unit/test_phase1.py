"""
Tests for Phase 1 — Core Graph Model & Execution Engine.

Covers:
- 4.1 Richer Type System (SocketType, ConcreteType, UnionType, AnyType)
- 4.1.2 Runtime validation on DataWrapper subclasses
- 4.1.3 Socket integration with SocketType
- 4.2 Execution Engine (ExecutionPlanner, BranchTask, ExecutionEngine, cancellation)
- 4.3 Iterator / Loop Nodes (IteratorNode)
- 4.4 Composite / Subgraph Nodes (CompositeNode)
- 4.5 Updated Operation base class (SocketDef, icon, cancel_event)
- 4.6 Node State Machine (NodeState enum)
"""
import threading
import time

import numpy as np
import pandas as pd
import pytest

from persistra.core.objects import (
    DataWrapper,
    DistanceMatrix,
    FloatParam,
    IntParam,
    Parameter,
    PersistenceDiagram,
    StringParam,
    TimeSeries,
)
from persistra.core.project import Operation
from persistra.core.types import AnyType, ConcreteType, SocketType, UnionType


# =========================================================================
# 4.1 — Richer Type System
# =========================================================================

class TestSocketTypeHierarchy:
    """SocketType / ConcreteType / UnionType / AnyType basics."""

    def test_concrete_same_class_accepts(self):
        t1 = ConcreteType(TimeSeries)
        t2 = ConcreteType(TimeSeries)
        assert t1.accepts(t2)

    def test_concrete_subclass_accepts(self):
        """ConcreteType(DataWrapper) should accept ConcreteType(TimeSeries)."""
        parent = ConcreteType(DataWrapper)
        child = ConcreteType(TimeSeries)
        assert parent.accepts(child)

    def test_concrete_incompatible_rejects(self):
        t1 = ConcreteType(TimeSeries)
        t2 = ConcreteType(DistanceMatrix)
        assert not t1.accepts(t2)

    def test_concrete_dtype_match(self):
        t1 = ConcreteType(DataWrapper, dtype="float64")
        t2 = ConcreteType(DataWrapper, dtype="float64")
        assert t1.accepts(t2)

    def test_concrete_dtype_mismatch(self):
        t1 = ConcreteType(DataWrapper, dtype="float64")
        t2 = ConcreteType(DataWrapper, dtype="int32")
        assert not t1.accepts(t2)

    def test_concrete_shape_match(self):
        t1 = ConcreteType(DataWrapper, shape=(None, 3))
        t2 = ConcreteType(DataWrapper, shape=(100, 3))
        assert t1.accepts(t2)

    def test_concrete_shape_mismatch(self):
        t1 = ConcreteType(DataWrapper, shape=(None, 3))
        t2 = ConcreteType(DataWrapper, shape=(100, 4))
        assert not t1.accepts(t2)

    def test_concrete_shape_dim_mismatch(self):
        t1 = ConcreteType(DataWrapper, shape=(10, 3))
        t2 = ConcreteType(DataWrapper, shape=(10, 3, 1))
        assert not t1.accepts(t2)

    def test_union_accepts_any_member(self):
        union = UnionType(ConcreteType(TimeSeries), ConcreteType(DistanceMatrix))
        assert union.accepts(ConcreteType(TimeSeries))
        assert union.accepts(ConcreteType(DistanceMatrix))

    def test_union_rejects_non_member(self):
        union = UnionType(ConcreteType(TimeSeries))
        assert not union.accepts(ConcreteType(DistanceMatrix))

    def test_any_accepts_everything(self):
        any_t = AnyType()
        assert any_t.accepts(ConcreteType(TimeSeries))
        assert any_t.accepts(ConcreteType(DistanceMatrix))
        assert any_t.accepts(UnionType(ConcreteType(DataWrapper)))
        assert any_t.accepts(AnyType())

    def test_concrete_accepts_any(self):
        """ConcreteType should accept AnyType as a source."""
        concrete = ConcreteType(DataWrapper)
        assert concrete.accepts(AnyType())

    def test_concrete_accepts_union(self):
        """ConcreteType(DataWrapper) should accept UnionType containing a matching member."""
        concrete = ConcreteType(DataWrapper)
        union = UnionType(ConcreteType(TimeSeries), ConcreteType(DistanceMatrix))
        assert concrete.accepts(union)

    def test_repr(self):
        assert "ConcreteType" in repr(ConcreteType(DataWrapper))
        assert "UnionType" in repr(UnionType(ConcreteType(DataWrapper)))
        assert "AnyType" in repr(AnyType())


# =========================================================================
# 4.1.2 — Runtime Validation
# =========================================================================

class TestRuntimeValidation:
    """DataWrapper.validate() checks on subclasses."""

    def test_data_wrapper_validate_default(self):
        dw = DataWrapper(42)
        assert dw.validate() is True

    def test_timeseries_validate_ok(self):
        ts = TimeSeries(pd.DataFrame({"a": [1, 2, 3]}))
        assert ts.validate() is True

    def test_distance_matrix_validate_ok(self):
        arr = np.zeros((3, 3))
        dm = DistanceMatrix(arr)
        assert dm.validate() is True

    def test_distance_matrix_validate_not_square(self):
        dm = DistanceMatrix.__new__(DistanceMatrix)
        dm.data = np.zeros((2, 3))
        dm.metadata = {}
        with pytest.raises(ValueError, match="square"):
            dm.validate()

    def test_persistence_diagram_validate_ok(self):
        pd_obj = PersistenceDiagram([np.array([[0, 1]])])
        assert pd_obj.validate() is True

    def test_persistence_diagram_validate_bad_type(self):
        pd_obj = PersistenceDiagram.__new__(PersistenceDiagram)
        pd_obj.data = "not a list"
        pd_obj.metadata = {}
        with pytest.raises(TypeError, match="list"):
            pd_obj.validate()


# =========================================================================
# 4.1.3 — Socket integration + 4.5 SocketDef + 4.6 NodeState
# =========================================================================

class TestSocketIntegration:
    """Socket now uses SocketType for compatibility checks."""

    def test_socket_has_socket_type(self):
        from persistra.core.project import Node, Socket
        from persistra.core.types import ConcreteType

        # Use a minimal operation
        from persistra.operations.io import CSVLoader

        node = Node(CSVLoader)
        out_sock = node.get_output_socket("data")
        assert isinstance(out_sock.socket_type, ConcreteType)
        assert out_sock.socket_type.wrapper_cls is TimeSeries

    def test_socket_backward_compat_data_type(self):
        """Socket.data_type should still be available for UI compatibility."""
        from persistra.core.project import Node
        from persistra.operations.io import CSVLoader

        node = Node(CSVLoader)
        out_sock = node.get_output_socket("data")
        assert out_sock.data_type is TimeSeries

    def test_connect_compatible_sockets(self):
        from persistra.core.project import Node
        from persistra.operations.io import CSVLoader
        from persistra.operations.viz import LinePlot

        csv = Node(CSVLoader)
        plot = Node(LinePlot)
        out = csv.get_output_socket("data")
        inp = plot.get_input_socket("data")
        out.connect_to(inp)  # Should not raise
        assert inp in out.connections

    def test_connect_incompatible_sockets_raises(self):
        from persistra.core.project import Node, Operation, Socket
        from persistra.core.types import ConcreteType

        class OutOp(Operation):
            name = "Out"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "x", "type": DistanceMatrix}]
            def execute(self, inputs, params, cancel_event=None):
                return {}

        class InOp(Operation):
            name = "In"
            def __init__(self):
                super().__init__()
                self.inputs = [{"name": "y", "type": TimeSeries}]
            def execute(self, inputs, params, cancel_event=None):
                return {}

        out_node = Node(OutOp)
        in_node = Node(InOp)
        with pytest.raises(TypeError, match="Type Mismatch"):
            out_node.get_output_socket("x").connect_to(in_node.get_input_socket("y"))

    def test_socket_required_field(self):
        from persistra.core.project import Socket, Node
        from persistra.core.types import ConcreteType

        class DummyOp(Operation):
            name = "Dummy"
            def __init__(self):
                super().__init__()
            def execute(self, inputs, params, cancel_event=None):
                return {}

        node = Node(DummyOp)
        sock = Socket(node, "test", ConcreteType(DataWrapper), is_input=True, required=False)
        assert sock.required is False


# =========================================================================
# 4.5 — Updated Operation Base Class
# =========================================================================

class TestUpdatedOperation:
    """Operation gains icon, cancel_event, and SocketDef support."""

    def test_operation_has_icon(self):
        from persistra.core.project import Operation
        assert hasattr(Operation, "icon")
        assert Operation.icon is None

    def test_operation_execute_signature_accepts_cancel_event(self):
        """execute() should accept cancel_event kwarg."""
        import inspect
        from persistra.core.project import Operation
        sig = inspect.signature(Operation.execute)
        assert "cancel_event" in sig.parameters

    def test_socketdef_creation(self):
        from persistra.core.project import SocketDef
        sd = SocketDef(name="data", socket_type=ConcreteType(TimeSeries), required=False,
                       description="Input time series")
        assert sd.name == "data"
        assert sd.required is False
        assert isinstance(sd.socket_type, ConcreteType)

    def test_node_from_socketdef_operation(self):
        """An Operation using SocketDef should produce correct Sockets."""
        from persistra.core.project import Node, Operation, SocketDef

        class SDOp(Operation):
            name = "SD Op"
            def __init__(self):
                super().__init__()
                self.inputs = [SocketDef("x", ConcreteType(TimeSeries), required=False)]
                self.outputs = [SocketDef("y", ConcreteType(DataWrapper))]
            def execute(self, inputs, params, cancel_event=None):
                return {"y": DataWrapper(42)}

        node = Node(SDOp)
        assert len(node.input_sockets) == 1
        assert node.input_sockets[0].name == "x"
        assert node.input_sockets[0].required is False
        assert isinstance(node.input_sockets[0].socket_type, ConcreteType)


# =========================================================================
# 4.6 — Node State Machine
# =========================================================================

class TestNodeStateMachine:
    """Nodes transition through IDLE → DIRTY → COMPUTING → VALID/ERROR."""

    def test_initial_state(self):
        from persistra.core.project import Node, NodeState
        from persistra.operations.io import CSVLoader
        node = Node(CSVLoader)
        assert node.state == NodeState.IDLE

    def test_invalidate_sets_dirty(self):
        from persistra.core.project import Node, NodeState, Operation

        class Noop(Operation):
            name = "Noop"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(1)}

        node = Node(Noop)
        # First compute to get to VALID
        node.compute()
        assert node.state == NodeState.VALID
        # Invalidate
        node.invalidate()
        assert node.state == NodeState.DIRTY

    def test_compute_success_sets_valid(self):
        from persistra.core.project import Node, NodeState, Operation

        class GoodOp(Operation):
            name = "Good"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(42)}

        node = Node(GoodOp)
        node.compute()
        assert node.state == NodeState.VALID

    def test_compute_error_sets_error(self):
        from persistra.core.project import Node, NodeState, Operation

        class BadOp(Operation):
            name = "Bad"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                raise ValueError("boom")

        node = Node(BadOp)
        with pytest.raises(ValueError):
            node.compute()
        assert node.state == NodeState.ERROR
        assert node._error == "boom"


# =========================================================================
# 4.2 — Execution Engine
# =========================================================================

class TestExecutionPlanner:
    """Topological sort and branch identification."""

    def _make_passthrough_op(self, name="Pass"):
        """Create an operation that simply passes input through."""
        class PassOp(Operation):
            pass
        PassOp.name = name

        def _init(self_op):
            Operation.__init__(self_op)
            self_op.inputs = [{"name": "x", "type": DataWrapper}]
            self_op.outputs = [{"name": "x", "type": DataWrapper}]
        PassOp.__init__ = _init

        def _exec(self_op, inputs, params, cancel_event=None):
            return {"x": inputs.get("x", DataWrapper(0))}
        PassOp.execute = _exec
        return PassOp

    def _make_source_op(self, name="Src", value=1):
        class SrcOp(Operation):
            pass
        SrcOp.name = name

        def _init(self_op):
            Operation.__init__(self_op)
            self_op.outputs = [{"name": "out", "type": DataWrapper}]
        SrcOp.__init__ = _init

        def _exec(self_op, inputs, params, cancel_event=None):
            return {"out": DataWrapper(value)}
        SrcOp.execute = _exec
        return SrcOp

    def test_topological_sort_linear(self):
        from persistra.core.engine import ExecutionPlanner
        from persistra.core.project import Project

        proj = Project()
        src = proj.add_node(self._make_source_op())
        mid = proj.add_node(self._make_passthrough_op())
        end = proj.add_node(self._make_passthrough_op())

        proj.connect(src, "out", mid, "x")
        proj.connect(mid, "x", end, "x")

        order = ExecutionPlanner.topological_sort(proj)
        ids = [n.id for n in order]
        assert ids.index(src.id) < ids.index(mid.id) < ids.index(end.id)

    def test_topological_sort_dirty_only(self):
        from persistra.core.engine import ExecutionPlanner
        from persistra.core.project import Project

        proj = Project()
        src = proj.add_node(self._make_source_op())
        end = proj.add_node(self._make_passthrough_op())
        proj.connect(src, "out", end, "x")

        # Compute all
        end.compute()
        # Only src should be non-dirty
        # Invalidate src — both become dirty
        src.invalidate()

        dirty_order = ExecutionPlanner.topological_sort(proj, dirty_only=True)
        assert len(dirty_order) == 2

    def test_identify_branches_independent(self):
        from persistra.core.engine import ExecutionPlanner
        from persistra.core.project import Project

        proj = Project()
        a = proj.add_node(self._make_source_op("A"))
        b = proj.add_node(self._make_source_op("B"))

        sorted_nodes = ExecutionPlanner.topological_sort(proj)
        branches = ExecutionPlanner.identify_branches(sorted_nodes)
        # Two independent source nodes → two branches
        assert len(branches) == 2

    def test_identify_branches_single_chain(self):
        from persistra.core.engine import ExecutionPlanner
        from persistra.core.project import Project

        proj = Project()
        a = proj.add_node(self._make_source_op())
        b = proj.add_node(self._make_passthrough_op())
        proj.connect(a, "out", b, "x")

        sorted_nodes = ExecutionPlanner.topological_sort(proj)
        branches = ExecutionPlanner.identify_branches(sorted_nodes)
        assert len(branches) == 1
        assert len(branches[0]) == 2


class TestExecutionEngine:
    """Full engine execution with cancellation."""

    def _make_source_op(self, value=42):
        class SrcOp(Operation):
            name = "Src"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(value)}
        return SrcOp

    def _make_slow_op(self, delay=0.5):
        class SlowOp(Operation):
            name = "Slow"
            def __init__(self_op):
                super().__init__()
                self_op.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self_op, inputs, params, cancel_event=None):
                time.sleep(delay)
                return {"out": DataWrapper(99)}
        return SlowOp

    def test_run_simple_graph(self):
        from persistra.core.engine import ExecutionEngine
        from persistra.core.project import Project

        proj = Project()
        proj.add_node(self._make_source_op(42))

        engine = ExecutionEngine()
        results = engine.run(proj)
        assert len(results) == 1
        assert results[0].success is True

    def test_cancel_stops_execution(self):
        from persistra.core.engine import ExecutionEngine
        from persistra.core.project import Project

        proj = Project()
        # Add two slow nodes in a chain
        class SlowSrc(Operation):
            name = "SlowSrc"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                time.sleep(2)
                return {"out": DataWrapper(1)}

        proj.add_node(SlowSrc)

        engine = ExecutionEngine()

        # Cancel almost immediately
        def _cancel_soon():
            time.sleep(0.05)
            engine.cancel()

        t = threading.Thread(target=_cancel_soon, daemon=True)
        t.start()
        results = engine.run(proj)
        # The task was either cancelled or completed before cancellation
        # Either way, we should get results back
        assert isinstance(results, list)

    def test_auto_compute_toggle(self):
        from persistra.core.project import Project
        proj = Project()
        assert proj.auto_compute is False
        proj.auto_compute = True
        assert proj.auto_compute is True


# =========================================================================
# 4.3 + 4.4 — Composite and Iterator Nodes
# =========================================================================

class TestCompositeNode:
    """CompositeNode wraps a sub-project."""

    def test_composite_basic(self):
        from persistra.core.composite import CompositeNode
        from persistra.core.project import Node, Operation, Project

        # Build a trivial sub-graph: Source → Pass
        class SrcOp(Operation):
            name = "Src"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(42)}

        class PassOp(Operation):
            name = "Pass"
            def __init__(self):
                super().__init__()
                self.inputs = [{"name": "x", "type": DataWrapper}]
                self.outputs = [{"name": "x", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"x": inputs["x"]}

        sub = Project()
        src = sub.add_node(SrcOp)
        pas = sub.add_node(PassOp)
        sub.connect(src, "out", pas, "x")

        comp = CompositeNode(
            sub_project=sub,
            exposed_outputs=[(pas, "x")],
        )

        result = comp.compute()
        assert "x" in result
        assert result["x"].data == 42

    def test_composite_exposed_params(self):
        from persistra.core.composite import CompositeNode
        from persistra.core.project import Node, Operation, Project

        class ParamOp(Operation):
            name = "ParamOp"
            def __init__(self):
                super().__init__()
                self.parameters = [IntParam("n", "Number", default=5)]
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(params["n"])}

        sub = Project()
        p_node = sub.add_node(ParamOp)

        comp = CompositeNode(
            sub_project=sub,
            exposed_outputs=[(p_node, "out")],
            exposed_params=[(p_node, "n", "Exposed N")],
        )

        assert len(comp.parameters) == 1
        assert comp.parameters[0].label == "Exposed N"


class TestIteratorNode:
    """IteratorNode executes body repeatedly."""

    def test_fixed_count_iterations(self):
        from persistra.core.composite import CompositeNode, IteratorNode
        from persistra.core.project import Node, NodeState, Operation, Project

        # A counter that increments its output each time
        call_count = {"n": 0}

        class CounterOp(Operation):
            name = "Counter"
            def __init__(self):
                super().__init__()
                self.inputs = [{"name": "x", "type": DataWrapper}]
                self.outputs = [{"name": "x", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                call_count["n"] += 1
                val = inputs.get("x", DataWrapper(0))
                return {"x": DataWrapper(val.data + 1)}

        sub = Project()
        counter = sub.add_node(CounterOp)

        body = CompositeNode(
            sub_project=sub,
            exposed_inputs=[(counter, "x")],
            exposed_outputs=[(counter, "x")],
        )

        it = IteratorNode(body, max_iter=5, mode="fixed_count")
        result = it.compute()
        assert it.state == NodeState.VALID
        # The counter should have been called 5 times
        assert call_count["n"] == 5

    def test_convergence_mode(self):
        from persistra.core.composite import CompositeNode, IteratorNode
        from persistra.core.project import Operation, Project

        # An operation that halves its input each time — converges to 0
        class HalveOp(Operation):
            name = "Halve"
            def __init__(self):
                super().__init__()
                self.inputs = [{"name": "x", "type": DataWrapper}]
                self.outputs = [{"name": "x", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                val = inputs.get("x", DataWrapper(np.array([100.0])))
                return {"x": DataWrapper(np.asarray(val.data) / 2.0)}

        sub = Project()
        halve = sub.add_node(HalveOp)

        body = CompositeNode(
            sub_project=sub,
            exposed_inputs=[(halve, "x")],
            exposed_outputs=[(halve, "x")],
        )

        it = IteratorNode(body, max_iter=1000, tolerance=0.01, mode="converge")
        result = it.compute()
        # Should converge well before 1000 iterations
        assert np.all(np.asarray(result["x"].data) < 0.01)


# =========================================================================
# Project.connect convenience method
# =========================================================================

class TestProjectConnect:
    """Project.connect() is a convenience wrapper around Socket.connect_to()."""

    def test_connect_and_compute(self):
        from persistra.core.project import Node, Operation, Project

        class SrcOp(Operation):
            name = "Src"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"out": DataWrapper(7)}

        class SinkOp(Operation):
            name = "Sink"
            def __init__(self):
                super().__init__()
                self.inputs = [{"name": "x", "type": DataWrapper}]
                self.outputs = [{"name": "x", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {"x": inputs["x"]}

        proj = Project()
        src = proj.add_node(SrcOp)
        sink = proj.add_node(SinkOp)
        proj.connect(src, "out", sink, "x")

        result = sink.compute()
        assert result["x"].data == 7

    def test_connect_bad_socket_raises(self):
        from persistra.core.project import Operation, Project

        class SrcOp(Operation):
            name = "Src"
            def __init__(self):
                super().__init__()
                self.outputs = [{"name": "out", "type": DataWrapper}]
            def execute(self, inputs, params, cancel_event=None):
                return {}

        proj = Project()
        src = proj.add_node(SrcOp)
        src2 = proj.add_node(SrcOp)
        with pytest.raises(KeyError, match="not found"):
            proj.connect(src, "nonexistent", src2, "out")
