"""
src/persistra/ui/widgets/recent_projects.py

QListWidget-based panel that shows recently opened projects.
Displayed in the Node Browser area when no project is open.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from persistra.core.recent import load_recent_projects


class RecentProjectsList(QWidget):
    """Shows a list of recently opened projects with a 'New Project' button.

    Signals
    -------
    project_selected(str)
        Emitted when the user clicks on a recent project entry.
    new_project_requested()
        Emitted when the user clicks the 'New Project' button.
    """

    project_selected = Signal(str)
    new_project_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._new_btn = QPushButton("New Project")
        self._new_btn.clicked.connect(self.new_project_requested.emit)
        layout.addWidget(self._new_btn)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_clicked)
        self._list.setStyleSheet(
            """
            QListWidget {
                background-color: #252526;
                alternate-background-color: #2E2E2E;
                color: #DDD;
                border: 1px solid #3E3E42;
            }
            QListWidget::item { padding: 5px; }
            QListWidget::item:selected { background-color: #37373D; color: white; }
            QListWidget::item:hover { background-color: #333333; }
            """
        )
        layout.addWidget(self._list)

        self.refresh()

    def refresh(self) -> None:
        """Reload the recent projects list from disk."""
        self._list.clear()
        for filepath in load_recent_projects():
            p = Path(filepath)
            name = p.stem
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                mtime = "unknown"
            item = QListWidgetItem(f"{name}  —  {filepath}\nLast modified: {mtime}")
            item.setData(Qt.ItemDataRole.UserRole, filepath)
            self._list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if filepath:
            self.project_selected.emit(filepath)
