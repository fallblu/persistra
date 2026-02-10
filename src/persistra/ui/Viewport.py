from PySide6.QtWidgets import QWidget, QStackedWidget

class Viewport(QStackedWidget):

    def __init__(self):
        super().__init__()
        self.addWidget(QWidget())

