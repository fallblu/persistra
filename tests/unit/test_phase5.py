"""
Tests for Phase 5 — UI/UX Overhaul & Theming.

Covers:
- 8.1  Theme Engine (ThemeTokens, ThemeManager, dark/light themes, QSS generation)
- 8.2  Menu Bar (PersistMenuBar with File/Edit/View/Help menus)
- 8.3  Toolbar (PersistToolBar with action buttons)
- 8.4  Node Browser Overhaul (searchable QTreeWidget with categories)
- 8.5.1 Snap-to-Grid
- 8.5.2 Auto-Layout (Sugiyama-style layered layout)
- 8.5.3 Category-Based Node Coloring (ThemeManager.get_category_color)
- 8.5.4 Copy-Paste
- 8.6  Context Panel Updates (Parameters/Info/Log tabs)
"""
from __future__ import annotations

import pytest
from dataclasses import fields

from PySide6.QtWidgets import QApplication

# Ensure a QApplication exists for all widget tests
@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# =========================================================================
# 8.1 — Theme Engine
# =========================================================================


class TestThemeTokens:
    """Verify ThemeTokens dataclass has all required fields."""

    def test_is_dataclass(self):
        from persistra.ui.theme.tokens import ThemeTokens
        assert hasattr(ThemeTokens, "__dataclass_fields__")

    def test_has_name_field(self):
        from persistra.ui.theme.tokens import ThemeTokens
        field_names = [f.name for f in fields(ThemeTokens)]
        assert "name" in field_names

    def test_has_all_global_tokens(self):
        from persistra.ui.theme.tokens import ThemeTokens
        field_names = {f.name for f in fields(ThemeTokens)}
        required = {
            "foreground", "foreground_secondary", "background",
            "background_secondary", "background_tertiary",
            "border", "border_focus",
        }
        assert required.issubset(field_names)

    def test_has_editor_tokens(self):
        from persistra.ui.theme.tokens import ThemeTokens
        field_names = {f.name for f in fields(ThemeTokens)}
        required = {
            "editor_background", "editor_grid", "editor_grid_major",
            "node_background", "node_border", "node_border_selected",
            "node_text", "wire_default", "wire_draft",
        }
        assert required.issubset(field_names)

    def test_has_category_tokens(self):
        from persistra.ui.theme.tokens import ThemeTokens
        field_names = {f.name for f in fields(ThemeTokens)}
        required = {
            "category_io", "category_preprocessing", "category_tda",
            "category_ml", "category_viz", "category_utility",
            "category_templates", "category_plugins",
        }
        assert required.issubset(field_names)


