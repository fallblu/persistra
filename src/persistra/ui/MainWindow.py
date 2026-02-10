from PySide6.QtCore import Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QVBoxLayout

from persistra.ui.MplCanvas import MplCanvas
from persistra.ui.Viewport import Viewport


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._viewport = Viewport()
        self.setCentralWidget(self._viewport)

        self.create_menus()

        geometry = self.screen().availableGeometry()
        self.setFixedSize(geometry.width() * 0.8, geometry.height() * 0.7)

    
    def create_menus(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

    def create_action(self):
        pass

    def create_toolbar(self):
        pass

    @Slot()
    def new_analysis(self):
        pass

    @Slot()
    def save_analysis(self):
        pass

    @Slot()
    def save_analysis_as(self):
        pass

    @Slot()
    def load_analysis(self):
        pass

