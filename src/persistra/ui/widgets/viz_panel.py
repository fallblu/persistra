import pandas as pd
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableView, 
                               QLabel, QHeaderView)
from PySide6.QtCore import Qt, QAbstractTableModel
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# --- Pandas Table Model ---
class PandasModel(QAbstractTableModel):
    """
    A custom model to interface between Pandas DataFrames and QTableView.
    Ref: README.md Section 4.3 (Viz Panel)
    """
    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])
            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section])
        return None

# --- Main Viz Panel Widget ---
class VizPanel(QWidget):
    """
    The viewer panel for results (Plots and Tables).
    Listens for node selection and displays output if available.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Tabs for different view modes
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # Tab 1: Plot Viewer
        self.plot_widget = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_widget)
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(5, 3)))
        self.plot_layout.addWidget(self.canvas)
        self.tabs.addTab(self.plot_widget, "Plot Viewer")
        
        # Tab 2: Table Viewer
        self.table_view = QTableView()
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.table_view, "Table Viewer")
        
        # Current Node Tracker
        self.current_node = None
        
        # Initial State: Show placeholder
        self.reset_views()

    def reset_views(self):
        """Clears current visualizations."""
        self.canvas.figure.clear()
        self.canvas.draw()
        self.table_view.setModel(None)

    def set_node(self, node):
        """
        Updates the panel based on the selected node.
        """
        self.current_node = node
        self.reset_views()
        
        if node is None:
            return

        # --- MOCK LOGIC: Simulate finding data based on node type ---
        # In the real app, we would access node.cached_output
        op_type = node.operation.__class__.__name__
        
        if op_type == "PersistencePlot" or op_type == "LinePlot":
            self.tabs.setCurrentIndex(0) # Switch to Plot Tab
            self._mock_render_plot(op_type)
            
        elif op_type in ["CSVLoader", "SlidingWindow", "DistanceMatrix"]:
            self.tabs.setCurrentIndex(1) # Switch to Table Tab
            self._mock_render_table(op_type)
        
        else:
            # Default or unknown
            pass

    def update_visualization(self, node, result):
        """
        Updates the visualization panel with computation results.
        Called when a background computation finishes.
        :param node: The Node that was computed.
        :param result: The computation result dictionary (used in later phases
                       to render real output data).
        """
        self.current_node = node
        self.reset_views()

        if node is None or result is None:
            return

        # TODO: In future phases, render actual results from the result dict.
        self.set_node(node)

    def _mock_render_plot(self, op_type):
        """Generates a dummy plot for UI testing."""
        ax = self.canvas.figure.add_subplot(111)
        if op_type == "PersistencePlot":
            # Draw a mock persistence diagram (points above diagonal)
            x = np.random.rand(20)
            y = x + np.random.rand(20) * 0.5
            ax.scatter(x, y, c='blue', alpha=0.6)
            ax.plot([0, 1], [0, 1], 'k--', alpha=0.5) # Diagonal
            ax.set_title("Persistence Diagram (Mock)")
        else:
            # Generic Line Plot
            x = np.linspace(0, 10, 100)
            y = np.sin(x)
            ax.plot(x, y)
            ax.set_title("Time Series (Mock)")
            
        self.canvas.draw()

    def _mock_render_table(self, op_type):
        """Generates a dummy table for UI testing."""
        if op_type == "CSVLoader":
            data = pd.DataFrame({
                'Date': pd.date_range(start='1/1/2023', periods=5),
                'Price': np.random.rand(5) * 100,
                'Volume': np.random.randint(100, 1000, 5)
            })
        elif op_type == "SlidingWindow":
            data = pd.DataFrame(np.random.rand(5, 4), columns=['t-3', 't-2', 't-1', 't'])
        else:
            data = pd.DataFrame({'Info': ['No data available']})
            
        model = PandasModel(data)
        self.table_view.setModel(model)
