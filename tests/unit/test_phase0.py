"""
Tests for Phase 0 — Foundation & Migration changes.

These tests validate:
- PySide6 migration (imports work correctly)
- Registry restructure (operation names as keys)
- Bug fixes (ChoiceParam attribute, update_visualization method)
"""
import pytest


class TestPySide6Migration:
    """Verify all UI modules import PySide6 successfully."""

    def test_main_window_imports(self):
        """main_window.py should import PySide6, not PyQt6."""
        import persistra.ui.main_window as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_context_panel_imports(self):
        import persistra.ui.widgets.context_panel as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_node_browser_imports(self):
        import persistra.ui.widgets.node_browser as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_viz_panel_imports(self):
        import persistra.ui.widgets.viz_panel as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_graph_items_imports(self):
        import persistra.ui.graph.items as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_graph_manager_imports(self):
        import persistra.ui.graph.manager as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_graph_scene_imports(self):
        import persistra.ui.graph.scene as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_graph_worker_imports(self):
        import persistra.ui.graph.worker as mod
        source = open(mod.__file__).read()
        assert "PyQt6" not in source
        assert "PySide6" in source

    def test_main_no_qt_api_hack(self):
        """__main__.py should not set QT_API env var."""
        import persistra.__main__ as mod
        source = open(mod.__file__).read()
        assert "QT_API" not in source

    def test_signal_syntax(self):
        """Signals should use PySide6 'Signal', not 'pyqtSignal'."""
        import persistra.ui.graph.manager as mgr
        import persistra.ui.graph.scene as scn
        import persistra.ui.graph.worker as wrk
        for mod in (mgr, scn, wrk):
            source = open(mod.__file__).read()
            assert "pyqtSignal" not in source


class TestRegistryRestructure:
    """Verify the operations registry uses operation class names as keys."""

    def test_registry_keys_are_class_names(self):
        from persistra.operations import OPERATIONS_REGISTRY
        expected_keys = {"CSVLoader", "SlidingWindow", "RipsPersistence",
                         "LinePlot", "PersistencePlot"}
        assert set(OPERATIONS_REGISTRY.keys()) == expected_keys

    def test_registry_values_are_callable(self):
        from persistra.operations import OPERATIONS_REGISTRY
        for name, cls in OPERATIONS_REGISTRY.items():
            assert callable(cls), f"Registry entry '{name}' is not callable"

    def test_registry_lookup_by_class_name(self):
        from persistra.operations import OPERATIONS_REGISTRY
        csv_cls = OPERATIONS_REGISTRY.get("CSVLoader")
        assert csv_cls is not None
        instance = csv_cls()
        assert instance.name == "CSV Loader"


class TestBugFixes:
    """Verify the three bug fixes from section 3.4."""

    def test_choice_param_uses_options_attribute(self):
        """ContextPanel should read 'options' from ChoiceParam, not 'choices'."""
        import persistra.ui.widgets.context_panel as mod
        source = open(mod.__file__).read()
        # The factory method should reference 'options', not 'choices'
        assert "getattr(param, 'options'" in source
        assert "getattr(param, 'choices'" not in source

    def test_choice_param_options_roundtrip(self):
        """ChoiceParam stores 'options' and it should be accessible."""
        from persistra.core.objects import ChoiceParam
        cp = ChoiceParam("test", "Test", options=["a", "b", "c"], default="a")
        assert cp.options == ["a", "b", "c"]
        assert not hasattr(cp, "choices") or getattr(cp, "choices", None) is None

    def test_viz_panel_has_update_visualization(self):
        """VizPanel must have an update_visualization method."""
        import persistra.ui.widgets.viz_panel as mod
        source = open(mod.__file__).read()
        assert "def update_visualization" in source
