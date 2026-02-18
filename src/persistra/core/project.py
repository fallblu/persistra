"""
src/persistra/core/project.py

Defines the structure of the Graph: Project, Node, Socket, and Operation.
This file contains NO GUI code.
"""
import uuid
from typing import List, Dict, Type, Any, Optional
from persistra.core.objects import DataWrapper, Parameter

# --- The Logic Definition ---

class Operation:
    """
    Defines the behavior of a Node. 
    Subclass this to create new tools (e.g., 'CSVLoader', 'RipsPersistence').
    """
    name: str = "Generic Operation"
    description: str = ""
    category: str = "General"

    def __init__(self):
        # These will be populated by the Node factory
        self.inputs: List[dict] = []  # e.g. [{'name': 'src', 'type': TimeSeries}]
        self.outputs: List[dict] = [] # e.g. [{'name': 'out', 'type': DistanceMatrix}]
        self.parameters: List[Parameter] = []

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        The core logic.
        :param inputs: Dictionary of input data (unwrapped).
        :param params: Dictionary of current parameter values.
        :return: Dictionary of output data.
        """
        raise NotImplementedError("Operation must implement execute()")


# --- The Graph Elements ---

class Socket:
    """Represents a connection point on a Node."""
    def __init__(self, node: 'Node', name: str, data_type: Type[DataWrapper], is_input: bool):
        self.id = str(uuid.uuid4())
        self.node = node
        self.name = name
        self.data_type = data_type
        self.is_input = is_input
        
        # Connections
        # If Input: holds ONE reference to an output socket
        # If Output: holds MANY references to input sockets
        self.connections: List['Socket'] = [] 

    def connect_to(self, other: 'Socket'):
        """Connects this socket to another."""
        # Basic validation (Direction)
        if self.is_input == other.is_input:
            raise ValueError("Cannot connect Input-to-Input or Output-to-Output")
        
        # Determine source (Output) and target (Input)
        source, target = (other, self) if self.is_input else (self, other)
        
        # Basic Validation (Type - simplistic check for now)
        if not issubclass(source.data_type, target.data_type):
            # We allow subclass compatibility (e.g., TimeSeries -> DataWrapper)
             raise TypeError(f"Type Mismatch: Cannot connect {source.data_type} to {target.data_type}")

        # Input sockets can only have ONE connection
        if len(target.connections) > 0:
            target.disconnect_all()

        source.connections.append(target)
        target.connections.append(source)
        
        # Trigger update
        target.node.invalidate()

    def disconnect(self, other: 'Socket'):
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
    def __init__(self, operation_cls: Type[Operation], position=(0,0)):
        self.id = str(uuid.uuid4())
        self.operation = operation_cls()
        self.position = position # (x, y) tuple for GUI restoration
        
        # State
        self._is_dirty = True
        self._cached_outputs: Dict[str, Any] = {} # Stores the result of compute()
        self._error: Optional[str] = None

        # Build Sockets based on Operation definition
        self.input_sockets: List[Socket] = []
        self.output_sockets: List[Socket] = []
        self.parameters: List[Parameter] = self.operation.parameters

        for inp in self.operation.inputs:
            self.input_sockets.append(Socket(self, inp['name'], inp['type'], is_input=True))
            
        for out in self.operation.outputs:
            self.output_sockets.append(Socket(self, out['name'], out['type'], is_input=False))

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
            return # Already dirty, stop recursion to save cycles

        self._is_dirty = True
        self._cached_outputs = {}
        self._error = None

        # Ripple effect: Invalidate all nodes connected to my outputs
        for out_sock in self.output_sockets:
            for connected_input in out_sock.connections:
                connected_input.node.invalidate()

    def compute(self) -> Dict[str, Any]:
        """
        The 'Pull' part of Lazy Evaluation.
        Gather inputs -> Execute Operation -> Cache Results.
        """
        if not self._is_dirty:
            return self._cached_outputs

        # 1. Gather Inputs
        input_values = {}
        try:
            for sock in self.input_sockets:
                if not sock.connections:
                    # Optional: Handle optional inputs here. For now, we assume strictness.
                    # input_values[sock.name] = None 
                    continue 
                
                # Pull data from upstream
                source_sock = sock.connections[0] # Input only has 1 source
                upstream_result = source_sock.node.compute()
                
                # Extract the specific output required
                if source_sock.name in upstream_result:
                    input_values[sock.name] = upstream_result[source_sock.name]
                else:
                    raise KeyError(f"Upstream node did not produce output '{source_sock.name}'")

            # 2. Gather Parameters
            param_values = {p.name: p.value for p in self.parameters}

            # 3. Execute
            print(f"Computing Node: {self.operation.name}...") # Debug logging
            self._cached_outputs = self.operation.execute(input_values, param_values)
            
            self._is_dirty = False
            return self._cached_outputs

        except Exception as e:
            self._error = str(e)
            print(f"Error in {self.operation.name}: {e}")
            raise e # Re-raise to be handled by controller/UI


class Project:
    """The root container for the graph."""
    def __init__(self):
        self.nodes: List[Node] = []

    def add_node(self, operation_class):
        node = Node(operation_class)
        self.nodes.append(node)
        return node

    def remove_node(self, node: Node):
        if node in self.nodes:
            # Disconnect all sockets first
            for s in node.input_sockets: s.disconnect_all()
            for s in node.output_sockets: s.disconnect_all()
            self.nodes.remove(node)

    def clear(self):
        for n in list(self.nodes):
            self.remove_node(n)
