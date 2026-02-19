"""
Tests for Phase 3 — Operations Library Expansion.

Covers:
- 6.1 OperationRegistry (register, get, all, by_category, search, dict-compat)
- 6.2 Plugin loader (load_plugins, error handling)
- 6.3.1 I/O operations (ManualDataEntry, DataGenerator, CSVWriter)
- 6.3.2 Preprocessing operations (Normalize, Differencing, Returns, LogTransform,
        LogReturns, RollingStatistics)
- 6.3.3 TDA operations (AlphaPersistence, CechPersistence, CubicalPersistence,
        PersistenceLandscape, PersistenceImage, DiagramDistance)
- 6.3.4 ML operations (KMeansClustering, PCA, LinearRegressionOp,
        LogisticRegressionOp)
- 6.3.5 Visualization operations deferred to Phase 4
- 6.3.6 Utility operations (ColumnSelector, MergeJoin)
- 6.3.7 Export (ExportFigure)
- 6.3.8 PythonExpression
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from persistra.core.objects import DataWrapper, PersistenceDiagram, TimeSeries
from persistra.core.project import Operation


# =========================================================================
# 6.1 — OperationRegistry
# =========================================================================

class TestOperationRegistry:
    """Verify the new OperationRegistry class and backward compat."""

    def test_registry_is_singleton(self):
        from persistra.operations import REGISTRY, OPERATIONS_REGISTRY
        assert REGISTRY is OPERATIONS_REGISTRY

    def test_register_and_get(self):
        from persistra.operations import OperationRegistry

        reg = OperationRegistry()

        class _DummyOp(Operation):
            name = "Dummy"
            category = "Test"

        reg.register(_DummyOp)
        assert reg.get("_DummyOp") is _DummyOp

    def test_duplicate_raises(self):
        from persistra.operations import OperationRegistry

        reg = OperationRegistry()

        class _DupOp(Operation):
            name = "Dup"

        reg.register(_DupOp)
        with pytest.raises(ValueError, match="Duplicate"):
            reg.register(_DupOp)

    def test_all_returns_copy(self):
        from persistra.operations import REGISTRY
        all_ops = REGISTRY.all()
        assert isinstance(all_ops, dict)
        # 28 = total built-in operations across all categories
        assert len(all_ops) >= 28

    def test_by_category_groups(self):
        from persistra.operations import REGISTRY
        cats = REGISTRY.by_category()
        assert "Input / Output" in cats
        assert "Preprocessing" in cats
        assert "TDA" in cats
        assert "Machine Learning" in cats

    def test_search_finds_csv(self):
        from persistra.operations import REGISTRY
        results = REGISTRY.search("csv")
        names = [r.__name__ for r in results]
        assert "CSVLoader" in names
        assert "CSVWriter" in names

    def test_search_case_insensitive(self):
        from persistra.operations import REGISTRY
        results = REGISTRY.search("NORMALIZE")
        assert any(r.__name__ == "Normalize" for r in results)

    def test_dict_compat_keys(self):
        from persistra.operations import OPERATIONS_REGISTRY
        assert "CSVLoader" in OPERATIONS_REGISTRY
        assert len(list(OPERATIONS_REGISTRY.keys())) >= 28

    def test_dict_compat_getitem(self):
        from persistra.operations import OPERATIONS_REGISTRY
        cls = OPERATIONS_REGISTRY["CSVLoader"]
        assert issubclass(cls, Operation)

    def test_dict_compat_get(self):
        from persistra.operations import OPERATIONS_REGISTRY
        assert OPERATIONS_REGISTRY.get("Nonexistent") is None

    def test_dict_compat_setitem_pop(self):
        from persistra.operations import OPERATIONS_REGISTRY

        class _TmpOp(Operation):
            name = "Tmp"

        OPERATIONS_REGISTRY["_TmpOp"] = _TmpOp
        assert OPERATIONS_REGISTRY.get("_TmpOp") is _TmpOp
        OPERATIONS_REGISTRY.pop("_TmpOp", None)
        assert OPERATIONS_REGISTRY.get("_TmpOp") is None

    def test_dict_compat_iter(self):
        from persistra.operations import OPERATIONS_REGISTRY
        keys = list(OPERATIONS_REGISTRY)
        assert "CSVLoader" in keys

    def test_dict_compat_len(self):
        from persistra.operations import OPERATIONS_REGISTRY
        assert len(OPERATIONS_REGISTRY) >= 28


# =========================================================================
# 6.2 — Plugin System
# =========================================================================

class TestPluginLoader:
    """Verify plugin loading from ~/.persistra/plugins/."""

    def test_load_plugins_creates_dir(self, tmp_path, monkeypatch):
        from persistra.plugins import loader

        fake_dir = tmp_path / "plugins"
        monkeypatch.setattr(loader, "PLUGIN_DIR", fake_dir)
        loader.load_plugins()
        assert fake_dir.exists()

    def test_load_valid_plugin(self, tmp_path, monkeypatch):
        from persistra.plugins import loader

        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        monkeypatch.setattr(loader, "PLUGIN_DIR", plugin_dir)

        plugin_file = plugin_dir / "test_plugin.py"
        plugin_file.write_text("LOADED = True\n")

        loader.load_plugins()  # Should not raise

    def test_load_bad_plugin_logs_error(self, tmp_path, monkeypatch, caplog):
        import logging
        from persistra.plugins import loader

        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        monkeypatch.setattr(loader, "PLUGIN_DIR", plugin_dir)

        plugin_file = plugin_dir / "bad_plugin.py"
        plugin_file.write_text("raise RuntimeError('boom')\n")

        with caplog.at_level(logging.ERROR, logger="persistra.plugins.loader"):
            loader.load_plugins()

        assert any("Failed to load plugin" in r.message for r in caplog.records)


# =========================================================================
# 6.3.1 — I/O Operations
# =========================================================================

class TestManualDataEntry:
    def test_default_table(self):
        from persistra.operations.io import ManualDataEntry
        op = ManualDataEntry()
        result = op.execute({}, {p.name: p.value for p in op.parameters})
        ts = result['data']
        assert isinstance(ts, TimeSeries)
        assert ts.data.shape == (3, 2)

    def test_custom_json(self):
        from persistra.operations.io import ManualDataEntry
        op = ManualDataEntry()
        custom = json.dumps({"columns": ["x"], "data": [[1], [2], [3], [4]]})
        result = op.execute({}, {'table_json': custom})
        assert result['data'].data.shape == (4, 1)


class TestDataGenerator:
    def test_sine(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'sine'
        params['length'] = 100
        result = op.execute({}, params)
        assert result['data'].data.shape[0] == 100

    def test_cosine(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'cosine'
        params['length'] = 50
        result = op.execute({}, params)
        assert result['data'].data.shape[0] == 50

    def test_white_noise(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'white_noise'
        result = op.execute({}, params)
        assert isinstance(result['data'], TimeSeries)

    def test_random_walk(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'random_walk'
        result = op.execute({}, params)
        assert isinstance(result['data'], TimeSeries)

    def test_brownian(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'brownian'
        result = op.execute({}, params)
        assert isinstance(result['data'], TimeSeries)

    def test_distribution(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'distribution'
        result = op.execute({}, params)
        assert isinstance(result['data'], TimeSeries)

    def test_sphere(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'sphere'
        params['dimensions'] = 4
        params['length'] = 200
        result = op.execute({}, params)
        df = result['data'].data
        assert df.shape == (200, 4)
        # Verify points are on unit sphere
        norms = np.linalg.norm(df.values, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-10)

    def test_deterministic_seed(self):
        from persistra.operations.io import DataGenerator
        op = DataGenerator()
        params = {p.name: p.value for p in op.parameters}
        params['signal_type'] = 'white_noise'
        r1 = op.execute({}, params)
        r2 = op.execute({}, params)
        pd.testing.assert_frame_equal(r1['data'].data, r2['data'].data)


class TestCSVWriter:
    def test_write_csv(self, tmp_path):
        from persistra.operations.io import CSVWriter
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        op = CSVWriter()
        outpath = str(tmp_path / "out.csv")
        op.execute(
            {'data': TimeSeries(df)},
            {'filepath': outpath, 'include_index': False},
        )
        assert os.path.exists(outpath)
        loaded = pd.read_csv(outpath)
        pd.testing.assert_frame_equal(loaded, df)


# =========================================================================
# 6.3.2 — Preprocessing Operations
# =========================================================================

def _sample_ts():
    """Create a simple TimeSeries for preprocessing tests."""
    return TimeSeries(pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}))


def _positive_ts():
    return TimeSeries(pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}))


class TestNormalize:
    def test_min_max(self):
        from persistra.operations.preprocessing import Normalize
        op = Normalize()
        result = op.execute({'data': _sample_ts()}, {'method': 'min-max'})
        df = result['data'].data
        assert df['a'].min() == pytest.approx(0.0)
        assert df['a'].max() == pytest.approx(1.0)

    def test_z_score(self):
        from persistra.operations.preprocessing import Normalize
        op = Normalize()
        result = op.execute({'data': _sample_ts()}, {'method': 'z-score'})
        df = result['data'].data
        assert df['a'].mean() == pytest.approx(0.0, abs=1e-10)


class TestDifferencing:
    def test_first_order(self):
        from persistra.operations.preprocessing import Differencing
        op = Differencing()
        result = op.execute({'data': _sample_ts()}, {'order': 1})
        df = result['data'].data
        assert len(df) == 4
        np.testing.assert_allclose(df['a'].values, [1.0, 1.0, 1.0, 1.0])

    def test_second_order(self):
        from persistra.operations.preprocessing import Differencing
        op = Differencing()
        result = op.execute({'data': _sample_ts()}, {'order': 2})
        df = result['data'].data
        assert len(df) == 3


class TestReturns:
    def test_simple_returns(self):
        from persistra.operations.preprocessing import Returns
        op = Returns()
        result = op.execute({'data': _positive_ts()}, {})
        df = result['data'].data
        assert len(df) == 4
        assert df['a'].iloc[0] == pytest.approx(1.0)  # (2-1)/1 = 1.0


class TestLogTransform:
    def test_natural_log(self):
        from persistra.operations.preprocessing import LogTransform
        op = LogTransform()
        result = op.execute({'data': _positive_ts()}, {'base': 'natural'})
        df = result['data'].data
        np.testing.assert_allclose(df['a'].values, np.log([1, 2, 3, 4, 5]))

    def test_base10_log(self):
        from persistra.operations.preprocessing import LogTransform
        op = LogTransform()
        result = op.execute({'data': _positive_ts()}, {'base': 'base10'})
        df = result['data'].data
        np.testing.assert_allclose(df['a'].values, np.log10([1, 2, 3, 4, 5]))

    def test_non_positive_raises(self):
        from persistra.operations.preprocessing import LogTransform
        op = LogTransform()
        bad = TimeSeries(pd.DataFrame({"a": [-1.0, 0.0, 1.0]}))
        with pytest.raises(ValueError, match="positive"):
            op.execute({'data': bad}, {'base': 'natural'})


class TestLogReturns:
    def test_log_returns(self):
        from persistra.operations.preprocessing import LogReturns
        op = LogReturns()
        result = op.execute({'data': _positive_ts()}, {})
        df = result['data'].data
        assert len(df) == 4
        expected_first = np.log(2.0 / 1.0)
        assert df['a'].iloc[0] == pytest.approx(expected_first)


class TestRollingStatistics:
    def test_rolling_mean(self):
        from persistra.operations.preprocessing import RollingStatistics
        op = RollingStatistics()
        ts = TimeSeries(pd.DataFrame({"a": list(range(20))}))
        result = op.execute({'data': ts}, {'window': 5, 'statistic': 'mean'})
        df = result['data'].data
        assert len(df) == 16  # 20 - 5 + 1

    def test_rolling_sum(self):
        from persistra.operations.preprocessing import RollingStatistics
        op = RollingStatistics()
        ts = TimeSeries(pd.DataFrame({"a": [1.0] * 10}))
        result = op.execute({'data': ts}, {'window': 3, 'statistic': 'sum'})
        df = result['data'].data
        np.testing.assert_allclose(df['a'].values, [3.0] * len(df))


# =========================================================================
# 6.3.3 — TDA Operations (unit tests using synthetic data)
# =========================================================================

class TestPersistenceLandscape:
    def test_landscape_shape(self):
        from persistra.operations.tda import PersistenceLandscape
        dgm = PersistenceDiagram([
            np.array([[0, 1], [0, 2]]),       # H0
            np.array([[0.5, 1.5], [0.3, 2]]), # H1
        ])
        op = PersistenceLandscape()
        result = op.execute(
            {'diagram': dgm},
            {'num_landscapes': 3, 'resolution': 50, 'homology_dim': 1},
        )
        data = result['landscape'].data
        assert data.shape == (3, 50)

    def test_empty_diagram(self):
        from persistra.operations.tda import PersistenceLandscape
        dgm = PersistenceDiagram([np.empty((0, 2))])
        op = PersistenceLandscape()
        result = op.execute(
            {'diagram': dgm},
            {'num_landscapes': 5, 'resolution': 100, 'homology_dim': 0},
        )
        assert np.all(result['landscape'].data == 0)


class TestPersistenceImage:
    def test_image_shape(self):
        from persistra.operations.tda import PersistenceImage
        dgm = PersistenceDiagram([
            np.array([[0, 1], [0, 2]]),       # H0
            np.array([[0.5, 1.5], [0.3, 2]]), # H1
        ])
        op = PersistenceImage()
        result = op.execute(
            {'diagram': dgm},
            {'resolution': 15, 'sigma': 0.1, 'homology_dim': 1},
        )
        assert result['image'].data.shape == (15, 15)

    def test_empty_diagram(self):
        from persistra.operations.tda import PersistenceImage
        dgm = PersistenceDiagram([np.empty((0, 2))])
        op = PersistenceImage()
        result = op.execute(
            {'diagram': dgm},
            {'resolution': 10, 'sigma': 0.1, 'homology_dim': 0},
        )
        assert np.all(result['image'].data == 0)


class TestDiagramDistance:
    def test_requires_persim(self):
        """DiagramDistance should raise if persim is not available."""
        from persistra.operations import tda as tda_mod
        from persistra.operations.tda import DiagramDistance

        original = tda_mod._persim_mod
        try:
            tda_mod._persim_mod = None
            op = DiagramDistance()
            dgm = PersistenceDiagram([np.array([[0, 1]])])
            with pytest.raises(ImportError, match="persim"):
                op.execute(
                    {'diagram_a': dgm, 'diagram_b': dgm},
                    {'metric': 'wasserstein', 'homology_dim': 0, 'order': 2.0},
                )
        finally:
            tda_mod._persim_mod = original


# =========================================================================
# 6.3.4 — ML Operations (require scikit-learn)
# =========================================================================

@pytest.fixture()
def _ensure_sklearn():
    pytest.importorskip("sklearn")


class TestKMeansClustering:
    def test_basic(self, _ensure_sklearn):
        from persistra.operations.ml import KMeansClustering
        data = DataWrapper(np.random.default_rng(0).normal(size=(100, 3)))
        op = KMeansClustering()
        result = op.execute(
            {'data': data},
            {'n_clusters': 3, 'max_iter': 100, 'random_state': 42},
        )
        assert result['labels'].data.shape == (100,)
        assert result['centroids'].data.shape == (3, 3)


class TestPCA:
    def test_basic(self, _ensure_sklearn):
        from persistra.operations.ml import PCA
        data = DataWrapper(np.random.default_rng(0).normal(size=(50, 5)))
        op = PCA()
        result = op.execute({'data': data}, {'n_components': 2})
        assert result['transformed'].data.shape == (50, 2)
        assert result['components'].data.shape == (2, 5)


class TestLinearRegressionOp:
    def test_basic(self, _ensure_sklearn):
        from persistra.operations.ml import LinearRegressionOp
        rng = np.random.default_rng(0)
        X = rng.normal(size=(100, 2))
        y = X[:, 0] * 3 + X[:, 1] * -1 + rng.normal(size=100) * 0.01
        op = LinearRegressionOp()
        result = op.execute(
            {'X': DataWrapper(X), 'y': DataWrapper(y)}, {}
        )
        assert result['predictions'].data.shape == (100,)
        assert float(result['r_squared'].data) > 0.99


class TestLogisticRegressionOp:
    def test_basic(self, _ensure_sklearn):
        from persistra.operations.ml import LogisticRegressionOp
        rng = np.random.default_rng(0)
        X = rng.normal(size=(100, 2))
        y = (X[:, 0] > 0).astype(int)
        op = LogisticRegressionOp()
        result = op.execute(
            {'X': DataWrapper(X), 'y': DataWrapper(y)},
            {'C': 1.0, 'max_iter': 200},
        )
        assert result['predictions'].data.shape == (100,)
        assert result['probabilities'].data.shape == (100, 2)
        assert 0 <= float(result['accuracy'].data) <= 1


# =========================================================================
# 6.3.6 — Utility Operations
# =========================================================================

class TestColumnSelector:
    def test_by_index(self):
        from persistra.operations.utility import ColumnSelector
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        op = ColumnSelector()
        result = op.execute({'data': TimeSeries(df)}, {'columns': '0, 2'})
        assert list(result['data'].data.columns) == ["a", "c"]

    def test_by_name(self):
        from persistra.operations.utility import ColumnSelector
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        op = ColumnSelector()
        result = op.execute({'data': TimeSeries(df)}, {'columns': 'a, c'})
        assert list(result['data'].data.columns) == ["a", "c"]


class TestMergeJoin:
    def test_inner_join(self):
        from persistra.operations.utility import MergeJoin
        left = pd.DataFrame({"key": [1, 2, 3], "val": ["a", "b", "c"]})
        right = pd.DataFrame({"key": [2, 3, 4], "val2": ["x", "y", "z"]})
        op = MergeJoin()
        result = op.execute(
            {'left': TimeSeries(left), 'right': TimeSeries(right)},
            {'how': 'inner', 'on': 'key', 'left_index': False, 'right_index': False},
        )
        assert len(result['data'].data) == 2

    def test_outer_join(self):
        from persistra.operations.utility import MergeJoin
        left = pd.DataFrame({"key": [1, 2], "v": [10, 20]})
        right = pd.DataFrame({"key": [2, 3], "w": [30, 40]})
        op = MergeJoin()
        result = op.execute(
            {'left': TimeSeries(left), 'right': TimeSeries(right)},
            {'how': 'outer', 'on': 'key', 'left_index': False, 'right_index': False},
        )
        assert len(result['data'].data) == 3


# =========================================================================
# 6.3.7 — Export Figure
# =========================================================================

class TestExportFigure:
    def test_export_png(self, tmp_path):
        import matplotlib.pyplot as plt
        from persistra.operations.utility import ExportFigure

        fig = plt.Figure(figsize=(3, 3))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3])

        op = ExportFigure()
        outpath = str(tmp_path / "fig.png")
        op.execute(
            {'figure': DataWrapper(fig)},
            {'filepath': outpath, 'format': 'png', 'dpi': 72},
        )
        assert os.path.exists(outpath)
        assert os.path.getsize(outpath) > 0
        plt.close(fig)


# =========================================================================
# 6.3.8 — Python Expression
# =========================================================================

class TestPythonExpression:
    def test_passthrough(self):
        from persistra.operations.utility import PythonExpression
        op = PythonExpression()
        inp_data = DataWrapper(42)
        result = op.execute(
            {'data': inp_data},
            {'code': "result = inputs.get('data')"},
        )
        assert result['result'] is inp_data

    def test_computation(self):
        from persistra.operations.utility import PythonExpression
        op = PythonExpression()
        result = op.execute(
            {},
            {'code': "result = np.arange(5).sum()"},
        )
        assert result['result'] == 10

    def test_pandas_access(self):
        from persistra.operations.utility import PythonExpression
        op = PythonExpression()
        result = op.execute(
            {},
            {'code': "result = pd.DataFrame({'x': [1,2,3]}).shape[0]"},
        )
        assert result['result'] == 3


# =========================================================================
# Cross-cutting: Category and metadata
# =========================================================================

class TestOperationMetadata:
    """Verify all registered operations have required metadata."""

    def test_all_ops_have_name(self):
        from persistra.operations import REGISTRY
        for key, cls in REGISTRY.items():
            op = cls()
            assert op.name, f"{key} has no name"

    def test_all_ops_have_category(self):
        from persistra.operations import REGISTRY
        for key, cls in REGISTRY.items():
            op = cls()
            assert op.category, f"{key} has no category"

    def test_all_ops_have_description(self):
        from persistra.operations import REGISTRY
        for key, cls in REGISTRY.items():
            op = cls()
            assert op.description, f"{key} has no description"

    def test_total_operation_count(self):
        from persistra.operations import REGISTRY
        assert len(REGISTRY) >= 28
