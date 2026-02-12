from PySide6.QtCore import Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QVBoxLayout

from persistra.ui.Workspace import Workspace


class MainWindow(QMainWindow):

    def __init__(self, analysis=None):
        super().__init__()

        self.create_menus()
        self.create_workspace()

        geometry = self.screen().availableGeometry()
        self.setFixedSize(geometry.width() * 0.8, geometry.height() * 0.7)

    
    def create_menus(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

    def create_action(self):
        pass

    def create_workspace(self, analysis=None):
        self._workspace = Workspace(analysis)
        self.setCentralWidget(self._workspace)


