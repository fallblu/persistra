import logging
import sys
from PySide6.QtWidgets import (QMainWindow, QWidget, QGridLayout,
                               QGraphicsView, QLabel, QFrame, QMessageBox,
                               QStatusBar)
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
from persistra.core.project import Project
from persistra.core.validation import GraphValidator
from persistra.operations import REGISTRY

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

        # --- Connections ---
        self.manager.node_selected.connect(self.context_panel.set_node)
        self.manager.computation_started.connect(self.status_bar.showMessage)
        self.manager.computation_finished.connect(
            lambda res: self.viz_panel.update_visualization(
                self.manager.current_worker.node, res
            )
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

        # Toolbar wiring
        self.toolbar.toggle_theme.connect(self.theme_manager.toggle)
        self.toolbar.zoom_to_fit.connect(self.view.zoom_to_fit)
        self.toolbar.auto_layout.connect(self.manager.auto_layout)
        self.toolbar.validate_graph.connect(self._validate_graph)

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


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
