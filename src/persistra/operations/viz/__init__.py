"""
src/persistra/operations/viz/__init__.py

Operations that generate Visualizations (Matplotlib Figures).

Tier 1 — Simple plot nodes (single data input → FigureWrapper + PlotData).
Tier 2 — Composition nodes (combine PlotData / FigureWrapper).
Tier 3 — Interactive / 3D nodes (InteractiveFigure output).
"""
import matplotlib.pyplot as plt
import numpy as np

try:
    import persim
except ImportError:
    persim = None

from persistra.core.objects import (
    BoolParam,
    ChoiceParam,
    DataWrapper,
    FigureWrapper,
    FloatParam,
    InteractiveFigure,
    IntParam,
    PersistenceDiagram,
    PlotData,
    StringParam,
    TimeSeries,
)
from persistra.core.project import Operation, SocketDef
from persistra.core.types import ConcreteType

# =========================================================================
# Tier 1 — Simple Plot Nodes
# =========================================================================

class LinePlot(Operation):
    name = "Line Plot"
    description = "Plots a standard time series line chart."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(TimeSeries))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            StringParam('title', 'Title', default='Time Series'),
            StringParam('color', 'Color', default=''),
            BoolParam('grid', 'Show Grid', default=True),
        ]

    def execute(self, inputs, params, cancel_event=None):
        df = inputs['data'].data
        title = params.get('title', 'Time Series')
        color = params.get('color', '') or None
        grid = params.get('grid', True)

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        df.plot(ax=ax, color=color)
        ax.set_title(title)
        ax.grid(grid)
        fig.tight_layout()

        style = {'color': color, 'label': title}
        x = np.arange(len(df))
        y = df.iloc[:, 0].values if hasattr(df, 'iloc') else df.values
        plot_data = PlotData(x=x, y=y, plot_type="line", style=style)

        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class ScatterPlot(Operation):
    name = "Scatter Plot"
    description = "Scatter plot from a DataFrame with 2+ columns."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            StringParam('x_column', 'X Column', default='0'),
            StringParam('y_column', 'Y Column', default='1'),
            StringParam('color', 'Color', default='blue'),
            FloatParam('point_size', 'Point Size', default=20.0, min_val=1.0, max_val=500.0),
        ]

    def execute(self, inputs, params, cancel_event=None):
        import pandas as pd

        raw = inputs['data'].data
        if isinstance(raw, pd.DataFrame):
            df = raw
        elif isinstance(raw, np.ndarray):
            df = pd.DataFrame(raw)
        else:
            raise TypeError("ScatterPlot requires a DataFrame or numpy array input")

        x_col = params.get('x_column', '0').strip()
        y_col = params.get('y_column', '1').strip()

        # Resolve column by index or name
        def _resolve(col_str, frame):
            if col_str.isdigit():
                return frame.iloc[:, int(col_str)]
            return frame[col_str]

        x = _resolve(x_col, df).values
        y = _resolve(y_col, df).values
        color = params.get('color', 'blue')
        size = params.get('point_size', 20.0)

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        ax.scatter(x, y, c=color, s=size, alpha=0.7)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title("Scatter Plot")
        fig.tight_layout()

        style = {'color': color, 'marker': 'o', 'size': size}
        plot_data = PlotData(x=x, y=y, plot_type="scatter", style=style)

        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class Histogram(Operation):
    name = "Histogram"
    description = "Histogram of a TimeSeries or numeric array."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            IntParam('bins', 'Bins', default=30, min_val=2, max_val=500),
            StringParam('color', 'Color', default='steelblue'),
            BoolParam('density', 'Density', default=False),
        ]

    def execute(self, inputs, params, cancel_event=None):
        import pandas as pd

        raw = inputs['data'].data
        if isinstance(raw, (pd.DataFrame, pd.Series)):
            values = raw.iloc[:, 0].values if isinstance(raw, pd.DataFrame) else raw.values
        elif isinstance(raw, np.ndarray):
            values = raw.ravel()
        else:
            raise TypeError("Histogram requires numeric data")

        bins = params.get('bins', 30)
        color = params.get('color', 'steelblue')
        density = params.get('density', False)

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        ax.hist(values, bins=bins, color=color, density=density, edgecolor='black', alpha=0.7)
        ax.set_title("Histogram")
        ax.set_ylabel("Density" if density else "Count")
        fig.tight_layout()

        style = {'color': color, 'bins': bins, 'density': density}
        plot_data = PlotData(x=values, y=np.array([]), plot_type="histogram", style=style)

        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class PersistenceDiagramPlot(Operation):
    name = "Persistence Diagram Plot"
    description = "Scatter-style persistence diagram (birth vs. death)."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('diagram', ConcreteType(PersistenceDiagram))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            StringParam('dimensions', 'Dimensions (comma-separated)', default='0,1'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        dgms = inputs['diagram'].data
        dims_str = params.get('dimensions', '0,1')
        dims = [int(d.strip()) for d in dims_str.split(',') if d.strip().isdigit()]

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple']
        all_x, all_y = [], []
        for dim in dims:
            if dim < len(dgms) and len(dgms[dim]) > 0:
                pts = np.asarray(dgms[dim])
                births = pts[:, 0]
                deaths = pts[:, 1]
                c = colors[dim % len(colors)]
                ax.scatter(births, deaths, c=c, s=20, alpha=0.7, label=f"H{dim}")
                all_x.extend(births.tolist())
                all_y.extend(deaths.tolist())

        # Draw diagonal
        if all_x and all_y:
            lo = min(min(all_x), min(all_y))
            hi = max(max(all_x), max(all_y))
            ax.plot([lo, hi], [lo, hi], 'k--', alpha=0.4)

        ax.set_xlabel("Birth")
        ax.set_ylabel("Death")
        ax.set_title("Persistence Diagram")
        ax.legend()
        fig.tight_layout()

        plot_data = PlotData(
            x=np.array(all_x), y=np.array(all_y),
            plot_type="scatter", style={'label': 'persistence'}
        )
        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class BarcodePlot(Operation):
    name = "Barcode Plot"
    description = "Barcode-style plot of persistence intervals."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('diagram', ConcreteType(PersistenceDiagram))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            StringParam('dimensions', 'Dimensions (comma-separated)', default='0,1'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        dgms = inputs['diagram'].data
        dims_str = params.get('dimensions', '0,1')
        dims = [int(d.strip()) for d in dims_str.split(',') if d.strip().isdigit()]

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        colors = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple']
        bar_idx = 0
        for dim in dims:
            if dim < len(dgms) and len(dgms[dim]) > 0:
                pts = np.asarray(dgms[dim])
                c = colors[dim % len(colors)]
                for birth, death in pts:
                    ax.barh(bar_idx, death - birth, left=birth, height=0.8,
                            color=c, alpha=0.7)
                    bar_idx += 1

        ax.set_xlabel("Parameter")
        ax.set_ylabel("Feature")
        ax.set_title("Barcode Plot")
        ax.invert_yaxis()
        fig.tight_layout()

        plot_data = PlotData(
            x=np.array([]), y=np.array([]),
            plot_type="barcode", style={'label': 'barcode'}
        )
        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class Heatmap(Operation):
    name = "Heatmap"
    description = "2D heatmap of a matrix or DistanceMatrix."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [
            SocketDef('plot', ConcreteType(FigureWrapper)),
            SocketDef('plot_data', ConcreteType(DataWrapper)),
        ]
        self.parameters = [
            StringParam('colormap', 'Colormap', default='viridis'),
            BoolParam('annotate', 'Annotate Cells', default=False),
        ]

    def execute(self, inputs, params, cancel_event=None):
        import pandas as pd

        raw = inputs['data'].data
        if isinstance(raw, pd.DataFrame):
            matrix = raw.values
        elif isinstance(raw, np.ndarray):
            matrix = raw
        else:
            raise TypeError("Heatmap requires a 2D array or DataFrame")

        if matrix.ndim != 2:
            raise ValueError("Heatmap data must be 2-dimensional")

        cmap = params.get('colormap', 'viridis')
        annotate = params.get('annotate', False)

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)
        im = ax.imshow(matrix, cmap=cmap, aspect='auto')
        fig.colorbar(im, ax=ax)

        if annotate:
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    ax.text(j, i, f"{matrix[i, j]:.2f}", ha='center', va='center',
                            fontsize=6, color='white')

        ax.set_title("Heatmap")
        fig.tight_layout()

        plot_data = PlotData(
            x=np.arange(matrix.shape[1]), y=np.arange(matrix.shape[0]),
            plot_type="heatmap", style={'colormap': cmap}
        )
        return {'plot': FigureWrapper(fig), 'plot_data': plot_data}


class PersistencePlot(Operation):
    name = "Persistence Plot"
    description = "Plots the Persistence Diagram (H0, H1, etc) using persim."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('diagram', ConcreteType(PersistenceDiagram))]
        self.outputs = [SocketDef('plot', ConcreteType(FigureWrapper))]
        self.parameters = [
            ChoiceParam('type', 'Plot Type', options=['scatter', 'barcode'], default='scatter'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        if persim is None:
            raise ImportError("The 'persim' library is not installed.")

        dgms = inputs['diagram'].data
        plot_type = params['type']

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        if plot_type == 'scatter':
            persim.plot_diagrams(dgms, ax=ax, show=False)
        elif plot_type == 'barcode':
            persim.plot_diagrams(dgms, ax=ax, show=False, lifetime=True)

        ax.set_title("Persistence Diagram")

        return {'plot': FigureWrapper(fig)}


# =========================================================================
# Tier 2 — Composition Nodes
# =========================================================================

class OverlayPlot(Operation):
    name = "Overlay Plot"
    description = "Overlays multiple PlotData series on shared axes."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [
            SocketDef('plot_data_1', ConcreteType(DataWrapper)),
            SocketDef('plot_data_2', ConcreteType(DataWrapper)),
        ]
        self.outputs = [SocketDef('plot', ConcreteType(FigureWrapper))]
        self.parameters = [
            StringParam('title', 'Title', default='Overlay Plot'),
            BoolParam('legend', 'Show Legend', default=True),
            StringParam('x_label', 'X Label', default=''),
            StringParam('y_label', 'Y Label', default=''),
        ]

    def execute(self, inputs, params, cancel_event=None):
        title = params.get('title', 'Overlay Plot')
        legend = params.get('legend', True)
        x_label = params.get('x_label', '')
        y_label = params.get('y_label', '')

        fig = plt.Figure(figsize=(5, 4), dpi=100)
        ax = fig.add_subplot(111)

        for key in sorted(inputs.keys()):
            pd_obj = inputs[key]
            if not isinstance(pd_obj, PlotData):
                continue
            label = pd_obj.style.get('label', key)
            color = pd_obj.style.get('color', None)
            if pd_obj.plot_type == "line":
                ax.plot(pd_obj.x, pd_obj.y, label=label, color=color)
            elif pd_obj.plot_type == "scatter":
                size = pd_obj.style.get('size', 20)
                ax.scatter(pd_obj.x, pd_obj.y, label=label, c=color, s=size, alpha=0.7)
            else:
                ax.plot(pd_obj.x, pd_obj.y, label=label, color=color)

        ax.set_title(title)
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        if legend:
            ax.legend()
        fig.tight_layout()

        return {'plot': FigureWrapper(fig)}


class SubplotGrid(Operation):
    name = "Subplot Grid"
    description = "Arranges N FigureWrapper inputs into a subplot grid."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [
            SocketDef('figure_1', ConcreteType(FigureWrapper)),
            SocketDef('figure_2', ConcreteType(FigureWrapper)),
        ]
        self.outputs = [SocketDef('plot', ConcreteType(FigureWrapper))]
        self.parameters = [
            IntParam('rows', 'Rows', default=1, min_val=1, max_val=10),
            IntParam('cols', 'Columns', default=2, min_val=1, max_val=10),
            BoolParam('shared_axes', 'Shared Axes', default=False),
        ]

    def execute(self, inputs, params, cancel_event=None):
        rows = params.get('rows', 1)
        cols = params.get('cols', 2)
        # shared_axes param reserved for future shared-axis support

        # Collect input figures in sorted key order
        figures = []
        for key in sorted(inputs.keys()):
            wrapper = inputs[key]
            if isinstance(wrapper, FigureWrapper):
                figures.append(wrapper.data)

        # shared_axes reserved for future shared-axis support
        fig = plt.Figure(figsize=(5 * cols, 4 * rows), dpi=100)

        # Re-create axes on the new non-pyplot figure
        for idx, src_fig in enumerate(figures):
            if idx >= rows * cols:
                break
            ax = fig.add_subplot(rows, cols, idx + 1)
            # Copy lines/collections/images from source figure axes
            if src_fig.axes:
                src_ax = src_fig.axes[0]
                for line in src_ax.get_lines():
                    ax.plot(line.get_xdata(), line.get_ydata(),
                            color=line.get_color(), linestyle=line.get_linestyle(),
                            linewidth=line.get_linewidth(), label=line.get_label())
                for coll in src_ax.collections:
                    offsets = coll.get_offsets()
                    if len(offsets) > 0:
                        ax.scatter(offsets[:, 0], offsets[:, 1], alpha=0.7)
                for im in src_ax.get_images():
                    ax.imshow(im.get_array(), aspect='auto')
                ax.set_title(src_ax.get_title())

        # Close the temporary pyplot figure
        plt.close('all')

        fig.tight_layout()
        return {'plot': FigureWrapper(fig)}


# =========================================================================
# Tier 3 — Interactive / 3D Nodes
# =========================================================================

class ThreeDScatter(Operation):
    name = "3D Scatter"
    description = "3D scatter plot from a PointCloud or DataFrame with 3+ columns."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [SocketDef('plot', ConcreteType(FigureWrapper))]
        self.parameters = [
            StringParam('x_column', 'X Column', default='0'),
            StringParam('y_column', 'Y Column', default='1'),
            StringParam('z_column', 'Z Column', default='2'),
            FloatParam('point_size', 'Point Size', default=20.0, min_val=1.0, max_val=500.0),
            StringParam('color', 'Color', default='blue'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        import pandas as pd

        raw = inputs['data'].data
        if isinstance(raw, pd.DataFrame):
            df = raw
        elif isinstance(raw, np.ndarray):
            df = pd.DataFrame(raw)
        else:
            raise TypeError("3D Scatter requires a DataFrame or numpy array input")

        def _resolve(col_str, frame):
            col_str = col_str.strip()
            if col_str.isdigit():
                return frame.iloc[:, int(col_str)].values
            return frame[col_str].values

        x = _resolve(params.get('x_column', '0'), df)
        y = _resolve(params.get('y_column', '1'), df)
        z = _resolve(params.get('z_column', '2'), df)
        color = params.get('color', 'blue')
        size = params.get('point_size', 20.0)

        fig = plt.Figure(figsize=(6, 5), dpi=100)
        ax = fig.add_subplot(111, projection='3d')
        ax.scatter(x, y, z, c=color, s=size, alpha=0.7)
        ax.set_xlabel(params.get('x_column', '0'))
        ax.set_ylabel(params.get('y_column', '1'))
        ax.set_zlabel(params.get('z_column', '2'))
        ax.set_title("3D Scatter")
        fig.tight_layout()

        return {'plot': FigureWrapper(fig)}


class InteractivePlot(Operation):
    name = "Interactive Plot"
    description = "Interactive line/scatter plot (InteractiveFigure output)."
    category = "Visualization"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef('data', ConcreteType(DataWrapper))]
        self.outputs = [SocketDef('plot', ConcreteType(DataWrapper))]
        self.parameters = [
            ChoiceParam('plot_type', 'Plot Type', options=['line', 'scatter'], default='line'),
            StringParam('title', 'Title', default='Interactive Plot'),
        ]

    def execute(self, inputs, params, cancel_event=None):
        import pandas as pd

        raw = inputs['data'].data
        if isinstance(raw, (pd.DataFrame, pd.Series)):
            df = raw if isinstance(raw, pd.DataFrame) else raw.to_frame()
        elif isinstance(raw, np.ndarray):
            df = pd.DataFrame(raw)
        else:
            raise TypeError("InteractivePlot requires a DataFrame, Series, or numpy array")

        plot_type = params.get('plot_type', 'line')
        title = params.get('title', 'Interactive Plot')

        # Store data and config for interactive rendering in the VizPanel
        interactive_data = {
            'dataframe': df,
            'plot_type': plot_type,
            'title': title,
        }

        return {'plot': InteractiveFigure(interactive_data, renderer="pyqtgraph")}
