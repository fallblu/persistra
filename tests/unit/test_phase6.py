"""
Tests for Phase 6 — Error Handling, Logging & Validation.

Covers:
- 9.1  Structured Logging (setup_logging, rotating file handler)
- 9.2  Log Tab in Context Panel (QLogHandler, LogView widget)
- 9.3  Visual Node Indicators (state-based rendering in NodeItem)
- 9.4  Graph Validation (GraphValidator with 5 checks, menu integration)
"""
from __future__ import annotations

import logging

import pytest

from PySide6.QtWidgets import QApplication

# Ensure a QApplication exists for all widget tests
@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# =========================================================================
# 9.1 — Structured Logging
# =========================================================================


class TestStructuredLogging:
    def test_setup_logging_returns_logger(self):
        from persistra.core.logging import setup_logging
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "persistra"

    def test_logger_has_handlers(self):
        from persistra.core.logging import setup_logging
        logger = setup_logging()
        # At least a console and file handler (may accumulate across calls)
        handler_types = {type(h).__name__ for h in logger.handlers}
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

    def test_log_dir_constant(self):
        from persistra.core.logging import LOG_DIR
        assert "persistra" in str(LOG_DIR)
        assert "logs" in str(LOG_DIR)

    def test_print_replaced_in_manager(self):
        """Verify that manager.py uses logger instead of print()."""
        import inspect
        from persistra.ui.graph import manager as mgr_module
        source = inspect.getsource(mgr_module)
        assert "print(" not in source
        assert "logger.error" in source


# =========================================================================
# 9.2 — Log Tab in Context Panel
# =========================================================================


class TestQLogHandler:
    def test_is_logging_handler(self):
        from persistra.ui.widgets.log_view import QLogHandler
        handler = QLogHandler()
        assert isinstance(handler, logging.Handler)

    def test_has_log_record_signal(self):
        from persistra.ui.widgets.log_view import QLogHandler
        handler = QLogHandler()
        assert hasattr(handler, "log_record")


class TestLogView:
    def test_is_qwidget(self):
        from PySide6.QtWidgets import QWidget
        from persistra.ui.widgets.log_view import LogView
        lv = LogView()
        assert isinstance(lv, QWidget)

    def test_has_text_edit(self):
        from PySide6.QtWidgets import QPlainTextEdit
        from persistra.ui.widgets.log_view import LogView
        lv = LogView()
        assert isinstance(lv.text_edit, QPlainTextEdit)
        assert lv.text_edit.isReadOnly()

    def test_has_node_filter(self):
        from PySide6.QtWidgets import QComboBox
        from persistra.ui.widgets.log_view import LogView
        lv = LogView()
        assert isinstance(lv.node_filter, QComboBox)
        assert lv.node_filter.currentText() == "All Nodes"

    def test_populate_node_filter(self):
        from persistra.ui.widgets.log_view import LogView
        lv = LogView()
        lv.populate_node_filter(["NodeA", "NodeB", "NodeA"])
        # All Nodes + 2 unique names
        assert lv.node_filter.count() == 3

    def test_context_panel_has_log_widget(self):
        from persistra.ui.widgets.context_panel import ContextPanel
        from persistra.ui.widgets.log_view import LogView
        cp = ContextPanel()
        assert isinstance(cp.log_widget, LogView)


# =========================================================================
# 9.3 — Visual Node Indicators
# =========================================================================


class TestVisualNodeIndicators:
    def test_node_item_paint_imports_state(self):
        """NodeItem.paint should reference NodeState."""
        import inspect
        from persistra.ui.graph.items import NodeItem
        source = inspect.getsource(NodeItem.paint)
        assert "NodeState" in source

    def test_node_item_paint_handles_error_state(self):
        """NodeItem.paint should have ERROR-specific rendering."""
        import inspect
        from persistra.ui.graph.items import NodeItem
        source = inspect.getsource(NodeItem.paint)
        assert "ERROR" in source
        assert "⚠" in source

    def test_node_item_paint_handles_dirty_state(self):
        import inspect
        from persistra.ui.graph.items import NodeItem
        source = inspect.getsource(NodeItem.paint)
        assert "DIRTY" in source
        assert "DashLine" in source

    def test_node_item_paint_handles_computing_state(self):
        import inspect
        from persistra.ui.graph.items import NodeItem
        source = inspect.getsource(NodeItem.paint)
        assert "COMPUTING" in source

    def test_node_item_paint_handles_invalid_state(self):
        import inspect
        from persistra.ui.graph.items import NodeItem
        source = inspect.getsource(NodeItem.paint)
        assert "INVALID" in source
        assert "setAlpha" in source


# =========================================================================
# 9.4 — Graph Validation
# =========================================================================


class TestValidationMessage:
    def test_is_dataclass(self):
        from persistra.core.validation import ValidationMessage
        msg = ValidationMessage(level="error", node_id="abc", message="test")
        assert msg.level == "error"
        assert msg.node_id == "abc"
        assert msg.message == "test"


class TestGraphValidator:
    def test_empty_project(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        v = GraphValidator()
        msgs = v.validate(Project())
        assert msgs == []

    def test_disconnected_required_input(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        from persistra.operations.preprocessing import Normalize
        p = Project()
        p.add_node(Normalize)
        msgs = GraphValidator().validate(p)
        errors = [m for m in msgs if m.level == "error"]
        assert any("not connected" in m.message for m in errors)

    def test_orphan_node_warning(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        from persistra.operations.io import DataGenerator
        p = Project()
        p.add_node(DataGenerator)
        msgs = GraphValidator().validate(p)
        warnings = [m for m in msgs if m.level == "warning"]
        assert any("orphan" in m.message.lower() for m in warnings)

    def test_connected_nodes_no_orphan(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        from persistra.operations.io import DataGenerator
        from persistra.operations.preprocessing import Normalize
        p = Project()
        gen = p.add_node(DataGenerator)
        norm = p.add_node(Normalize)
        p.connect(gen, "data", norm, "data")
        msgs = GraphValidator().validate(p)
        orphan_msgs = [m for m in msgs if "orphan" in m.message.lower()]
        assert len(orphan_msgs) == 0

    def test_missing_parameter_warning(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        from persistra.operations.io import CSVLoader
        p = Project()
        node = p.add_node(CSVLoader)
        # Set a parameter to empty string
        node.set_parameter("filepath", "")
        msgs = GraphValidator().validate(p)
        warnings = [m for m in msgs if m.level == "warning" and "filepath" in m.message]
        assert len(warnings) >= 1

    def test_no_missing_parameter_with_defaults(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator
        from persistra.operations.io import DataGenerator
        p = Project()
        p.add_node(DataGenerator)
        msgs = GraphValidator().validate(p)
        param_warnings = [m for m in msgs if "empty or None" in m.message]
        assert len(param_warnings) == 0

    def test_validate_returns_list(self):
        from persistra.core.project import Project
        from persistra.core.validation import GraphValidator, ValidationMessage
        p = Project()
        msgs = GraphValidator().validate(p)
        assert isinstance(msgs, list)
        # If non-empty, should all be ValidationMessage
        for m in msgs:
            assert isinstance(m, ValidationMessage)


class TestValidateGraphMenuIntegration:
    def test_menu_bar_has_validate_graph_signal(self):
        from persistra.ui.menus.menu_bar import PersistMenuBar
        mb = PersistMenuBar()
        assert hasattr(mb, "validate_graph")

    def test_toolbar_has_validate_graph_signal(self):
        from persistra.ui.menus.toolbar import PersistToolBar
        tb = PersistToolBar()
        assert hasattr(tb, "validate_graph")
