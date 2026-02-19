import math
import typing
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QLineF

# Import visual items
from persistra.ui.graph.items import SocketItem, NodeItem, WireItem

class GraphScene(QGraphicsScene):
    """
    The custom scene that manages the infinite grid and interaction logic.
    Ref: README.md Section 4.2
    """
    
    # Signals to notify the Controller (GraphManager)
    connection_requested = Signal(object, object)  # (Source SocketItem, Target SocketItem)
    selection_changed_custom = Signal(list)        # (List of selected items)
    node_moved = Signal(object, object)            # (NodeItem, New Position)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_size = 20
        self.grid_squares = 5
        
        # Visual style
        self.setBackgroundBrush(QColor("#1E1E1E"))
        # Define a large scene rect to simulate "infinite" space
        self.setSceneRect(-5000, -5000, 10000, 10000)
        
        # Interaction State
        self.draft_wire_source: typing.Optional[SocketItem] = None
        self.draft_wire_path: typing.Optional[QPainterPath] = None

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """
        Draws the grid background.
        """
        super().drawBackground(painter, rect)
        
        # Calculate grid lines based on the exposed rect
        left = int(math.floor(rect.left()))
        right = int(math.ceil(rect.right()))
        top = int(math.floor(rect.top()))
        bottom = int(math.ceil(rect.bottom()))
        
        first_left = left - (left % self.grid_size)
        first_top = top - (top % self.grid_size)
        
        # 1. Fine grid lines
        painter.setPen(QPen(QColor("#2F2F2F"), 1))
        lines = []
        # Vertical lines
        for x in range(first_left, right, self.grid_size):
            lines.append(QLineF(x, top, x, bottom).toLine())
        # Horizontal lines
        for y in range(first_top, bottom, self.grid_size):
            lines.append(QLineF(left, y, right, y).toLine())
        painter.drawLines(lines)
        
        # 2. Major grid lines (Thicker)
        painter.setPen(QPen(QColor("#111111"), 2))
        lines_thick = []
        major_spacing = self.grid_size * self.grid_squares
        
        first_left_major = left - (left % major_spacing)
        first_top_major = top - (top % major_spacing)

        for x in range(first_left_major, right, major_spacing):
            lines_thick.append(QLineF(x, top, x, bottom).toLine())
        for y in range(first_top_major, bottom, major_spacing):
            lines_thick.append(QLineF(left, y, right, y).toLine())
            
        painter.drawLines(lines_thick)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """
        Renders the temporary 'draft wire' when the user is dragging from a socket.
        """
        if self.draft_wire_path:
            painter.setPen(QPen(QColor("#FF9800"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.draft_wire_path)

    # --- Event Handling ---

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Detects clicks on Sockets to start wiring.
        """
        # Check what was clicked
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        
        if isinstance(item, SocketItem):
            # Start creating a wire
            self.draft_wire_source = item
            event.accept()
        else:
            # Normal selection behavior (Node selection)
            super().mousePressEvent(event)
            # Notify controller of selection change
            self.selection_changed_custom.emit(self.selectedItems())

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Updates the draft wire visual or handles node movement.
        """
        if self.draft_wire_source:
            # We are dragging a wire
            start_pos = self.draft_wire_source.scenePos()
            end_pos = event.scenePos()
            
            # Calculate Bezier curve for the draft wire
            path = QPainterPath()
            path.moveTo(start_pos)
            
            dx = end_pos.x() - start_pos.x()
            dy = end_pos.y() - start_pos.y()
            
            # Control points for smooth curvature
            ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
            ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())
            
            path.cubicTo(ctrl1, ctrl2, end_pos)
            
            self.draft_wire_path = path
            self.update() # Trigger redraw of foreground
            event.accept()
        else:
            # Normal behavior (e.g. dragging a node)
            super().mouseMoveEvent(event)
            
            # If items are selected and we are dragging, we could emit 'node_moved' here
            # For now, we rely on QGraphicsItem's internal ItemIsMovable flag
            if self.selectedItems() and event.buttons() & Qt.MouseButton.LeftButton:
                 # Update connected wires for moving nodes
                 for item in self.selectedItems():
                     if isinstance(item, NodeItem):
                         # In a real impl, we might force update connected wires here
                         # But WireItem usually updates via scene interaction or signals
                         pass

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Completes the wire connection or cancels the drag.
        """
        if self.draft_wire_source:
            # Find what we released over
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            
            # Check if we released over a DIFFERENT socket
            if isinstance(item, SocketItem) and item != self.draft_wire_source:
                # Request connection from Controller
                self.connection_requested.emit(self.draft_wire_source, item)
            
            # Reset state
            self.draft_wire_source = None
            self.draft_wire_path = None
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
