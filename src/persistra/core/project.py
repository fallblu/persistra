"""
src/persistra/core/project.py

Defines the structure of the Graph: Project, Node, Socket, and Operation.
This file contains NO GUI code.
"""
import enum
import threading
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Type, Any, Optional

from persistra.core.objects import DataWrapper, Parameter
from persistra.core.types import SocketType, ConcreteType, AnyType


# --- Node State Machine (§4.6) ---

class NodeState(enum.Enum):
    """Explicit states that a node can be in for UI rendering and engine logic."""
    IDLE = "idle"           # Clean, has cached output or no output yet
    DIRTY = "dirty"         # Needs recomputation
    COMPUTING = "computing" # Currently being executed
    VALID = "valid"         # Computation succeeded, cached output available
    ERROR = "error"         # Computation failed
    INVALID = "invalid"     # Required inputs are disconnected


# --- Socket Definition (§4.5) ---

@dataclass
class SocketDef:
    """Declarative socket definition used by Operation subclasses."""
    name: str
    socket_type: SocketType
    required: bool = True
    description: str = ""


# --- The Logic Definition ---

class Operation:
    """
    Defines the behavior of a Node.
    Subclass this to create new tools (e.g., 'CSVLoader', 'RipsPersistence').
    """
    name: str = "Generic Operation"
    description: str = ""
    category: str = "General"
    icon: Optional[str] = None  # Path to icon file or built-in icon name

    def __init__(self):
        # These will be populated by the Node factory.
        self.inputs: List[SocketDef] = []
        self.outputs: List[SocketDef] = []
        self.parameters: List[Parameter] = []

    def execute(
        self,
        inputs: Dict[str, Any],
        params: Dict[str, Any],
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """
        The core logic.
        :param inputs: Dictionary of input data (unwrapped).
        :param params: Dictionary of current parameter values.
        :param cancel_event: Optional threading Event for cooperative cancellation.
        :return: Dictionary of output data.
        """
        raise NotImplementedError("Operation must implement execute()")


def _socket_type_from_def(definition: SocketDef) -> tuple:
    """Return (name, SocketType, required) from a SocketDef."""
    return definition.name, definition.socket_type, definition.required


# --- The Graph Elements ---

class Socket:
    """Represents a connection point on a Node."""

    def __init__(
        self,
        node: "Node",
        name: str,
        socket_type: SocketType,
        is_input: bool,
        required: bool = True,
    ):
        self.id = str(uuid.uuid4())
        self.node = node
        self.name = name
        self.socket_type = socket_type
        self.is_input = is_input
        self.required = required

        # Connections
        # If Input: holds ONE reference to an output socket
        # If Output: holds MANY references to input sockets
        self.connections: List["Socket"] = []

    def connect_to(self, other: "Socket"):
        """Connects this socket to another."""
        # Basic validation (Direction)
        if self.is_input == other.is_input:
            raise ValueError("Cannot connect Input-to-Input or Output-to-Output")

        # Determine source (Output) and target (Input)
        source, target = (other, self) if self.is_input else (self, other)

        # Type validation using the new SocketType system
        if not target.socket_type.accepts(source.socket_type):
            raise TypeError(
                f"Type Mismatch: Cannot connect {source.socket_type} to {target.socket_type}"
            )

        # Input sockets can only have ONE connection
        if len(target.connections) > 0:
            target.disconnect_all()

        source.connections.append(target)
        target.connections.append(source)

        # Trigger update
        target.node.invalidate()

    def disconnect(self, other: "Socket"):
        if other in self.connections:
            self.connections.remove(other)
        if self in other.connections:
            other.connections.remove(self)

        # If we just disconnected an input, that node is now invalid/stale
        if self.is_input:
            self.node.invalidate()
        else:
            other.node.invalidate()

    def disconnect_all(self):
        """Disconnect from all linked sockets."""
        # Iterate over a copy since we are modifying the list
        for other in list(self.connections):
            self.disconnect(other)


class Node:
    """
    The container in the graph. Holds an Operation and manages state.
    """

    def __init__(self, operation_cls: Type[Operation], position=(0, 0)):
        self.id = str(uuid.uuid4())
        self.operation = operation_cls()
        self.position = position  # (x, y) tuple for GUI restoration

        # State machine (§4.6)
        self.state: NodeState = NodeState.IDLE
        self._is_dirty = True
        self._cached_outputs: Dict[str, Any] = {}  # Stores the result of compute()
        self._error: Optional[str] = None

        # Build Sockets based on Operation definition
        self.input_sockets: List[Socket] = []
        self.output_sockets: List[Socket] = []
        self.parameters: List[Parameter] = self.operation.parameters

        for inp in self.operation.inputs:
            name, stype, req = _socket_type_from_def(inp)
            self.input_sockets.append(Socket(self, name, stype, is_input=True, required=req))

        for out in self.operation.outputs:
            name, stype, req = _socket_type_from_def(out)
            self.output_sockets.append(Socket(self, name, stype, is_input=False, required=req))

    def get_input_socket(self, name: str) -> Optional[Socket]:
        return next((s for s in self.input_sockets if s.name == name), None)

    def get_output_socket(self, name: str) -> Optional[Socket]:
        return next((s for s in self.output_sockets if s.name == name), None)

    def set_parameter(self, name: str, value: Any):
        """Updates a parameter and invalidates the node."""
        for param in self.parameters:
            if param.name == name:
                param.value = value
                self.invalidate()
                return
        raise KeyError(f"Parameter {name} not found in node {self.operation.name}")

    def invalidate(self):
        """
        Marks this node as dirty and recursively invalidates downstream nodes.
        This is the 'Push' part of the Lazy Evaluation.
        """
        if self._is_dirty:
            return  # Already dirty, stop recursion to save cycles

        self._is_dirty = True
        self._cached_outputs = {}
        self._error = None
        self.state = NodeState.DIRTY

        # Ripple effect: Invalidate all nodes connected to my outputs
        for out_sock in self.output_sockets:
            for connected_input in out_sock.connections:
                connected_input.node.invalidate()

    def compute(self) -> Dict[str, Any]:
        """
        The 'Pull' part of Lazy Evaluation.
        Gather inputs -> Execute Operation -> Cache Results.
        Validates outputs via DataWrapper.validate() before caching.
        """
        if not self._is_dirty:
            return self._cached_outputs

        self.state = NodeState.COMPUTING

        # 1. Gather Inputs
        input_values = {}
        try:
            # Check for injected inputs (used by CompositeNode.set_inputs)
            injected = getattr(self, "_injected_inputs", {})

            for sock in self.input_sockets:
                if sock.name in injected:
                    input_values[sock.name] = injected.pop(sock.name)
                elif not sock.connections:
                    continue
                else:
                    # Pull data from upstream
                    source_sock = sock.connections[0]  # Input only has 1 source
                    upstream_result = source_sock.node.compute()

                    # Extract the specific output required
                    if source_sock.name in upstream_result:
                        input_values[sock.name] = upstream_result[source_sock.name]
                    else:
                        raise KeyError(
                            f"Upstream node did not produce output '{source_sock.name}'"
                        )

            # 2. Gather Parameters
            param_values = {p.name: p.value for p in self.parameters}

            # 3. Execute
            self._cached_outputs = self.operation.execute(input_values, param_values)

            # 4. Runtime validation (§4.1.2)
            for value in self._cached_outputs.values():
                if isinstance(value, DataWrapper):
                    value.validate()

            self._is_dirty = False
            self.state = NodeState.VALID
            return self._cached_outputs

        except Exception as e:
            self._error = str(e)
            self.state = NodeState.ERROR
            raise


class Project:
    """The root container for the graph."""

    def __init__(self):
        self.nodes: List[Node] = []
        self.auto_compute: bool = False  # §4.2.3 global toggle (default: off)
        self.autosave_interval_minutes: int = 5  # §5.3 autosave interval

    def add_node(self, operation_class, position=(0, 0)):
        node = Node(operation_class, position=position)
        self.nodes.append(node)
        return node

    def remove_node(self, node: Node):
        if node in self.nodes:
            # Disconnect all sockets first
            for s in node.input_sockets:
                s.disconnect_all()
            for s in node.output_sockets:
                s.disconnect_all()
            self.nodes.remove(node)

    def connect(
        self,
        source_node: Node,
        source_socket_name: str,
        target_node: Node,
        target_socket_name: str,
    ):
        """Connect an output socket of *source_node* to an input socket of *target_node*."""
        source_sock = source_node.get_output_socket(source_socket_name)
        target_sock = target_node.get_input_socket(target_socket_name)
        if source_sock is None:
            raise KeyError(
                f"Output socket '{source_socket_name}' not found on {source_node.operation.name}"
            )
        if target_sock is None:
            raise KeyError(
                f"Input socket '{target_socket_name}' not found on {target_node.operation.name}"
            )
        source_sock.connect_to(target_sock)

    def clear(self):
        for n in list(self.nodes):
            self.remove_node(n)
