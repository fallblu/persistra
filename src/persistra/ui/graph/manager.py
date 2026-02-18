from PyQt6.QtCore import QObject, pyqtSignal
from persistra.ui.graph.scene import GraphScene
from persistra.ui.graph.items import NodeItem, WireItem, SocketItem
from persistra.ui.graph.worker import Worker
# Import the REAL backend
from persistra.core.project import Project 

class GraphManager(QObject):
    """
    The Controller logic. Mediates between Project (Model) and GraphScene (View).
    """
    node_selected = pyqtSignal(object)
    computation_started = pyqtSignal(str) # Message to show in status bar
    computation_finished = pyqtSignal(object) # Result to send to VizPanel

    def __init__(self, scene: GraphScene, project_model: Project):
        super().__init__()
        self.scene = scene
        self.project = project_model
        
        self.node_map = {}  # {NodeItem: NodeModel}
        self.wire_map = {}  # {WireItem: (SourceNode, TargetNode, ...)} 
        self.current_worker = None

        # Connect Scene Signals
        self.scene.connection_requested.connect(self.handle_connection)
        self.scene.selection_changed_custom.connect(self.handle_selection)

    def add_node(self, operation_class_name: str, pos_x: float = 0, pos_y: float = 0):
        """Creates a Node in the Model and View."""
        # 1. Update Model (Real Backend)
        from persistra.operations import OPERATIONS_REGISTRY
        
        # FIX: Handle Registry entries that might be [Class] or [Class, Metadata] lists
        op_entry = OPERATIONS_REGISTRY.get(operation_class_name)
        
        if not op_entry:
            print(f"Error: Operation '{operation_class_name}' not found in registry.")
            return

        # If the registry returns a list (e.g., [Class, "Description"]), extract the Class
        if isinstance(op_entry, list) or isinstance(op_entry, tuple):
            op_class = op_entry[0]
        else:
            op_class = op_entry

        # Safety check to ensure we actually have a class (callable)
        if not callable(op_class):
            print(f"Error: Registry entry for '{operation_class_name}' is not a callable class. Got: {type(op_class)}")
            return

        node_model = self.project.add_node(op_class)
        
        # Safety Check for Backend Return Value (from previous step)
        if node_model is None:
            print(f"CRITICAL ERROR: Project.add_node() returned None for operation '{operation_class_name}'.")
            return

        # 2. Update View
        node_item = NodeItem(node_model)
        node_item.setPos(pos_x, pos_y)
        self.scene.addItem(node_item)
        
        self.node_map[node_item] = node_model
        return node_item

    def handle_connection(self, start_socket: SocketItem, end_socket: SocketItem):
        if start_socket.is_input == end_socket.is_input: return
        if not start_socket.is_input: source, target = start_socket, end_socket
        else: source, target = end_socket, start_socket

        if source.parentItem() == target.parentItem(): return

        source_node_item = source.parentItem()
        target_node_item = target.parentItem()
        source_node = self.node_map[source_node_item]
        target_node = self.node_map[target_node_item]
        
        # 1. Update Model (Real Backend)
        # connect() usually takes (source_node, source_output_name, target_node, target_input_name)
        self.project.connect(source_node, source.socket_name, target_node, target.socket_name) #

        # 2. Update View
        wire_item = WireItem(source, target)
        self.scene.addItem(wire_item)
        
        self.wire_map[wire_item] = (source_node, target_node)

    def handle_selection(self, selected_items):
        if not selected_items: return
        first_item = selected_items[0]
        if isinstance(first_item, NodeItem):
            node_model = self.node_map[first_item]
            self.node_selected.emit(node_model)
            
            # Auto-compute on selection (Optional, or trigger via button)
            # self.request_computation(node_model)

    def request_computation(self, node):
        """Starts background computation for the selected node."""
        if self.current_worker and self.current_worker.isRunning():
            return # Busy
            
        self.computation_started.emit(f"Computing {node}...")
        
        self.current_worker = Worker(node)
        self.current_worker.finished.connect(self._on_compute_finished)
        self.current_worker.error.connect(self._on_compute_error)
        self.current_worker.start()

    def _on_compute_finished(self, result):
        self.computation_finished.emit(result)
        self.computation_started.emit("Ready")

    def _on_compute_error(self, error_msg):
        print(error_msg)
        self.computation_started.emit("Error during computation")
