import typing
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyleOptionGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QFont

from persistra.ui.theme import ThemeManager

# Type hinting for the backend objects
if typing.TYPE_CHECKING:
    from persistra.core.project import Node


def snap_to_grid(pos: QPointF, grid_size: int = 20) -> QPointF:
    """Snap a position to the nearest grid intersection."""
    x = round(pos.x() / grid_size) * grid_size
    y = round(pos.y() / grid_size) * grid_size
    return QPointF(x, y)


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
        
    def add_wire(self, wire: 'WireItem'):
        self.wires.append(wire)

    def boundingRect(self) -> QRectF:
        return QRectF(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        tokens = ThemeManager().current_tokens
        color = QColor(tokens.socket_hover) if self.isUnderMouse() else QColor(tokens.socket_default)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(-self.RADIUS, -self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
        painter.drawEllipse(rect)

class NodeItem(QGraphicsItem):
    """
    Generic visual representation of a Node.
    Reads colors from ThemeManager for theming support.
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
        
        real_inputs = node_data.input_sockets
        real_outputs = node_data.output_sockets

        # Determine dynamic height
        n_inputs = len(real_inputs)
        n_outputs = len(real_outputs)
        self.height = self.HEADER_HEIGHT + (max(n_inputs, n_outputs) * self.SOCKET_SPACING) + 10
        
        # Create Input Sockets
        self.inputs = []
        for i, sock in enumerate(real_inputs):
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
        Detects position changes: updates connected wires and snaps to grid.
        """
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap to grid on position change
            return snap_to_grid(value)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for socket in self.inputs + self.outputs:
                for wire in socket.wires:
                    wire.update_path()
                    
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.height)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        from persistra.core.project import NodeState

        tm = ThemeManager()
        tokens = tm.current_tokens
        state = getattr(self.node_data, "state", NodeState.IDLE)

        # --- Determine border pen based on state ---
        if self.isSelected():
            border_pen = QPen(QColor(tokens.node_border_selected), 2)
        elif state == NodeState.ERROR:
            border_pen = QPen(QColor(tokens.error), 2)
        elif state == NodeState.COMPUTING:
            # Pulsing accent border (alpha cycles via _pulse_phase)
            alpha = int(128 + 127 * (((getattr(self, "_pulse_phase", 0) % 20) / 20.0) * 2 - 1))
            accent = QColor(tokens.accent)
            accent.setAlpha(max(0, min(255, alpha)))
            border_pen = QPen(accent, 2)
        elif state == NodeState.DIRTY:
            border_pen = QPen(QColor(tokens.node_border), 1, Qt.PenStyle.DashLine)
        elif state == NodeState.INVALID:
            border_pen = QPen(QColor(tokens.node_border), 1)
        else:
            # IDLE / VALID — normal border
            border_pen = QPen(QColor(tokens.node_border), 1)

        # --- Body fill ---
        if state == NodeState.INVALID:
            body_color = QColor(tokens.node_background)
            body_color.setAlpha(100)
        elif self.isSelected():
            body_color = QColor(tokens.node_background_selected)
        else:
            body_color = QColor(tokens.node_background)

        # Draw Background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.WIDTH, self.height, 5, 5)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(path)

        # Draw Header (colored by category)
        header_rect = QRectF(0, 0, self.WIDTH, self.HEADER_HEIGHT)
        category = getattr(self.node_data.operation, "category", "Utility")
        header_color = tm.get_category_color(category)
        painter.setBrush(QBrush(QColor(header_color)))
        painter.setPen(Qt.PenStyle.NoPen)
        path_header = QPainterPath()
        path_header.addRoundedRect(header_rect, 5, 5) 
        painter.setClipPath(path_header) 
        painter.drawRect(header_rect)
        painter.setClipping(False) 

        # Draw Title
        text_color = QColor(tokens.node_text)
        if state == NodeState.INVALID:
            text_color.setAlpha(120)
        painter.setPen(text_color)
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)

        # Reserve space for error icon in header
        title_rect = header_rect
        if state == NodeState.ERROR:
            title_rect = QRectF(0, 0, self.WIDTH - 22, self.HEADER_HEIGHT)

        painter.drawText(
            title_rect, Qt.AlignmentFlag.AlignCenter,
            self.node_data.operation.__class__.__name__,
        )

        # Error icon ⚠ in header
        if state == NodeState.ERROR:
            painter.setPen(QColor(tokens.error))
            warn_font = QFont("Segoe UI", 12)
            painter.setFont(warn_font)
            icon_rect = QRectF(self.WIDTH - 24, 2, 22, self.HEADER_HEIGHT - 4)
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "⚠")

        # Draw Socket Labels
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        label_color = QColor(tokens.node_text)
        if state == NodeState.INVALID:
            label_color.setAlpha(120)
        painter.setPen(label_color)

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
        tokens = ThemeManager().current_tokens
        self.setPen(QPen(QColor(tokens.wire_default), 2))
        
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
