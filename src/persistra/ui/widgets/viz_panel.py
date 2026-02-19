import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QStackedLayout, QTableView, QVBoxLayout, QWidget

from persistra.core.objects import (
    DataWrapper,
    FigureWrapper,
    InteractiveFigure,
    TimeSeries,
)


# --- Pandas Table Model ---
class PandasModel(QAbstractTableModel):
    """
    A custom model to interface between Pandas DataFrames and QTableView.
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


# --- Sub-views for the stacked layout ---

class PlaceholderView(QWidget):
    """'Select a node to view' placeholder."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Select a node to view its output")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class MatplotlibView(QWidget):
    """Renders a Matplotlib Figure via FigureCanvasQTAgg."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvasQTAgg(self._figure)
        layout.addWidget(self.canvas)

    def set_figure(self, fig):
        """Replace the displayed figure."""
        self.canvas.figure = fig
        self.canvas.draw()

    def clear(self):
        self._figure.clear()
        self.canvas.figure = self._figure
        self.canvas.draw()


class DataTableView(QWidget):
    """Displays tabular data via QTableView + PandasModel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableView()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def set_data(self, data):
        if isinstance(data, pd.DataFrame):
            self.table.setModel(PandasModel(data))
        elif isinstance(data, pd.Series):
            self.table.setModel(PandasModel(data.to_frame()))
        elif isinstance(data, np.ndarray) and data.ndim == 2:
            self.table.setModel(PandasModel(pd.DataFrame(data)))
        else:
            self.table.setModel(None)

    def clear(self):
        self.table.setModel(None)


class PointCloudView(QWidget):
    """Placeholder for pyqtgraph GLViewWidget (3D point cloud)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel("3D viewer — pyqtgraph GLViewWidget")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def set_data(self, data):
        self.label.setText(f"3D data: {type(data).__name__}")


class CodeEditorView(QWidget):
    """Placeholder for code editor (PythonExpression node)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel("Code editor view")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def set_node(self, node):
        self.label.setText(f"Code editor for: {node.operation.name}")


class SpreadsheetView(QWidget):
    """Placeholder for spreadsheet (ManualDataEntry node)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel("Spreadsheet view")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def set_node(self, node):
        self.label.setText(f"Spreadsheet for: {node.operation.name}")


# --- Main Viz Panel Widget ---

class VizPanel(QWidget):
    """
    Dynamic visualization panel.
    Inspects the selected node's output type and chooses the appropriate display.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.stack = QStackedLayout(self)

        # Pre-created views
        self.placeholder = PlaceholderView()
        self.matplotlib_view = MatplotlibView()
        self.table_view = DataTableView()
        self.gl_view = PointCloudView()
        self.code_editor = CodeEditorView()
        self.spreadsheet_view = SpreadsheetView()

        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.matplotlib_view)
        self.stack.addWidget(self.table_view)
        self.stack.addWidget(self.gl_view)
        self.stack.addWidget(self.code_editor)
        self.stack.addWidget(self.spreadsheet_view)

        # Current Node Tracker
        self.current_node = None

    def display_node(self, node):
        """Inspect the node and switch to the appropriate view."""
        self.current_node = node
        if node is None:
            self.stack.setCurrentWidget(self.placeholder)
            return

        # Lazy import to avoid circular dependencies
        from persistra.operations.io import ManualDataEntry
        from persistra.operations.utility import PythonExpression

        # Special node types with custom editors
        if isinstance(node.operation, PythonExpression):
            self.code_editor.set_node(node)
            self.stack.setCurrentWidget(self.code_editor)
            return

        if isinstance(node.operation, ManualDataEntry):
            self.spreadsheet_view.set_node(node)
            self.stack.setCurrentWidget(self.spreadsheet_view)
            return

        # Check cached outputs
        outputs = node._cached_outputs
        if not outputs:
            self.stack.setCurrentWidget(self.placeholder)
            return

        # Route based on output data type
        first_output = next(iter(outputs.values()), None)

        if isinstance(first_output, FigureWrapper):
            self.matplotlib_view.set_figure(first_output.data)
            self.stack.setCurrentWidget(self.matplotlib_view)

        elif isinstance(first_output, InteractiveFigure):
            if first_output.renderer == "pyqtgraph":
                self.gl_view.set_data(first_output.data)
                self.stack.setCurrentWidget(self.gl_view)

        elif isinstance(first_output, (TimeSeries, DataWrapper)):
            self.table_view.set_data(first_output.data)
            self.stack.setCurrentWidget(self.table_view)

        else:
            self.stack.setCurrentWidget(self.placeholder)

    def set_node(self, node):
        """Alias for display_node (backward compatibility)."""
        self.display_node(node)

    def update_visualization(self, node, result):
        """
        Updates the visualization panel with computation results.
        Called when a background computation finishes.
        """
        self.display_node(node)

    def reset_views(self):
        """Clears current visualizations."""
        self.matplotlib_view.clear()
        self.table_view.clear()
        self.stack.setCurrentWidget(self.placeholder)
