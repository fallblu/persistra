from matplotlib.backends.backend_qtagg import FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QWidget, QHBoxLayout

class Viewport(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout()
        self.setLayout(self._layout)
        self._figure = FigureCanvas(Figure(figsize=(8,5)))
        self._layout.addWidget(self._figure)
