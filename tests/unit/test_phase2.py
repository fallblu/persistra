"""
Tests for Phase 2 — Project Persistence.

Covers:
- 5.1 Archive format (.persistra ZIP with manifest.json, graph.json, cache/)
- 5.1.1 graph.json schema (nodes, connections, settings)
- 5.1.2 Cache serialization (npz, parquet, pkl fallback)
- 5.2 Save/Load round-trip via ProjectSerializer
- 5.3 Autosave service (path helpers, timer logic)
- 5.4 Figure export helper
- 5.5 Recent projects (add, load, pruning, max 10)
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from persistra.core.objects import DataWrapper, IntParam, TimeSeries
from persistra.core.project import Node, NodeState, Operation, Project


# =========================================================================
# Helper operations (pure-logic, no GUI)
# =========================================================================

class _SourceOp(Operation):
    name = "TestSource"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.outputs = [{"name": "out", "type": DataWrapper}]
        self.parameters = [IntParam("value", "Value", default=42, min_val=0, max_val=9999)]

    def execute(self, inputs, params, cancel_event=None):
        return {"out": DataWrapper(params["value"])}


class _PassOp(Operation):
    name = "TestPass"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.inputs = [{"name": "x", "type": DataWrapper}]
        self.outputs = [{"name": "x", "type": DataWrapper}]

    def execute(self, inputs, params, cancel_event=None):
        return {"x": inputs["x"]}


class _NumpySourceOp(Operation):
    name = "NumpySource"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.outputs = [{"name": "arr", "type": DataWrapper}]

    def execute(self, inputs, params, cancel_event=None):
        return {"arr": DataWrapper(np.arange(12).reshape(3, 4))}


class _DataFrameSourceOp(Operation):
    name = "DFSource"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.outputs = [{"name": "df", "type": DataWrapper}]

    def execute(self, inputs, params, cancel_event=None):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        return {"df": TimeSeries(df)}


# Dynamically register test ops so the serializer can resolve them
import persistra.operations as _ops_pkg

_TEST_OPS = {
    "_SourceOp": _SourceOp,
    "_PassOp": _PassOp,
    "_NumpySourceOp": _NumpySourceOp,
    "_DataFrameSourceOp": _DataFrameSourceOp,
}


@pytest.fixture(autouse=True)
def _register_test_ops():
    """Temporarily register test operations for serialization round-trips."""
    for name, cls in _TEST_OPS.items():
        _ops_pkg.OPERATIONS_REGISTRY[name] = cls
    yield
    for name in _TEST_OPS:
        _ops_pkg.OPERATIONS_REGISTRY.pop(name, None)


# =========================================================================
# 5.1 + 5.2 — Archive format & Save/Load round-trip
# =========================================================================

class TestProjectSerializer:
    """ProjectSerializer saves and loads .persistra archives."""

    def test_save_creates_zip(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.add_node(_SourceOp, position=(10, 20))
        fp = tmp_path / "test.persistra"
        ProjectSerializer().save(proj, fp)
        assert fp.exists()
        assert zipfile.is_zipfile(fp)

    def test_archive_contains_manifest_and_graph(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.add_node(_SourceOp)
        fp = tmp_path / "test.persistra"
        ProjectSerializer().save(proj, fp)

        with zipfile.ZipFile(fp, "r") as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "graph.json" in names

    def test_manifest_fields(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        fp = tmp_path / "test.persistra"
        ProjectSerializer().save(proj, fp)

        with zipfile.ZipFile(fp, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format_version"] == "1.0"
        assert "persistra_version" in manifest
        assert "created_at" in manifest

    def test_graph_json_schema(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.add_node(_SourceOp, position=(100, 200))
        proj.auto_compute = True
        fp = tmp_path / "test.persistra"
        ProjectSerializer().save(proj, fp)

        with zipfile.ZipFile(fp, "r") as zf:
            graph = json.loads(zf.read("graph.json"))

        assert graph["version"] == "1.0"
        assert len(graph["nodes"]) == 1
        node = graph["nodes"][0]
        assert "id" in node
        assert "operation" in node
        assert node["position"] == [100, 200]
        assert "parameters" in node
        assert "state" in node
        assert isinstance(graph["connections"], list)
        assert graph["settings"]["auto_compute"] is True

    def test_roundtrip_empty_project(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        fp = tmp_path / "empty.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert isinstance(loaded, Project)
        assert len(loaded.nodes) == 0

    def test_roundtrip_single_node(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.add_node(_SourceOp, position=(50, 60))
        fp = tmp_path / "single.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert len(loaded.nodes) == 1
        node = loaded.nodes[0]
        assert node.position == (50, 60)
        assert node.operation.name == "TestSource"

    def test_roundtrip_preserves_parameters(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_SourceOp)
        node.set_parameter("value", 99)
        fp = tmp_path / "params.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert loaded.nodes[0].parameters[0].value == 99

    def test_roundtrip_preserves_connections(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        src = proj.add_node(_SourceOp)
        sink = proj.add_node(_PassOp)
        proj.connect(src, "out", sink, "x")
        fp = tmp_path / "conn.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert len(loaded.nodes) == 2
        # The sink's input socket should have a connection
        sink_node = next(n for n in loaded.nodes if n.operation.name == "TestPass")
        inp = sink_node.get_input_socket("x")
        assert len(inp.connections) == 1

    def test_roundtrip_preserves_node_ids(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        n = proj.add_node(_SourceOp)
        original_id = n.id
        fp = tmp_path / "ids.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert loaded.nodes[0].id == original_id

    def test_roundtrip_preserves_settings(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.auto_compute = True
        proj.autosave_interval_minutes = 3
        fp = tmp_path / "settings.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)
        assert loaded.auto_compute is True
        assert loaded.autosave_interval_minutes == 3


# =========================================================================
# 5.1.2 — Cache serialization
# =========================================================================

class TestCacheSerialization:
    """Cached outputs are stored per-node inside cache/ in the archive."""

    def test_cache_saved_for_computed_nodes(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_SourceOp)
        node.compute()
        assert node.state == NodeState.VALID

        fp = tmp_path / "cache.persistra"
        ProjectSerializer().save(proj, fp)

        with zipfile.ZipFile(fp, "r") as zf:
            cache_files = [n for n in zf.namelist() if n.startswith("cache/")]
            assert len(cache_files) == 1
            assert cache_files[0] == f"cache/{node.id}.bin"

    def test_cache_not_saved_for_dirty_nodes(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        proj.add_node(_SourceOp)  # Not computed → no cache

        fp = tmp_path / "nocache.persistra"
        ProjectSerializer().save(proj, fp)

        with zipfile.ZipFile(fp, "r") as zf:
            cache_files = [n for n in zf.namelist() if n.startswith("cache/")]
            assert len(cache_files) == 0

    def test_cache_restores_valid_state(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_SourceOp)
        node.compute()

        fp = tmp_path / "cache_restore.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)

        restored_node = loaded.nodes[0]
        assert restored_node._is_dirty is False
        assert restored_node.state == NodeState.VALID
        assert "out" in restored_node._cached_outputs

    def test_numpy_cache_roundtrip(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_NumpySourceOp)
        node.compute()

        fp = tmp_path / "np_cache.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)

        restored = loaded.nodes[0]._cached_outputs["arr"]
        expected = np.arange(12).reshape(3, 4)
        np.testing.assert_array_equal(
            restored.data if isinstance(restored, DataWrapper) else restored,
            expected,
        )

    def test_dataframe_cache_roundtrip(self, tmp_path):
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_DataFrameSourceOp)
        node.compute()

        fp = tmp_path / "df_cache.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)
        loaded = ser.load(fp)

        restored = loaded.nodes[0]._cached_outputs["df"]
        raw = restored.data if isinstance(restored, DataWrapper) else restored
        pd.testing.assert_frame_equal(
            raw, pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        )

    def test_missing_cache_marks_dirty(self, tmp_path):
        """If cache file is absent, node should be dirty and recompute."""
        from persistra.core.io import ProjectSerializer

        proj = Project()
        node = proj.add_node(_SourceOp)
        node.compute()

        fp = tmp_path / "mc.persistra"
        ser = ProjectSerializer()
        ser.save(proj, fp)

        # Remove cache entry from the archive
        clean_fp = tmp_path / "mc_clean.persistra"
        with zipfile.ZipFile(fp, "r") as zf_in, zipfile.ZipFile(
            clean_fp, "w"
        ) as zf_out:
            for item in zf_in.namelist():
                if not item.startswith("cache/"):
                    zf_out.writestr(item, zf_in.read(item))

        loaded = ser.load(clean_fp)
        assert loaded.nodes[0]._is_dirty is True


# =========================================================================
# 5.3 — Autosave Service
# =========================================================================

class TestAutosaveService:
    """AutosaveService helpers (no real timer firing in unit tests)."""

    def test_autosave_path_for(self):
        from persistra.core.autosave import AutosaveService

        p = Path("/home/user/project.persistra")
        auto = AutosaveService.autosave_path_for(p)
        assert auto == Path("/home/user/project.persistra.autosave")

    def test_has_autosave_no_file(self, tmp_path):
        from persistra.core.autosave import AutosaveService

        assert AutosaveService.has_autosave(tmp_path / "nope.persistra") is False

    def test_has_autosave_newer(self, tmp_path):
        from persistra.core.autosave import AutosaveService

        proj_path = tmp_path / "proj.persistra"
        auto_path = AutosaveService.autosave_path_for(proj_path)
        proj_path.write_text("old")
        import time; time.sleep(0.05)
        auto_path.write_text("new")
        assert AutosaveService.has_autosave(proj_path) is True

    def test_remove_autosave(self, tmp_path):
        from persistra.core.autosave import AutosaveService

        proj_path = tmp_path / "proj.persistra"
        auto_path = AutosaveService.autosave_path_for(proj_path)
        auto_path.write_text("temp")
        assert auto_path.exists()
        AutosaveService.remove_autosave(proj_path)
        assert not auto_path.exists()

    def test_start_noop_without_path(self):
        """Autosave should not start if no project path is set."""
        from PySide6.QtWidgets import QApplication

        # Ensure a QApplication exists for QTimer
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        from persistra.core.autosave import AutosaveService

        svc = AutosaveService()
        svc.set_project(Project())
        svc.start()
        assert svc.is_active is False
        svc.stop()

    def test_set_interval(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        from persistra.core.autosave import AutosaveService

        svc = AutosaveService()
        svc.set_interval_minutes(10)
        assert svc._interval_ms == 10 * 60 * 1000


# =========================================================================
# 5.4 — Figure Export
# =========================================================================

class TestFigureExport:
    """export_figure() helper function."""

    def test_export_matplotlib_png(self, tmp_path):
        import matplotlib.pyplot as plt
        from persistra.ui.dialogs.export_figure import export_figure

        fig = plt.Figure(figsize=(3, 2))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3])

        out = tmp_path / "fig.png"
        export_figure(fig, out, fmt="png", dpi=100)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_export_matplotlib_svg(self, tmp_path):
        import matplotlib.pyplot as plt
        from persistra.ui.dialogs.export_figure import export_figure

        fig = plt.Figure(figsize=(3, 2))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3])

        out = tmp_path / "fig.svg"
        export_figure(fig, out, fmt="svg")
        assert out.exists()
        content = out.read_text()
        assert "<svg" in content

    def test_export_matplotlib_pdf(self, tmp_path):
        import matplotlib.pyplot as plt
        from persistra.ui.dialogs.export_figure import export_figure

        fig = plt.Figure(figsize=(3, 2))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3])

        out = tmp_path / "fig.pdf"
        export_figure(fig, out, fmt="pdf")
        assert out.exists()
        assert out.stat().st_size > 0

    def test_export_raises_without_figure_or_widget(self, tmp_path):
        from persistra.ui.dialogs.export_figure import export_figure

        with pytest.raises(ValueError, match="figure or a QWidget"):
            export_figure(None, tmp_path / "bad.png")


# =========================================================================
# 5.5 — Recent Projects
# =========================================================================

class TestRecentProjects:
    """Recent project file management."""

    def test_load_empty(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        monkeypatch.setattr(recent_mod, "_RECENT_FILE", tmp_path / "recent.json")
        assert recent_mod.load_recent_projects() == []

    def test_add_and_load(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        rf = tmp_path / "recent.json"
        monkeypatch.setattr(recent_mod, "_RECENT_FILE", rf)
        monkeypatch.setattr(recent_mod, "_CONFIG_DIR", tmp_path)

        # Create a fake project file
        fake_proj = tmp_path / "project.persistra"
        fake_proj.write_text("")

        recent_mod.add_recent_project(str(fake_proj))
        result = recent_mod.load_recent_projects()
        assert len(result) == 1
        assert result[0] == str(fake_proj.resolve())

    def test_most_recent_first(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        rf = tmp_path / "recent.json"
        monkeypatch.setattr(recent_mod, "_RECENT_FILE", rf)
        monkeypatch.setattr(recent_mod, "_CONFIG_DIR", tmp_path)

        f1 = tmp_path / "a.persistra"
        f2 = tmp_path / "b.persistra"
        f1.write_text("")
        f2.write_text("")

        recent_mod.add_recent_project(str(f1))
        recent_mod.add_recent_project(str(f2))
        result = recent_mod.load_recent_projects()
        assert result[0] == str(f2.resolve())

    def test_max_10_entries(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        rf = tmp_path / "recent.json"
        monkeypatch.setattr(recent_mod, "_RECENT_FILE", rf)
        monkeypatch.setattr(recent_mod, "_CONFIG_DIR", tmp_path)

        for i in range(15):
            f = tmp_path / f"proj{i}.persistra"
            f.write_text("")
            recent_mod.add_recent_project(str(f))

        result = recent_mod.load_recent_projects()
        assert len(result) == 10

    def test_prune_missing_files(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        rf = tmp_path / "recent.json"
        monkeypatch.setattr(recent_mod, "_RECENT_FILE", rf)
        monkeypatch.setattr(recent_mod, "_CONFIG_DIR", tmp_path)

        # Write a JSON with a path that doesn't exist
        rf.write_text(json.dumps(["/nonexistent/file.persistra"]))
        result = recent_mod.load_recent_projects()
        assert result == []

    def test_deduplication(self, monkeypatch, tmp_path):
        import persistra.core.recent as recent_mod

        rf = tmp_path / "recent.json"
        monkeypatch.setattr(recent_mod, "_RECENT_FILE", rf)
        monkeypatch.setattr(recent_mod, "_CONFIG_DIR", tmp_path)

        f = tmp_path / "dupe.persistra"
        f.write_text("")

        recent_mod.add_recent_project(str(f))
        recent_mod.add_recent_project(str(f))
        result = recent_mod.load_recent_projects()
        assert len(result) == 1


# =========================================================================
# Legacy helpers
# =========================================================================

class TestLegacyHelpers:
    """save_project / load_project convenience wrappers."""

    def test_save_load_roundtrip(self, tmp_path):
        from persistra.core.io import load_project, save_project

        proj = Project()
        proj.add_node(_SourceOp, position=(5, 10))

        fp = tmp_path / "legacy.persistra"
        save_project(proj, str(fp))
        loaded = load_project(str(fp))
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0].operation.name == "TestSource"
