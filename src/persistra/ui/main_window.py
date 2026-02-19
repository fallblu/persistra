import logging
import sys
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (QMainWindow, QWidget, QGridLayout,
                               QGraphicsView, QLabel, QFrame, QMessageBox,
                               QStatusBar, QFileDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter

# Import Custom UI
from persistra.ui.graph.scene import GraphScene
from persistra.ui.graph.manager import GraphManager
from persistra.ui.menus.menu_bar import PersistMenuBar
from persistra.ui.menus.toolbar import PersistToolBar
from persistra.ui.theme import ThemeManager
from persistra.ui.widgets.context_panel import ContextPanel
from persistra.ui.widgets.node_browser import NodeBrowser
from persistra.ui.widgets.viz_panel import VizPanel

# Import REAL Backend
from persistra.core.autosave import AutosaveService
from persistra.core.engine import ExecutionEngine
from persistra.core.io import ProjectSerializer
from persistra.core.project import Project
from persistra.core.recent import add_recent_project
from persistra.core.validation import GraphValidator
from persistra.operations import REGISTRY
from persistra.ui.dialogs.export_figure import ExportFigureDialog
from persistra.ui.widgets.recent_projects import RecentProjectsList

logger = logging.getLogger("persistra.ui.main_window")


class GraphView(QGraphicsView):
    def __init__(self, scene, manager, parent=None):
        super().__init__(scene, parent)
        self.manager = manager
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        op_name = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        self.manager.add_node(op_name, scene_pos.x(), scene_pos.y())
        event.accept()

    # --- Zoom helpers ---

    def zoom_in(self):
        self.scale(1.15, 1.15)

    def zoom_out(self):
        self.scale(1 / 1.15, 1 / 1.15)

    def zoom_to_fit(self):
        items_rect = self.scene().itemsBoundingRect()
        if items_rect.isNull():
            return
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Persistra - Visual Analysis Tool")
        self.resize(1280, 800)

        # Theme Manager
        self.theme_manager = ThemeManager()

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Initialize REAL Project Model
        self.project_model = Project()

        # --- Menu Bar ---
        self.menu_bar = PersistMenuBar(self)
        self.setMenuBar(self.menu_bar)

        # --- Toolbar ---
        self.toolbar = PersistToolBar(self)
        self.addToolBar(self.toolbar)

        # Layout Setup
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QGridLayout(central_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        for c in range(16):
            self.layout.setColumnStretch(c, 1)
        for r in range(10):
            self.layout.setRowStretch(r, 1)

        # 1. Node Browser (category tree)
        self.node_browser = NodeBrowser()
        self.node_browser.populate_from_registry(REGISTRY)
        self.layout.addWidget(self.node_browser, 0, 0, 4, 6)

        # 2. Graph Editor
        self.scene = GraphScene()
        self.manager = GraphManager(self.scene, self.project_model)
        self.view = GraphView(self.scene, self.manager)
        self.layout.addWidget(self.view, 4, 0, 6, 6)

        # 3. Viz Panel
        self.viz_panel = VizPanel()
        self.layout.addWidget(self.viz_panel, 0, 6, 6, 10)

        # 4. Context Panel
        self.context_panel = ContextPanel()
        self.layout.addWidget(self.context_panel, 6, 6, 4, 10)

        # Autosave service
        self.autosave_service = AutosaveService(self)
        self._current_filepath = None

        # Recent Projects widget
        self.recent_projects = RecentProjectsList()
        self.recent_projects.project_selected.connect(self._open_project_path)
        self.recent_projects.new_project_requested.connect(self._new_project)

        # --- Connections ---
        self.manager.node_selected.connect(self.context_panel.set_node)
        self.manager.computation_started.connect(self.status_bar.showMessage)
        self.manager.computation_finished.connect(
            lambda res, node: self.viz_panel.update_visualization(node, res)
        )

        # Menu bar wiring
        self.menu_bar.toggle_theme.connect(self.theme_manager.toggle)
        self.menu_bar.zoom_in.connect(self.view.zoom_in)
        self.menu_bar.zoom_out.connect(self.view.zoom_out)
        self.menu_bar.zoom_to_fit.connect(self.view.zoom_to_fit)
        self.menu_bar.auto_layout.connect(self.manager.auto_layout)
        self.menu_bar.copy_nodes.connect(self.manager.copy_selected)
        self.menu_bar.paste_nodes.connect(self.manager.paste)
        self.menu_bar.validate_graph.connect(self._validate_graph)
        self.menu_bar.quit_app.connect(self.close)

        # File operations
        self.menu_bar.new_project.connect(self._new_project)
        self.menu_bar.open_project.connect(self._open_project)
        self.menu_bar.save_project.connect(self._save_project)
        self.menu_bar.save_project_as.connect(self._save_project_as)
        self.menu_bar.export_figure.connect(self._export_figure)

        # Edit operations
        self.menu_bar.delete_nodes.connect(self.manager.delete_selected)
        self.menu_bar.select_all.connect(self._select_all)

        # View operations
        self.menu_bar.toggle_auto_compute.connect(self._toggle_auto_compute)

        # Help operations
        self.menu_bar.about.connect(self._show_about)
        self.menu_bar.open_docs.connect(self._open_docs)

        # Toolbar wiring
        self.toolbar.toggle_theme.connect(self.theme_manager.toggle)
        self.toolbar.zoom_to_fit.connect(self.view.zoom_to_fit)
        self.toolbar.auto_layout.connect(self.manager.auto_layout)
        self.toolbar.validate_graph.connect(self._validate_graph)
        self.toolbar.new_project.connect(self._new_project)
        self.toolbar.open_project.connect(self._open_project)
        self.toolbar.save_project.connect(self._save_project)
        self.toolbar.run_graph.connect(self._run_graph)
        self.toolbar.stop_graph.connect(self._stop_graph)

        # Apply theme
        self.theme_manager.apply()

    # ------------------------------------------------------------------
    # Graph Validation (§9.4)
    # ------------------------------------------------------------------

    def _validate_graph(self):
        """Run graph validation and display results in the log tab."""
        validator = GraphValidator()
        messages = validator.validate(self.project_model)

        for msg in messages:
            log_line = f"[{msg.level.upper()}] {msg.message}"
            if msg.level == "error":
                logger.error(log_line)
            elif msg.level == "warning":
                logger.warning(log_line)
            else:
                logger.info(log_line)

        errors = [m for m in messages if m.level == "error"]
        warnings = [m for m in messages if m.level == "warning"]

        if not messages:
            logger.info("Graph validation passed — no issues found.")
            self.status_bar.showMessage("Validation passed ✓")
        else:
            self.status_bar.showMessage(
                f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)"
            )

        if errors:
            summary = "\n".join(f"• {e.message}" for e in errors)
            QMessageBox.warning(
                self,
                "Validation Errors",
                f"The graph has {len(errors)} error(s) that must be fixed "
                f"before execution:\n\n{summary}",
            )

    # ------------------------------------------------------------------
    # File Operations (§10.2)
    # ------------------------------------------------------------------

    def _new_project(self):
        """Create a new empty project."""
        self.autosave_service.stop()
        self.project_model.clear()
        self.scene.clear()
        self.manager.node_map.clear()
        self.manager.wire_map.clear()
        self._current_filepath = None
        self.viz_panel.reset_views()
        self.context_panel.set_node(None)
        self.status_bar.showMessage("New project created")
        logger.info("New project created")

    def _open_project(self):
        """Show file dialog and load a .persistra archive."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Persistra Files (*.persistra);;All Files (*)"
        )
        if filepath:
            self._open_project_path(filepath)

    def _open_project_path(self, filepath):
        """Load a project from the given file path."""
        try:
            self.autosave_service.stop()
            serializer = ProjectSerializer()
            self.project_model = serializer.load(Path(filepath))
            self._current_filepath = Path(filepath)

            # Rebuild scene from loaded project
            self.scene.clear()
            self.manager.node_map.clear()
            self.manager.wire_map.clear()
            self.manager.project = self.project_model

            # Recreate node items
            from persistra.ui.graph.items import NodeItem
            for node_model in self.project_model.nodes:
                node_item = NodeItem(node_model)
                node_item.setPos(*node_model.position)
                self.scene.addItem(node_item)
                self.manager.node_map[node_item] = node_model

            # Wire autosave
            self.autosave_service.set_project(self.project_model, self._current_filepath)
            self.autosave_service.start()

            add_recent_project(filepath)
            self.status_bar.showMessage(f"Opened: {filepath}")
            logger.info("Project opened: %s", filepath)
        except Exception as exc:
            logger.exception("Failed to open project: %s", filepath)
            QMessageBox.critical(self, "Open Failed", str(exc))

    def _save_project(self):
        """Save to current path, or prompt if untitled."""
        if self._current_filepath:
            self._do_save(self._current_filepath)
        else:
            self._save_project_as()

    def _save_project_as(self):
        """Show save dialog and save to new path."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "Persistra Files (*.persistra)"
        )
        if filepath:
            if not filepath.endswith(".persistra"):
                filepath += ".persistra"
            self._do_save(Path(filepath))

    def _do_save(self, filepath):
        """Perform the actual save."""
        try:
            serializer = ProjectSerializer()
            serializer.save(self.project_model, filepath)
            self._current_filepath = Path(filepath)

            self.autosave_service.set_project(self.project_model, self._current_filepath)
            self.autosave_service.start()

            add_recent_project(str(filepath))
            AutosaveService.remove_autosave(self._current_filepath)
            self.status_bar.showMessage(f"Saved: {filepath}")
            logger.info("Project saved: %s", filepath)
        except Exception as exc:
            logger.exception("Failed to save project: %s", filepath)
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _export_figure(self):
        """Open ExportFigureDialog for the active visualization."""
        fig = None
        mpl_view = self.viz_panel.matplotlib_view
        if mpl_view.canvas.figure and mpl_view.canvas.figure.get_axes():
            fig = mpl_view.canvas.figure
        dialog = ExportFigureDialog(figure=fig, parent=self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Edit Operations
    # ------------------------------------------------------------------

    def _select_all(self):
        """Select all items in the graph scene."""
        for item in self.scene.items():
            item.setSelected(True)

    # ------------------------------------------------------------------
    # View Operations
    # ------------------------------------------------------------------

    def _toggle_auto_compute(self):
        """Toggle the project auto_compute flag."""
        self.project_model.auto_compute = not self.project_model.auto_compute
        state = "ON" if self.project_model.auto_compute else "OFF"
        self.status_bar.showMessage(f"Auto-Compute: {state}")
        logger.info("Auto-compute toggled: %s", state)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _run_graph(self):
        """Execute the full graph via ExecutionEngine."""
        engine = ExecutionEngine()
        self.status_bar.showMessage("Running graph\u2026")
        logger.info("Graph execution started")
        try:
            results = engine.run(self.project_model, dirty_only=True)
            errors = [r for r in results if not r.success]
            if errors:
                summary = "; ".join(f"{e.node_id}: {e.error}" for e in errors)
                self.status_bar.showMessage(
                    f"Execution finished with {len(errors)} error(s)"
                )
                logger.error("Graph execution errors: %s", summary)
            else:
                self.status_bar.showMessage("Graph execution completed \u2713")
                logger.info("Graph execution completed successfully")
        except Exception as exc:
            self.status_bar.showMessage("Execution failed")
            logger.exception("Graph execution failed")
            QMessageBox.critical(self, "Execution Error", str(exc))

    def _stop_graph(self):
        """Cancel running graph execution."""
        if hasattr(self, '_engine') and self._engine is not None:
            self._engine.cancel()
        self.status_bar.showMessage("Execution cancelled")
        logger.info("Graph execution cancelled")

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _show_about(self):
        """Show about dialog."""
        from persistra.core.io import get_app_version
        QMessageBox.about(
            self,
            "About Persistra",
            f"<b>Persistra</b> v{get_app_version()}<br><br>"
            "Visual Analysis Tool for Topological Data Analysis<br><br>"
            "\u00a9 2026 Persistra Contributors",
        )

    def _open_docs(self):
        """Open documentation in browser."""
        webbrowser.open("https://persistra.readthedocs.io/")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
