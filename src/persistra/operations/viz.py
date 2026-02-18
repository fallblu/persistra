"""
src/persistra/operations/viz.py

Operations that generate Visualizations (Matplotlib Figures).
"""
import matplotlib.pyplot as plt
import matplotlib.figure
try:
    import persim
except ImportError:
    persim = None

from persistra.core.project import Operation
from persistra.core.objects import TimeSeries, PersistenceDiagram, DataWrapper, ChoiceParam

class FigureWrapper(DataWrapper):
    """Wraps a Matplotlib Figure for the UI to render."""
    def __init__(self, data: matplotlib.figure.Figure, metadata=None):
        super().__init__(data, metadata)

class LinePlot(Operation):
    name = "Line Plot"
    description = "Plots a standard time series."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'data', 'type': TimeSeries}]
        self.outputs = [{'name': 'plot', 'type': FigureWrapper}]
        self.parameters = [] # Could add 'Color', 'Style' later

    def execute(self, inputs, params):
        df = inputs['data'].data
        
        # Create a generic Figure
        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        
        # Plot
        df.plot(ax=ax)
        ax.set_title("Time Series")
        ax.grid(True)
        fig.tight_layout()

        return {'plot': FigureWrapper(fig)}


class PersistencePlot(Operation):
    name = "Persistence Plot"
    description = "Plots the Persistence Diagram (H0, H1, etc)."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [{'name': 'diagram', 'type': PersistenceDiagram}]
        self.outputs = [{'name': 'plot', 'type': FigureWrapper}]
        
        self.parameters = [
            ChoiceParam('type', 'Plot Type', options=['scatter', 'barcode'], default='scatter')
        ]

    def execute(self, inputs, params):
        if persim is None:
            raise ImportError("The 'persim' library is not installed.")

        dgms = inputs['diagram'].data
        plot_type = params['type']

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        # Persim typically plots to the "current" axes (plt.gca()).
        # We need to temporarily set the context or use library features that accept 'ax'.
        # Persim's plot_diagrams accepts an 'ax' parameter.
        
        if plot_type == 'scatter':
            persim.plot_diagrams(dgms, ax=ax, show=False)
        elif plot_type == 'barcode':
            # Barcode plotting logic might vary, basic fallback to scatter if barcode specific func missing
            persim.plot_diagrams(dgms, ax=ax, show=False, lifetime=True) # pseudo-barcode style
        
        ax.set_title("Persistence Diagram")
        
        return {'plot': FigureWrapper(fig)}
