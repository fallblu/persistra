"""
Tests for viz panel node selection wiring.

Verifies that selecting a node in the graph editor updates the viz panel.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestVizPanelNodeSelection:
    """Verify node_selected signal is connected to viz_panel.display_node."""

    def test_node_selected_connected_to_viz_panel(self):
        """MainWindow must wire manager.node_selected → viz_panel.display_node."""
        from persistra.ui.main_window import MainWindow

        win = MainWindow()
        # Emit the node_selected signal with a mock node
        mock_node = MagicMock()
        mock_node.operation = MagicMock()
        mock_node._cached_outputs = {}

        with patch.object(win.viz_panel, "display_node", wraps=win.viz_panel.display_node) as spy:
            win.manager.node_selected.emit(mock_node)
            spy.assert_called_once_with(mock_node)

    def test_node_selected_updates_viz_panel_current_node(self):
        """After node_selected fires, viz_panel.current_node should be set."""
        from persistra.ui.main_window import MainWindow

        win = MainWindow()
        mock_node = MagicMock()
        mock_node.operation = MagicMock()
        mock_node._cached_outputs = {}

        win.manager.node_selected.emit(mock_node)
        assert win.viz_panel.current_node is mock_node
