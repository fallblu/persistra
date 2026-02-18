import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QGridLayout, 
                             QGraphicsView, QLabel, QFrame, QStatusBar)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter

# Import Custom UI
from persistra.ui.graph.scene import GraphScene
from persistra.ui.graph.manager import GraphManager
from persistra.ui.widgets.context_panel import ContextPanel
from persistra.ui.widgets.node_browser import NodeBrowser
from persistra.ui.widgets.viz_panel import VizPanel

# Import REAL Backend
from persistra.core.project import Project
from persistra.operations import OPERATIONS_REGISTRY 

class GraphView(QGraphicsView):
    # ... (Same implementation as Step 5) ...
    def __init__(self, scene, manager, parent=None):
        super().__init__(scene, parent)
        self.manager = manager 
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        if event.angleDelta().y() > 0: self.scale(zoom_in_factor, zoom_in_factor)
        else: self.scale(zoom_out_factor, zoom_out_factor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText(): event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText(): event.accept()
        else: event.ignore()

    def dropEvent(self, event):
        op_name = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        self.manager.add_node(op_name, scene_pos.x(), scene_pos.y())
        event.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Persistra - Visual Analysis Tool")
        self.resize(1280, 800) 
        
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Initialize REAL Project Model
        self.project_model = Project()

        # Layout Setup
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QGridLayout(central_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        for c in range(16): self.layout.setColumnStretch(c, 1)
        for r in range(10): self.layout.setRowStretch(r, 1)
        
        # 1. Node Browser
        self.node_browser = NodeBrowser()
        # Populate from REAL Registry
        for op_name in OPERATIONS_REGISTRY.keys():
            self.node_browser.add_operation(op_name)
        self.layout.addWidget(self.node_browser, 0, 0, 4, 6)
        
        # 2. Graph Editor
        self.scene = GraphScene()
        self.manager = GraphManager(self.scene, self.project_model)
        self.view = GraphView(self.scene, self.manager)
        self.layout.addWidget(self.view, 4, 0, 6, 6)
        
        # 3. Viz Panel
        self.viz_panel = VizPanel()
        self.layout.addWidget(self.viz_panel, 0, 6, 6, 10)
        
        # 4. Context Panel
        self.context_panel = ContextPanel() 
        self.context_panel.setStyleSheet("background-color: #2A2A2A; color: #EEE;")
        self.layout.addWidget(self.context_panel, 6, 6, 4, 10)

        # --- Connections ---
        # Node Selection -> Update Context Panel
        self.manager.node_selected.connect(self.context_panel.set_node)
        
        # Computation Status -> Status Bar
        self.manager.computation_started.connect(self.status_bar.showMessage)
        
        # Computation Result -> Viz Panel
        # Note: We connect the RESULT directly to the viz panel
        self.manager.computation_finished.connect(lambda res: self.viz_panel.update_visualization(self.manager.current_worker.node, res))

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
