import json
import logging
import uuid
from collections import defaultdict

from PySide6.QtCore import QObject, QPointF, Signal

from persistra.core.project import Project
from persistra.ui.graph.items import NodeItem, SocketItem, WireItem
from persistra.ui.graph.scene import GraphScene
from persistra.ui.graph.worker import Worker

logger = logging.getLogger("persistra.ui.graph.manager")


class GraphManager(QObject):
    """
    The Controller logic. Mediates between Project (Model) and GraphScene (View).
    """
    node_selected = Signal(object)
    computation_started = Signal(str) # Message to show in status bar
    computation_finished = Signal(object) # Result to send to VizPanel

    def __init__(self, scene: GraphScene, project_model: Project):
        super().__init__()
        self.scene = scene
        self.project = project_model
        
        self.node_map = {}  # {NodeItem: NodeModel}
        self.wire_map = {}  # {WireItem: (SourceNode, TargetNode, ...)} 
        self.current_worker = None

        # Clipboard for copy/paste
        self._clipboard: list[dict] = []

        # Connect Scene Signals
        self.scene.connection_requested.connect(self.handle_connection)
        self.scene.selection_changed_custom.connect(self.handle_selection)

    def add_node(self, operation_class_name: str, pos_x: float = 0, pos_y: float = 0):
        """Creates a Node in the Model and View."""
        from persistra.operations import REGISTRY
        
        op_entry = REGISTRY.get(operation_class_name)
        
        if not op_entry:
            logger.error("Operation '%s' not found in registry.", operation_class_name)
            return

        if isinstance(op_entry, (list, tuple)):
            op_class = op_entry[0]
        else:
            op_class = op_entry

        if not callable(op_class):
            logger.error("Registry entry for '%s' is not callable.", operation_class_name)
            return

        node_model = self.project.add_node(op_class)
        
        if node_model is None:
            logger.error("Project.add_node() returned None for '%s'.", operation_class_name)
            return

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
        
        self.project.connect(source_node, source.socket_name, target_node, target.socket_name)

        wire_item = WireItem(source, target)
        self.scene.addItem(wire_item)
        
        self.wire_map[wire_item] = (source_node, target_node)

    def handle_selection(self, selected_items):
        if not selected_items: return
        first_item = selected_items[0]
        if isinstance(first_item, NodeItem):
            node_model = self.node_map[first_item]
            self.node_selected.emit(node_model)

    def request_computation(self, node):
        """Starts background computation for the selected node."""
        if self.current_worker and self.current_worker.isRunning():
            return
            
        self.computation_started.emit(f"Computing {node}...")
        
        self.current_worker = Worker(node)
        self.current_worker.finished.connect(self._on_compute_finished)
        self.current_worker.error.connect(self._on_compute_error)
        self.current_worker.start()

    def _on_compute_finished(self, result):
        self.computation_finished.emit(result)
        self.computation_started.emit("Ready")

    def _on_compute_error(self, error_msg):
        logger.error(error_msg)
        self.computation_started.emit("Error during computation")

    # ------------------------------------------------------------------
    # Copy / Paste (§8.5.4)
    # ------------------------------------------------------------------

    def copy_selected(self):
        """Serialize selected nodes to the internal clipboard."""
        selected = [
            item for item in self.scene.selectedItems() if isinstance(item, NodeItem)
        ]
        if not selected:
            return

        # Build a set of selected node model ids for connection filtering
        selected_ids = {self.node_map[item].id for item in selected}

        clipboard = []
        for item in selected:
            model = self.node_map[item]
            pos = item.pos()
            entry = {
                "original_id": model.id,
                "op_class_name": model.operation.__class__.__name__,
                "x": pos.x(),
                "y": pos.y(),
                "params": {p.name: p.value for p in model.parameters},
            }
            clipboard.append(entry)

        # Record internal connections among the copied nodes
        connections = []
        for wire_item, (src_node, tgt_node) in self.wire_map.items():
            if src_node.id in selected_ids and tgt_node.id in selected_ids:
                connections.append({
                    "src_id": src_node.id,
                    "src_socket": wire_item.start_socket.socket_name,
                    "tgt_id": tgt_node.id,
                    "tgt_socket": wire_item.end_socket.socket_name,
                })

        self._clipboard = clipboard
        self._clipboard_connections = connections

    def paste(self):
        """Deserialize clipboard nodes with new UUIDs, offset by (20, 20)."""
        if not self._clipboard:
            return

        old_to_new: dict[str, str] = {}  # original_id -> new NodeModel.id
        old_to_item: dict[str, NodeItem] = {}

        for entry in self._clipboard:
            item = self.add_node(
                entry["op_class_name"],
                entry["x"] + 20,
                entry["y"] + 20,
            )
            if item is None:
                continue
            model = self.node_map[item]
            old_to_new[entry["original_id"]] = model.id
            old_to_item[entry["original_id"]] = item

            # Restore parameter values
            for pname, pval in entry.get("params", {}).items():
                try:
                    model.set_parameter(pname, pval)
                except KeyError:
                    pass

        # Re-create internal connections
        for conn in getattr(self, "_clipboard_connections", []):
            src_old = conn["src_id"]
            tgt_old = conn["tgt_id"]
            if src_old not in old_to_item or tgt_old not in old_to_item:
                continue
            src_item = old_to_item[src_old]
            tgt_item = old_to_item[tgt_old]
            src_model = self.node_map[src_item]
            tgt_model = self.node_map[tgt_item]
            try:
                self.project.connect(
                    src_model, conn["src_socket"],
                    tgt_model, conn["tgt_socket"],
                )
                # Find matching visual sockets
                src_socket = next(
                    (s for s in src_item.outputs if s.socket_name == conn["src_socket"]),
                    None,
                )
                tgt_socket = next(
                    (s for s in tgt_item.inputs if s.socket_name == conn["tgt_socket"]),
                    None,
                )
                if src_socket and tgt_socket:
                    wire = WireItem(src_socket, tgt_socket)
                    self.scene.addItem(wire)
                    self.wire_map[wire] = (src_model, tgt_model)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Auto-Layout (§8.5.2) — Sugiyama-style layered layout
    # ------------------------------------------------------------------

    def auto_layout(self, h_spacing: int = 250, v_spacing: int = 80):
        """Assign layers and position nodes using a left-to-right Sugiyama layout."""
        if not self.node_map:
            return

        # Build adjacency from model
        node_items = list(self.node_map.keys())
        model_to_item = {v.id: k for k, v in self.node_map.items()}
        children: dict[str, list[str]] = defaultdict(list)
        parents: dict[str, list[str]] = defaultdict(list)

        for _, (src, tgt) in self.wire_map.items():
            children[src.id].append(tgt.id)
            parents[tgt.id].append(src.id)

        all_ids = {m.id for m in self.node_map.values()}

        # 1. Layer assignment (longest path from a source)
        layers: dict[str, int] = {}
        visited: set[str] = set()

        def assign_layer(nid: str) -> int:
            if nid in layers:
                return layers[nid]
            if nid in visited:
                return 0  # cycle guard
            visited.add(nid)
            if not parents[nid]:
                layers[nid] = 0
            else:
                layers[nid] = max(assign_layer(p) + 1 for p in parents[nid])
            return layers[nid]

        for nid in all_ids:
            assign_layer(nid)

        # 2. Group by layer
        layer_groups: dict[int, list[str]] = defaultdict(list)
        for nid, layer in layers.items():
            layer_groups[layer].append(nid)

        # 3. Ordering (barycenter heuristic)
        for layer_idx in sorted(layer_groups.keys()):
            if layer_idx == 0:
                continue
            group = layer_groups[layer_idx]

            def barycenter(nid):
                pars = parents[nid]
                if not pars:
                    return 0
                prev_layer = layer_groups.get(layer_idx - 1, [])
                positions = []
                for p in pars:
                    if p in prev_layer:
                        positions.append(prev_layer.index(p))
                return sum(positions) / len(positions) if positions else 0

            layer_groups[layer_idx] = sorted(group, key=barycenter)

        # 4. Positioning
        for layer_idx, group in layer_groups.items():
            for rank, nid in enumerate(group):
                item = model_to_item.get(nid)
                if item:
                    item.setPos(layer_idx * h_spacing, rank * v_spacing)
