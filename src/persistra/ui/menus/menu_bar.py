"""
Menu bar for the Persistra main window.

Provides File, Edit, View, and Help menus with standard actions.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar


class PersistMenuBar(QMenuBar):
    """Application menu bar with File, Edit, View, and Help menus."""

    # Signals emitted by menu actions
    new_project = Signal()
    open_project = Signal()
    save_project = Signal()
    save_project_as = Signal()
    export_figure = Signal()
    quit_app = Signal()

    copy_nodes = Signal()
    paste_nodes = Signal()
    delete_nodes = Signal()
    select_all = Signal()

    toggle_theme = Signal()
    zoom_in = Signal()
    zoom_out = Signal()
    zoom_to_fit = Signal()
    toggle_auto_compute = Signal()
    auto_layout = Signal()

    about = Signal()
    open_docs = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_help_menu()

    def _build_file_menu(self):
        menu = self.addMenu("&File")

        action = menu.addAction("New Project")
        action.triggered.connect(self.new_project.emit)

        action = menu.addAction("Open Project")
        action.triggered.connect(self.open_project.emit)

        menu.addSeparator()

        action = menu.addAction("Save")
        action.setShortcut(QKeySequence("Ctrl+S"))
        action.triggered.connect(self.save_project.emit)

        action = menu.addAction("Save As")
        action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        action.triggered.connect(self.save_project_as.emit)

        menu.addSeparator()

        action = menu.addAction("Export Figure")
        action.triggered.connect(self.export_figure.emit)

        menu.addSeparator()

        action = menu.addAction("Quit")
        action.setShortcut(QKeySequence("Ctrl+Q"))
        action.triggered.connect(self.quit_app.emit)

    def _build_edit_menu(self):
        menu = self.addMenu("&Edit")

        action = menu.addAction("Copy")
        action.setShortcut(QKeySequence("Ctrl+C"))
        action.triggered.connect(self.copy_nodes.emit)

        action = menu.addAction("Paste")
        action.setShortcut(QKeySequence("Ctrl+V"))
        action.triggered.connect(self.paste_nodes.emit)

        action = menu.addAction("Delete")
        action.setShortcut(QKeySequence("Del"))
        action.triggered.connect(self.delete_nodes.emit)

        menu.addSeparator()

        action = menu.addAction("Select All")
        action.setShortcut(QKeySequence("Ctrl+A"))
        action.triggered.connect(self.select_all.emit)

    def _build_view_menu(self):
        menu = self.addMenu("&View")

        action = menu.addAction("Toggle Light/Dark Mode")
        action.triggered.connect(self.toggle_theme.emit)

        menu.addSeparator()

        action = menu.addAction("Zoom In")
        action.setShortcut(QKeySequence("Ctrl+="))
        action.triggered.connect(self.zoom_in.emit)

        action = menu.addAction("Zoom Out")
        action.setShortcut(QKeySequence("Ctrl+-"))
        action.triggered.connect(self.zoom_out.emit)

        action = menu.addAction("Zoom to Fit")
        action.setShortcut(QKeySequence("Ctrl+0"))
        action.triggered.connect(self.zoom_to_fit.emit)

        menu.addSeparator()

        action = menu.addAction("Auto Layout")
        action.triggered.connect(self.auto_layout.emit)

        menu.addSeparator()

        self._auto_compute_action = menu.addAction("Toggle Auto-Compute")
        self._auto_compute_action.setCheckable(True)
        self._auto_compute_action.triggered.connect(self.toggle_auto_compute.emit)

    def _build_help_menu(self):
        menu = self.addMenu("&Help")

        action = menu.addAction("About Persistra")
        action.triggered.connect(self.about.emit)

        action = menu.addAction("Documentation")
        action.triggered.connect(self.open_docs.emit)
