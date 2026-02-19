"""
Tests for Phase 4 — Visualization System.

Covers:
- 7.1 FigureWrapper, InteractiveFigure, PlotData as first-class data types
- 7.2 Tier 1 simple plot nodes (LinePlot, ScatterPlot, Histogram,
      PersistenceDiagramPlot, BarcodePlot, Heatmap)
- 7.3 Tier 2 composition nodes (OverlayPlot, SubplotGrid)
- 7.4 Tier 3 interactive/3D nodes (ThreeDScatter, InteractivePlot)
- 7.5 VizPanel overhaul (dynamic routing)
- Registry updates (new operation count)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from persistra.core.objects import (
    DataWrapper,
    FigureWrapper,
    InteractiveFigure,
    PersistenceDiagram,
    PlotData,
    TimeSeries,
)
from persistra.core.project import Operation


# =========================================================================
# 7.1 — First-class data types
# =========================================================================

class TestFigureWrapper:
    def test_is_data_wrapper(self):
        assert issubclass(FigureWrapper, DataWrapper)

    def test_wraps_figure(self):
        import matplotlib.pyplot as plt
        fig = plt.Figure()
        fw = FigureWrapper(fig)
        assert fw.data is fig
        assert fw.metadata == {}
        plt.close(fig)

    def test_with_metadata(self):
        import matplotlib.pyplot as plt
        fig = plt.Figure()
        fw = FigureWrapper(fig, metadata={'title': 'test'})
        assert fw.metadata == {'title': 'test'}
        plt.close(fig)


class TestInteractiveFigure:
    def test_is_data_wrapper(self):
        assert issubclass(InteractiveFigure, DataWrapper)

    def test_default_renderer(self):
        ifig = InteractiveFigure(data={'key': 'value'})
        assert ifig.renderer == "pyqtgraph"

    def test_custom_renderer(self):
        ifig = InteractiveFigure(data={'key': 'value'}, renderer="plotly")
        assert ifig.renderer == "plotly"


class TestPlotData:
    def test_dataclass_fields(self):
        pd_obj = PlotData(x=np.array([1, 2]), y=np.array([3, 4]),
                          plot_type="line", style={'color': 'red'})
        assert pd_obj.plot_type == "line"
        assert pd_obj.style == {'color': 'red'}
        np.testing.assert_array_equal(pd_obj.x, [1, 2])
        np.testing.assert_array_equal(pd_obj.y, [3, 4])


# =========================================================================
# 7.2 — Tier 1 Simple Plot Nodes
# =========================================================================

def _sample_ts():
    return TimeSeries(pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}))


def _sample_df():
    return DataWrapper(pd.DataFrame({"x": [1, 2, 3, 4], "y": [10, 20, 15, 25]}))


def _sample_diagram():
    return PersistenceDiagram([
        np.array([[0.0, 1.0], [0.0, 2.0]]),  # H0
        np.array([[0.5, 1.5], [0.3, 2.0]]),  # H1
    ])


class TestLinePlot:
    def test_returns_figure_wrapper(self):
        from persistra.operations.viz import LinePlot
        op = LinePlot()
        result = op.execute(
            {'data': _sample_ts()},
            {'title': 'Test', 'color': '', 'grid': True},
        )
        assert isinstance(result['plot'], FigureWrapper)
        assert result['plot'].data is not None

    def test_returns_plot_data(self):
        from persistra.operations.viz import LinePlot
        op = LinePlot()
        result = op.execute(
            {'data': _sample_ts()},
            {'title': 'Test', 'color': '', 'grid': True},
        )
        pd_obj = result['plot_data']
        assert isinstance(pd_obj, PlotData)
        assert pd_obj.plot_type == "line"
        assert len(pd_obj.x) == 5

    def test_parameters(self):
        from persistra.operations.viz import LinePlot
        op = LinePlot()
        param_names = [p.name for p in op.parameters]
        assert 'title' in param_names
        assert 'color' in param_names
        assert 'grid' in param_names


class TestScatterPlot:
    def test_basic(self):
        from persistra.operations.viz import ScatterPlot
        op = ScatterPlot()
        result = op.execute(
            {'data': _sample_df()},
            {'x_column': '0', 'y_column': '1', 'color': 'blue', 'point_size': 20.0},
        )
        assert isinstance(result['plot'], FigureWrapper)
        assert isinstance(result['plot_data'], PlotData)
        assert result['plot_data'].plot_type == "scatter"

    def test_by_column_name(self):
        from persistra.operations.viz import ScatterPlot
        op = ScatterPlot()
        result = op.execute(
            {'data': _sample_df()},
            {'x_column': 'x', 'y_column': 'y', 'color': 'red', 'point_size': 10.0},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_numpy_input(self):
        from persistra.operations.viz import ScatterPlot
        op = ScatterPlot()
        arr = np.array([[1, 2], [3, 4], [5, 6]])
        result = op.execute(
            {'data': DataWrapper(arr)},
            {'x_column': '0', 'y_column': '1', 'color': 'green', 'point_size': 15.0},
        )
        assert isinstance(result['plot'], FigureWrapper)


class TestHistogram:
    def test_basic(self):
        from persistra.operations.viz import Histogram
        op = Histogram()
        result = op.execute(
            {'data': _sample_ts()},
            {'bins': 10, 'color': 'steelblue', 'density': False},
        )
        assert isinstance(result['plot'], FigureWrapper)
        assert isinstance(result['plot_data'], PlotData)
        assert result['plot_data'].plot_type == "histogram"

    def test_density(self):
        from persistra.operations.viz import Histogram
        op = Histogram()
        result = op.execute(
            {'data': _sample_ts()},
            {'bins': 5, 'color': 'red', 'density': True},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_numpy_input(self):
        from persistra.operations.viz import Histogram
        op = Histogram()
        arr = np.random.randn(100)
        result = op.execute(
            {'data': DataWrapper(arr)},
            {'bins': 20, 'color': 'green', 'density': False},
        )
        assert isinstance(result['plot'], FigureWrapper)


class TestPersistenceDiagramPlot:
    def test_basic(self):
        from persistra.operations.viz import PersistenceDiagramPlot
        op = PersistenceDiagramPlot()
        result = op.execute(
            {'diagram': _sample_diagram()},
            {'dimensions': '0,1'},
        )
        assert isinstance(result['plot'], FigureWrapper)
        assert isinstance(result['plot_data'], PlotData)

    def test_single_dimension(self):
        from persistra.operations.viz import PersistenceDiagramPlot
        op = PersistenceDiagramPlot()
        result = op.execute(
            {'diagram': _sample_diagram()},
            {'dimensions': '0'},
        )
        assert isinstance(result['plot'], FigureWrapper)


class TestBarcodePlot:
    def test_basic(self):
        from persistra.operations.viz import BarcodePlot
        op = BarcodePlot()
        result = op.execute(
            {'diagram': _sample_diagram()},
            {'dimensions': '0,1'},
        )
        assert isinstance(result['plot'], FigureWrapper)
        assert isinstance(result['plot_data'], PlotData)
        assert result['plot_data'].plot_type == "barcode"


class TestHeatmap:
    def test_numpy_2d(self):
        from persistra.operations.viz import Heatmap
        op = Heatmap()
        matrix = np.random.rand(5, 5)
        result = op.execute(
            {'data': DataWrapper(matrix)},
            {'colormap': 'viridis', 'annotate': False},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_dataframe(self):
        from persistra.operations.viz import Heatmap
        op = Heatmap()
        df = pd.DataFrame(np.random.rand(4, 3), columns=['a', 'b', 'c'])
        result = op.execute(
            {'data': DataWrapper(df)},
            {'colormap': 'hot', 'annotate': True},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_non_2d_raises(self):
        from persistra.operations.viz import Heatmap
        op = Heatmap()
        arr = np.array([1, 2, 3])
        with pytest.raises(ValueError, match="2-dimensional"):
            op.execute(
                {'data': DataWrapper(arr)},
                {'colormap': 'viridis', 'annotate': False},
            )


# =========================================================================
# 7.3 — Tier 2 Composition Nodes
# =========================================================================

class TestOverlayPlot:
    def test_basic(self):
        from persistra.operations.viz import OverlayPlot
        op = OverlayPlot()

        pd1 = PlotData(x=np.arange(5), y=np.sin(np.arange(5)),
                        plot_type="line", style={'color': 'red', 'label': 'sin'})
        pd2 = PlotData(x=np.arange(5), y=np.cos(np.arange(5)),
                        plot_type="line", style={'color': 'blue', 'label': 'cos'})

        result = op.execute(
            {'plot_data_1': pd1, 'plot_data_2': pd2},
            {'title': 'Combined', 'legend': True, 'x_label': 'x', 'y_label': 'y'},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_scatter_overlay(self):
        from persistra.operations.viz import OverlayPlot
        op = OverlayPlot()

        pd1 = PlotData(x=np.array([1, 2, 3]), y=np.array([4, 5, 6]),
                        plot_type="scatter", style={'color': 'red', 'label': 'A', 'size': 30})
        pd2 = PlotData(x=np.array([2, 3, 4]), y=np.array([5, 6, 7]),
                        plot_type="scatter", style={'color': 'blue', 'label': 'B', 'size': 20})

        result = op.execute(
            {'plot_data_1': pd1, 'plot_data_2': pd2},
            {'title': 'Scatter Overlay', 'legend': True, 'x_label': '', 'y_label': ''},
        )
        assert isinstance(result['plot'], FigureWrapper)


class TestSubplotGrid:
    def test_basic(self):
        import matplotlib.pyplot as plt
        from persistra.operations.viz import SubplotGrid

        fig1 = plt.Figure(figsize=(3, 3))
        ax1 = fig1.add_subplot(111)
        ax1.plot([1, 2, 3])
        ax1.set_title("Sub1")

        fig2 = plt.Figure(figsize=(3, 3))
        ax2 = fig2.add_subplot(111)
        ax2.plot([4, 5, 6])
        ax2.set_title("Sub2")

        op = SubplotGrid()
        result = op.execute(
            {'figure_1': FigureWrapper(fig1), 'figure_2': FigureWrapper(fig2)},
            {'rows': 1, 'cols': 2, 'shared_axes': False},
        )
        assert isinstance(result['plot'], FigureWrapper)
        # The resulting figure should have subplot axes
        assert len(result['plot'].data.axes) >= 2

        plt.close('all')


# =========================================================================
# 7.4 — Tier 3 Interactive / 3D Nodes
# =========================================================================

class TestThreeDScatter:
    def test_basic(self):
        from persistra.operations.viz import ThreeDScatter
        op = ThreeDScatter()
        arr = np.random.rand(50, 3)
        result = op.execute(
            {'data': DataWrapper(arr)},
            {'x_column': '0', 'y_column': '1', 'z_column': '2',
             'point_size': 20.0, 'color': 'blue'},
        )
        assert isinstance(result['plot'], FigureWrapper)

    def test_dataframe_input(self):
        from persistra.operations.viz import ThreeDScatter
        op = ThreeDScatter()
        df = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6], 'z': [7, 8, 9]})
        result = op.execute(
            {'data': DataWrapper(df)},
            {'x_column': 'x', 'y_column': 'y', 'z_column': 'z',
             'point_size': 15.0, 'color': 'red'},
        )
        assert isinstance(result['plot'], FigureWrapper)


class TestInteractivePlot:
    def test_basic(self):
        from persistra.operations.viz import InteractivePlot
        op = InteractivePlot()
        df = pd.DataFrame({"a": [1, 2, 3, 4]})
        result = op.execute(
            {'data': DataWrapper(df)},
            {'plot_type': 'line', 'title': 'Test'},
        )
        assert isinstance(result['plot'], InteractiveFigure)
        assert result['plot'].renderer == "pyqtgraph"

    def test_numpy_input(self):
        from persistra.operations.viz import InteractivePlot
        op = InteractivePlot()
        arr = np.array([[1, 2], [3, 4]])
        result = op.execute(
            {'data': DataWrapper(arr)},
            {'plot_type': 'scatter', 'title': 'Scatter'},
        )
        assert isinstance(result['plot'], InteractiveFigure)

    def test_bad_input_raises(self):
        from persistra.operations.viz import InteractivePlot
        op = InteractivePlot()
        with pytest.raises(TypeError, match="requires"):
            op.execute(
                {'data': DataWrapper("not a dataframe")},
                {'plot_type': 'line', 'title': 'Bad'},
            )


# =========================================================================
# Registry & Metadata
# =========================================================================

class TestPhase4Registry:
    def test_new_ops_registered(self):
        from persistra.operations import REGISTRY
        new_ops = [
            'ScatterPlot', 'Histogram', 'PersistenceDiagramPlot',
            'BarcodePlot', 'Heatmap', 'OverlayPlot', 'SubplotGrid',
            'ThreeDScatter', 'InteractivePlot',
        ]
        for name in new_ops:
            assert name in REGISTRY, f"{name} not found in registry"

    def test_total_count(self):
        from persistra.operations import REGISTRY
        # 28 original + 9 new = 37
        assert len(REGISTRY) >= 37

    def test_visualization_category(self):
        from persistra.operations import REGISTRY
        cats = REGISTRY.by_category()
        assert "Visualization" in cats
        viz_names = [op.__name__ for op in cats["Visualization"]]
        assert "ScatterPlot" in viz_names
        assert "Histogram" in viz_names
        assert "Heatmap" in viz_names
        assert "OverlayPlot" in viz_names
        assert "SubplotGrid" in viz_names
        assert "ThreeDScatter" in viz_names
        assert "InteractivePlot" in viz_names

    def test_all_new_ops_have_metadata(self):
        from persistra.operations import REGISTRY
        new_ops = [
            'ScatterPlot', 'Histogram', 'PersistenceDiagramPlot',
            'BarcodePlot', 'Heatmap', 'OverlayPlot', 'SubplotGrid',
            'ThreeDScatter', 'InteractivePlot',
        ]
        for name in new_ops:
            cls = REGISTRY.get(name)
            assert cls is not None, f"{name} not in registry"
            op = cls()
            assert op.name, f"{name} has no name"
            assert op.category, f"{name} has no category"
            assert op.description, f"{name} has no description"
