import typing
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyleOptionGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QFont

# Type hinting for the backend objects
if typing.TYPE_CHECKING:
    from persistra.core.project import Node

class SocketItem(QGraphicsItem):
    """
    Visual representation of an Input or Output port.
    """
    RADIUS = 6.0
    
    def __init__(self, parent: QGraphicsItem, index: int, is_input: bool, socket_name: str):
        super().__init__(parent)
        self.index = index
        self.is_input = is_input
        self.socket_name = socket_name
        self.setAcceptHoverEvents(True)
        
        # Track connected wires to update them when the parent node moves
        self.wires = [] 
        
        # Colors
        self._color = QColor("#E0E0E0")
        self._hover_color = QColor("#FF9800")
        
    def add_wire(self, wire: 'WireItem'):
        self.wires.append(wire)

    def boundingRect(self) -> QRectF:
        return QRectF(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        painter.setBrush(QBrush(self._hover_color if self.isUnderMouse() else self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        painter.drawEllipse(rect)

class NodeItem(QGraphicsItem):
    """
    Generic visual representation of a Node.
    """
    HEADER_HEIGHT = 30
    SOCKET_SPACING = 25
    WIDTH = 180
    
    def __init__(self, node_data: 'Node'):
        super().__init__()
        self.node_data = node_data
        
        # ItemSendsGeometryChanges is required for itemChange to detect position updates
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        # FIX: Access the initialized Socket objects from the Node model.
        # The backend 'Node' class creates 'input_sockets' and 'output_sockets' lists
        # containing objects with a .name attribute.
        real_inputs = node_data.input_sockets
        real_outputs = node_data.output_sockets

        # Determine dynamic height
        n_inputs = len(real_inputs)
        n_outputs = len(real_outputs)
        self.height = self.HEADER_HEIGHT + (max(n_inputs, n_outputs) * self.SOCKET_SPACING) + 10
        
        # Create Input Sockets
        self.inputs = []
        for i, sock in enumerate(real_inputs):
            # sock is a Socket object, so .name is valid
            socket_item = SocketItem(self, i, True, sock.name)
            socket_item.setPos(0, self.HEADER_HEIGHT + (i * self.SOCKET_SPACING) + 10)
            self.inputs.append(socket_item)
            
        # Create Output Sockets
        self.outputs = []
        for i, sock in enumerate(real_outputs):
            socket_item = SocketItem(self, i, False, sock.name)
            socket_item.setPos(self.WIDTH, self.HEADER_HEIGHT + (i * self.SOCKET_SPACING) + 10)
            self.outputs.append(socket_item)

    def itemChange(self, change, value):
        """
        Detects position changes and updates connected wires.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Iterate through all input and output sockets
            for socket in self.inputs + self.outputs:
                # Update every wire attached to these sockets
                for wire in socket.wires:
                    wire.update_path()
                    
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.height)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        # Draw Background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.WIDTH, self.height, 5, 5)
        
        if self.isSelected():
            painter.setPen(QPen(QColor("#FF9800"), 2))
            painter.setBrush(QBrush(QColor("#333333")))
        else:
            painter.setPen(QPen(QColor("#111111"), 1))
            painter.setBrush(QBrush(QColor("#222222")))
        
        painter.drawPath(path)
        
        # Draw Header
        header_rect = QRectF(0, 0, self.WIDTH, self.HEADER_HEIGHT)
        painter.setBrush(QBrush(QColor("#444444")))
        painter.setPen(Qt.PenStyle.NoPen)
        path_header = QPainterPath()
        path_header.addRoundedRect(header_rect, 5, 5) 
        painter.setClipPath(path_header) 
        painter.drawRect(header_rect)
        painter.setClipping(False) 
        
        # Draw Title
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        # Assuming node_data.operation is an instance of an Operation subclass
        painter.drawText(header_rect, Qt.AlignmentFlag.AlignCenter, self.node_data.operation.__class__.__name__)
        
        # Draw Socket Labels
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        
        for inp in self.inputs:
            rect = QRectF(10.0, inp.y() - 10.0, self.WIDTH/2, 20.0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, inp.socket_name)
            
        for out in self.outputs:
            rect = QRectF(self.WIDTH/2 - 10.0, out.y() - 10.0, self.WIDTH/2, 20.0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, out.socket_name)

class WireItem(QGraphicsPathItem):
    """
    Cubic Bezier curve connecting two sockets.
    """
    def __init__(self, start_socket: SocketItem, end_socket: SocketItem):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.setZValue(-1) # Render behind nodes
        self.setPen(QPen(QColor("#AAAAAA"), 2))
        
        # Register this wire with the sockets so they can trigger updates
        self.start_socket.add_wire(self)
        self.end_socket.add_wire(self)
        
        self.update_path()

    def update_path(self):
        start_pos = self.start_socket.scenePos()
        end_pos = self.end_socket.scenePos()
        
        path = QPainterPath()
        path.moveTo(start_pos)
        
        dx = end_pos.x() - start_pos.x()
        
        # Curvature control points
        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)
