from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QTableWidget

from persistra.core.TimeSeriesAnalysis import TimeSeriesAnalysis

class Workspace(QWidget):

    def __init__(self, analysis=None):
        super().__init__()

        self._analysis = analysis if analysis else TimeSeriesAnalysis()
        
        self.table = QTableWidget()

        llayout = QVBoxLayout()
        llayout.addWidget(self.table)

        rlayout = QVBoxLayout()
        rlayout.addWidget(QWidget())
        
        layout = QHBoxLayout(self)
        layout.addLayout(llayout, 2)
        layout.addLayout(rlayout, 5)

    def populate_table(self):
        pass
