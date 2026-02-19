"""
Main toolbar for the Persistra application.

Buttons (left to right): New · Open · Save · | · Run · Stop · Validate Graph
· | · Zoom to Fit · | · Theme Toggle (sun/moon icon)
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStyle, QToolBar, QToolButton


class PersistToolBar(QToolBar):
    """Application toolbar with common actions."""

    new_project = Signal()
    open_project = Signal()
    save_project = Signal()

    run_graph = Signal()
    stop_graph = Signal()
    validate_graph = Signal()

    zoom_to_fit = Signal()
    auto_layout = Signal()

    toggle_theme = Signal()

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        style = self.style()

        # --- File actions ---
        btn = self._add_button(
            "New", style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        btn.clicked.connect(self.new_project.emit)

        btn = self._add_button(
            "Open", style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        btn.clicked.connect(self.open_project.emit)

        btn = self._add_button(
            "Save", style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        btn.clicked.connect(self.save_project.emit)

        self.addSeparator()

        # --- Execution actions ---
        btn = self._add_button(
            "Run", style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        )
        btn.clicked.connect(self.run_graph.emit)

        btn = self._add_button(
            "Stop", style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
        )
        btn.clicked.connect(self.stop_graph.emit)

        btn = self._add_button(
            "Validate Graph",
            style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        btn.clicked.connect(self.validate_graph.emit)

        self.addSeparator()

        # --- View actions ---
        btn = self._add_button(
            "Zoom to Fit",
            style.standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton),
        )
        btn.clicked.connect(self.zoom_to_fit.emit)

        btn = self._add_button(
            "Auto Layout",
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView),
        )
        btn.clicked.connect(self.auto_layout.emit)

        self.addSeparator()

        # --- Theme toggle ---
        self.theme_button = self._add_button(
            "Theme",
            style.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon),
        )
        self.theme_button.setToolTip("Toggle Light/Dark Mode")
        self.theme_button.clicked.connect(self.toggle_theme.emit)

    def _add_button(self, text, icon):
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setToolTip(text)
        btn.setStatusTip(text)
        self.addWidget(btn)
        return btn
