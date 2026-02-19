from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor

class NodeBrowser(QListWidget):
    """
    Displays a list of available operations.
    Allows users to drag items onto the GraphCanvas.
    Ref: README.md Section 4.1
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        
        # Styling to match dark theme
        # FIX: Added 'alternate-background-color' to ensure readability on alternating rows
        self.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                alternate-background-color: #2E2E2E; 
                color: #DDD;
                border: 1px solid #3E3E42;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #37373D;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
        """)

    def add_operation(self, name):
        """Adds an operation name to the list."""
        item = QListWidgetItem(name)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        self.addItem(item)

    def startDrag(self, supportedActions):
        """
        Custom drag event to package the operation name.
        """
        item = self.currentItem()
        if not item:
            return
            
        op_name = item.text()
        
        # 1. Create Mime Data (Standard Text)
        mime_data = QMimeData()
        mime_data.setText(op_name)
        
        # 2. Create Drag Object
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        
        # 3. Create a visual pixmap for the drag cursor
        pixmap = QPixmap(100, 30)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setBrush(QColor("#444"))
        painter.setPen(QColor("#FFF"))
        painter.drawRect(0, 0, 99, 29)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, op_name)
        painter.end()
        
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        
        drag.exec(supportedActions)
