from PySide6.QtWidgets import QTreeWidget

class NodeBrowser(QTreeWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Name"])
