from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QWidget

from persistra.ui.widgets.canvas import ProjectCanvas
from persistra.ui.widgets.dashboard import Dashboard
from persistra.ui.widgets.node_browser import NodeBrowser
from persistra.ui.widgets.viewport import Viewport

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Persistra")

        self._menu = self.menuBar()
        file_menu = self._menu.addMenu("&File")

        file_menu.addAction("Exit", self.close)

        self._status = self.statusBar()
        
        self._main = QWidget()
        self.setCentralWidget(self._main)

        self.setup_layout()

        geometry = self.screen().availableGeometry()
        self.setFixedSize(geometry.width() * 0.8, geometry.height() * 0.8)

    def setup_layout(self):
        self._layout = QHBoxLayout()
        self._main.setLayout(self._layout)

        self._project_canvas = ProjectCanvas()
        self._node_browser = NodeBrowser()

        llayout = QVBoxLayout()
        llayout.addWidget(self._node_browser, 4)
        llayout.addWidget(self._project_canvas, 6)

        self._viewport = Viewport()
        self._dashboard = Dashboard()

        rlayout = QVBoxLayout()
        rlayout.addWidget(self._viewport, 6)
        rlayout.addWidget(self._dashboard, 4)

        self._layout.addLayout(llayout, 6)
        self._layout.addLayout(rlayout, 10)

