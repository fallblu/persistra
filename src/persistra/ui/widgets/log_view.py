"""
src/persistra/ui/widgets/log_view.py

Log viewer widget with a custom logging.Handler that emits Qt signals.
Features:
- QPlainTextEdit (read-only) for log display
- QLogHandler: logging.Handler subclass that emits Signal(str) per record
- Node filter dropdown (All Nodes + per-node filtering)
- Auto-scroll (pauses when user scrolls up)
- Level coloring: ERROR=red, WARNING=yellow, INFO=white/black, DEBUG=gray
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from persistra.ui.theme import ThemeManager


class QLogHandler(logging.Handler, QObject):
    """A logging.Handler that emits a Qt Signal for each log record."""

    log_record = Signal(str, str)  # (formatted_message, level_name)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.log_record.emit(msg, record.levelname)
        except Exception:
            self.handleError(record)


class LogView(QWidget):
    """Log panel widget with node filtering and level coloring."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # --- Filter bar ---
        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(4, 4, 4, 0)
        self.node_filter = QComboBox()
        self.node_filter.addItem("All Nodes")
        self.node_filter.setToolTip("Filter log messages by node")
        filter_bar.addWidget(self.node_filter)
        layout.addLayout(filter_bar)

        # --- Log text area ---
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)
        layout.addWidget(self.text_edit)

        # Auto-scroll state
        self._auto_scroll = True
        vbar = self.text_edit.verticalScrollBar()
        vbar.valueChanged.connect(self._on_scroll)

        # Install the log handler
        self.handler = QLogHandler()
        self.handler.log_record.connect(self._append_record)
        logging.getLogger("persistra").addHandler(self.handler)

    def closeEvent(self, event):
        """Remove the handler from the logger to prevent leaks."""
        logging.getLogger("persistra").removeHandler(self.handler)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate_node_filter(self, node_names: list[str]):
        """Rebuild the node filter dropdown from a list of node names."""
        current = self.node_filter.currentText()
        self.node_filter.clear()
        self.node_filter.addItem("All Nodes")
        for name in sorted(set(node_names)):
            self.node_filter.addItem(name)
        idx = self.node_filter.findText(current)
        if idx >= 0:
            self.node_filter.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _level_color(self, level_name: str) -> QColor:
        tokens = ThemeManager().current_tokens
        mapping = {
            "ERROR": QColor(tokens.log_error),
            "CRITICAL": QColor(tokens.log_error),
            "WARNING": QColor(tokens.log_warning),
            "INFO": QColor(tokens.log_info),
            "DEBUG": QColor(tokens.log_debug),
        }
        return mapping.get(level_name, QColor(tokens.log_info))

    def _append_record(self, message: str, level_name: str):
        """Append a formatted log record with level coloring."""
        # Node filtering: if a specific node is selected, only show records
        # that contain the node name in the message.
        selected_node = self.node_filter.currentText()
        if selected_node != "All Nodes":
            if selected_node not in message:
                return

        color = self._level_color(level_name)
        fmt = QTextCharFormat()
        fmt.setForeground(color)

        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)

        if self._auto_scroll:
            self.text_edit.verticalScrollBar().setValue(
                self.text_edit.verticalScrollBar().maximum()
            )

    def _on_scroll(self, value: int):
        """Pause auto-scroll when the user scrolls away from the bottom."""
        vbar = self.text_edit.verticalScrollBar()
        self._auto_scroll = value >= vbar.maximum() - 4