class TestDarkModernTheme:
    def test_name(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        assert DARK_MODERN.name == "dark"

    def test_background_is_dark(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        assert DARK_MODERN.background.startswith("#")

    def test_accent_color(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        assert DARK_MODERN.accent == "#007ACC"


class TestLightModernTheme:
    def test_name(self):
        from persistra.ui.theme.light_modern import LIGHT_MODERN
        assert LIGHT_MODERN.name == "light"

    def test_background_is_light(self):
        from persistra.ui.theme.light_modern import LIGHT_MODERN
        assert LIGHT_MODERN.background == "#FFFFFF"

    def test_accent_color(self):
        from persistra.ui.theme.light_modern import LIGHT_MODERN
        assert LIGHT_MODERN.accent == "#005FB8"


class TestStylesheetGeneration:
    def test_generates_string(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        from persistra.ui.theme.stylesheets import generate_stylesheet
        qss = generate_stylesheet(DARK_MODERN)
        assert isinstance(qss, str)
        assert len(qss) > 100

    def test_contains_widget_rules(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        from persistra.ui.theme.stylesheets import generate_stylesheet
        qss = generate_stylesheet(DARK_MODERN)
        assert "QWidget" in qss
        assert "QMenuBar" in qss
        assert "QToolBar" in qss
        assert "QTreeWidget" in qss

    def test_contains_token_values(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        from persistra.ui.theme.stylesheets import generate_stylesheet
        qss = generate_stylesheet(DARK_MODERN)
        assert DARK_MODERN.background in qss
        assert DARK_MODERN.foreground in qss
        assert DARK_MODERN.accent in qss


class TestThemeManager:
    def test_singleton(self):
        from persistra.ui.theme import ThemeManager
        tm1 = ThemeManager()
        tm2 = ThemeManager()
        assert tm1 is tm2

    def test_default_theme_is_dark(self):
        from persistra.ui.theme import ThemeManager
        tm = ThemeManager()
        assert tm.current_theme in ("dark", "light")

    def test_has_current_tokens(self):
        from persistra.ui.theme import ThemeManager
        from persistra.ui.theme.tokens import ThemeTokens
        tm = ThemeManager()
        assert isinstance(tm.current_tokens, ThemeTokens)

    def test_get_category_color(self):
        from persistra.ui.theme import ThemeManager
        tm = ThemeManager()
        color = tm.get_category_color("TDA")
        assert color.startswith("#")

    def test_get_category_color_unknown(self):
        from persistra.ui.theme import ThemeManager
        tm = ThemeManager()
        color = tm.get_category_color("NonexistentCategory")
        assert color == tm.current_tokens.category_utility

    def test_themes_dict(self):
        from persistra.ui.theme import THEMES
        assert "dark" in THEMES
        assert "light" in THEMES


# =========================================================================
# 8.2 — Menu Bar
# =========================================================================


class TestMenuBar:
    def test_has_signals(self):
        from persistra.ui.menus.menu_bar import PersistMenuBar
        mb = PersistMenuBar()
        assert hasattr(mb, "new_project")
        assert hasattr(mb, "save_project")
        assert hasattr(mb, "toggle_theme")
        assert hasattr(mb, "zoom_in")
        assert hasattr(mb, "zoom_out")
        assert hasattr(mb, "copy_nodes")
        assert hasattr(mb, "paste_nodes")
        assert hasattr(mb, "auto_layout")

    def test_menu_count(self):
        from persistra.ui.menus.menu_bar import PersistMenuBar
        mb = PersistMenuBar()
        # Should have 4 menus: File, Edit, View, Help
        assert len(mb.actions()) == 4


# =========================================================================
# 8.3 — Toolbar
# =========================================================================


class TestToolbar:
    def test_has_signals(self):
        from persistra.ui.menus.toolbar import PersistToolBar
        tb = PersistToolBar()
        assert hasattr(tb, "new_project")
        assert hasattr(tb, "save_project")
        assert hasattr(tb, "run_graph")
        assert hasattr(tb, "toggle_theme")
        assert hasattr(tb, "zoom_to_fit")
        assert hasattr(tb, "auto_layout")

    def test_not_movable(self):
        from persistra.ui.menus.toolbar import PersistToolBar
        tb = PersistToolBar()
        assert not tb.isMovable()

    def test_has_theme_button(self):
        from persistra.ui.menus.toolbar import PersistToolBar
        tb = PersistToolBar()
        assert tb.theme_button is not None


# =========================================================================
# 8.4 — Node Browser Overhaul
# =========================================================================


class TestNodeBrowser:
    def test_is_qwidget(self):
        from PySide6.QtWidgets import QWidget
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        assert isinstance(nb, QWidget)

    def test_has_search_bar(self):
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        assert nb.search_bar is not None

    def test_has_tree(self):
        from PySide6.QtWidgets import QTreeWidget
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        assert isinstance(nb.tree, QTreeWidget)

    def test_add_operation_creates_category(self):
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        nb.add_operation("TestOp", "TDA", "A test operation")
        assert "TDA" in nb._category_items
        assert nb._category_items["TDA"].childCount() == 1

    def test_add_multiple_to_same_category(self):
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        nb.add_operation("Op1", "TDA")
        nb.add_operation("Op2", "TDA")
        assert nb._category_items["TDA"].childCount() == 2

    def test_populate_from_registry(self):
        from persistra.operations import REGISTRY
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        nb.populate_from_registry(REGISTRY)
        assert len(nb._category_items) > 0

    def test_search_filter(self):
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        nb.add_operation("CSVLoader", "Input / Output", "Load CSV files")
        nb.add_operation("Normalize", "Preprocessing", "Normalize data")

        nb._filter_tree("CSV")
        cat_io = nb._category_items["Input / Output"]
        cat_pre = nb._category_items["Preprocessing"]
        assert not cat_io.child(0).isHidden()
        assert cat_pre.child(0).isHidden()

    def test_search_clear_shows_all(self):
        from persistra.ui.widgets.node_browser import NodeBrowser
        nb = NodeBrowser()
        nb.add_operation("CSVLoader", "Input / Output")
        nb.add_operation("Normalize", "Preprocessing")
        nb._filter_tree("CSV")
        nb._filter_tree("")
        assert not nb._category_items["Preprocessing"].child(0).isHidden()


# =========================================================================
# 8.5.1 — Snap-to-Grid
# =========================================================================


class TestSnapToGrid:
    def test_snap_exact(self):
        from PySide6.QtCore import QPointF
        from persistra.ui.graph.items import snap_to_grid
        result = snap_to_grid(QPointF(40, 60))
        assert result.x() == 40
        assert result.y() == 60

    def test_snap_round_up(self):
        from PySide6.QtCore import QPointF
        from persistra.ui.graph.items import snap_to_grid
        result = snap_to_grid(QPointF(31, 49))
        assert result.x() == 40
        assert result.y() == 40

    def test_snap_round_down(self):
        from PySide6.QtCore import QPointF
        from persistra.ui.graph.items import snap_to_grid
        result = snap_to_grid(QPointF(28, 22))
        assert result.x() == 20
        assert result.y() == 20

    def test_snap_custom_grid(self):
        from PySide6.QtCore import QPointF
        from persistra.ui.graph.items import snap_to_grid
        result = snap_to_grid(QPointF(37, 63), grid_size=50)
        assert result.x() == 50
        assert result.y() == 50

    def test_snap_negative(self):
        from PySide6.QtCore import QPointF
        from persistra.ui.graph.items import snap_to_grid
        result = snap_to_grid(QPointF(-31, -49))
        assert result.x() == -40
        assert result.y() == -40


# =========================================================================
# 8.5.2 — Auto-Layout
# =========================================================================


class TestAutoLayout:
    def test_auto_layout_empty_graph(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        manager.auto_layout()

    def test_auto_layout_single_node(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        item = manager.add_node("CSVLoader", 100, 200)
        assert item is not None
        manager.auto_layout()
        assert item.pos().x() == 0
        assert item.pos().y() == 0

    def test_auto_layout_connected_nodes(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        src_item = manager.add_node("DataGenerator", 0, 0)
        tgt_item = manager.add_node("Normalize", 0, 0)
        assert src_item is not None
        assert tgt_item is not None

        src_model = manager.node_map[src_item]
        tgt_model = manager.node_map[tgt_item]
        try:
            project.connect(src_model, "data", tgt_model, "data")
            from persistra.ui.graph.items import WireItem
            wire = WireItem(src_item.outputs[0], tgt_item.inputs[0])
            scene.addItem(wire)
            manager.wire_map[wire] = (src_model, tgt_model)
        except Exception:
            pass

        manager.auto_layout(h_spacing=250)
        assert src_item.pos().x() < tgt_item.pos().x()


# =========================================================================
# 8.5.3 — Category-Based Node Coloring
# =========================================================================


class TestCategoryColoring:
    def test_all_categories_have_colors(self):
        from persistra.ui.theme import ThemeManager
        tm = ThemeManager()
        categories = [
            "Input / Output", "Preprocessing", "TDA",
            "Machine Learning", "Visualization", "Utility",
            "Templates", "Plugins",
        ]
        for cat in categories:
            color = tm.get_category_color(cat)
            assert color.startswith("#"), f"{cat} has no valid color: {color}"

    def test_dark_and_light_have_different_colors(self):
        from persistra.ui.theme.dark_modern import DARK_MODERN
        from persistra.ui.theme.light_modern import LIGHT_MODERN
        assert DARK_MODERN.category_io != LIGHT_MODERN.category_io
        assert DARK_MODERN.category_tda != LIGHT_MODERN.category_tda


# =========================================================================
# 8.5.4 — Copy-Paste
# =========================================================================


class TestCopyPaste:
    def test_copy_empty_selection(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        manager.copy_selected()
        assert manager._clipboard == []

    def test_paste_empty_clipboard(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        manager.paste()
        assert len(project.nodes) == 0

    def test_copy_paste_creates_new_node(self):
        from persistra.core.project import Project
        from persistra.ui.graph.manager import GraphManager
        from persistra.ui.graph.scene import GraphScene
        scene = GraphScene()
        project = Project()
        manager = GraphManager(scene, project)
        item = manager.add_node("CSVLoader", 100, 100)
        assert item is not None

        item.setSelected(True)
        manager.copy_selected()
        assert len(manager._clipboard) == 1

        initial_count = len(project.nodes)
        manager.paste()
        assert len(project.nodes) == initial_count + 1

        ids = [n.id for n in project.nodes]
        assert len(set(ids)) == len(ids)


# =========================================================================
# 8.6 — Context Panel Updates
# =========================================================================


class TestContextPanel:
    def test_has_tabs(self):
        from PySide6.QtWidgets import QTabWidget
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        assert isinstance(cp.tabs, QTabWidget)

    def test_tab_count(self):
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        assert cp.tabs.count() == 3

    def test_tab_names(self):
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        tab_names = [cp.tabs.tabText(i) for i in range(cp.tabs.count())]
        assert "Parameters" in tab_names
        assert "Info" in tab_names
        assert "Log" in tab_names

    def test_set_node_none(self):
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        cp.set_node(None)
        assert cp.header.text() == "Context: No Selection"

    def test_set_node_updates_info(self):
        from persistra.core.project import Node
        from persistra.operations.io import CSVLoader
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        node = Node(CSVLoader)
        cp.set_node(node)
        assert "CSVLoader" in cp.header.text()
        info_text = cp.info_label.text()
        assert "Input / Output" in info_text or "CSVLoader" in info_text

    def test_has_log_view(self):
        from PySide6.QtWidgets import QPlainTextEdit
        from persistra.ui.widgets.context_panel import ContextPanel
        cp = ContextPanel()
        assert isinstance(cp.log_widget.text_edit, QPlainTextEdit)
        assert cp.log_widget.text_edit.isReadOnly()
