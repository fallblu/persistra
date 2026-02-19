"""QSS stylesheet generation from theme tokens."""

from persistra.ui.theme.tokens import ThemeTokens


def generate_stylesheet(tokens: ThemeTokens) -> str:
    """Generate a complete QSS stylesheet from theme tokens."""
    return f"""
    /* === Global === */
    QWidget {{
        background-color: {tokens.background};
        color: {tokens.foreground};
        font-family: "Segoe UI", "SF Pro", "Helvetica Neue", sans-serif;
        font-size: 13px;
    }}

    /* === Main Window === */
    QMainWindow {{
        background-color: {tokens.background};
    }}

    /* === Menu Bar === */
    QMenuBar {{
        background-color: {tokens.toolbar_background};
        color: {tokens.menu_text};
        border-bottom: 1px solid {tokens.border};
        padding: 2px;
    }}
    QMenuBar::item:selected {{
        background-color: {tokens.menu_hover};
    }}
    QMenu {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        border: 1px solid {tokens.border};
    }}
    QMenu::item:selected {{
        background-color: {tokens.menu_hover};
    }}
    QMenu::separator {{
        height: 1px;
        background: {tokens.border};
        margin: 4px 8px;
    }}

    /* === Toolbar === */
    QToolBar {{
        background-color: {tokens.toolbar_background};
        border-bottom: 1px solid {tokens.border};
        spacing: 4px;
        padding: 2px;
    }}
    QToolBar::separator {{
        width: 1px;
        background: {tokens.toolbar_separator};
        margin: 4px 2px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px;
        color: {tokens.foreground};
    }}
    QToolButton:hover {{
        background-color: {tokens.menu_hover};
        border: 1px solid {tokens.border};
    }}
    QToolButton:pressed {{
        background-color: {tokens.accent};
        color: {tokens.accent_foreground};
    }}

    /* === Status Bar === */
    QStatusBar {{
        background-color: {tokens.statusbar_background};
        color: {tokens.statusbar_text};
        border-top: 1px solid {tokens.border};
    }}

    /* === Tab Widget === */
    QTabWidget::pane {{
        border: 1px solid {tokens.border};
        background-color: {tokens.background_secondary};
    }}
    QTabBar::tab {{
        background-color: {tokens.viz_tab_inactive};
        color: {tokens.foreground_secondary};
        border: 1px solid {tokens.border};
        padding: 6px 12px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {tokens.background_secondary};
        color: {tokens.foreground};
        border-bottom: 2px solid {tokens.viz_tab_active};
    }}
    QTabBar::tab:hover {{
        background-color: {tokens.menu_hover};
    }}

    /* === Tree Widget (Node Browser) === */
    QTreeWidget {{
        background-color: {tokens.browser_background};
        alternate-background-color: {tokens.browser_alternate};
        color: {tokens.browser_text};
        border: 1px solid {tokens.border};
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 4px 8px;
    }}
    QTreeWidget::item:selected {{
        background-color: {tokens.browser_selected};
        color: {tokens.foreground};
    }}
    QTreeWidget::item:hover {{
        background-color: {tokens.browser_hover};
    }}
    QTreeWidget::branch {{
        background-color: {tokens.browser_background};
    }}

    /* === List Widget (Recent Projects) === */
    QListWidget {{
        background-color: {tokens.browser_background};
        alternate-background-color: {tokens.browser_alternate};
        color: {tokens.browser_text};
        border: 1px solid {tokens.border};
    }}
    QListWidget::item {{
        padding: 6px 8px;
    }}
    QListWidget::item:selected {{
        background-color: {tokens.browser_selected};
    }}
    QListWidget::item:hover {{
        background-color: {tokens.browser_hover};
    }}

    /* === Table View === */
    QTableView {{
        background-color: {tokens.background_secondary};
        alternate-background-color: {tokens.background_tertiary};
        color: {tokens.foreground};
        gridline-color: {tokens.border};
        border: 1px solid {tokens.border};
        selection-background-color: {tokens.accent};
        selection-color: {tokens.accent_foreground};
    }}
    QHeaderView::section {{
        background-color: {tokens.panel_header_background};
        color: {tokens.panel_header_foreground};
        border: 1px solid {tokens.border};
        padding: 4px 8px;
        font-weight: bold;
    }}

    /* === Scroll Area === */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    /* === Scrollbar === */
    QScrollBar:vertical {{
        background: {tokens.scrollbar_background};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens.scrollbar_handle};
        min-height: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {tokens.scrollbar_handle_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {tokens.scrollbar_background};
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {tokens.scrollbar_handle};
        min-width: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {tokens.scrollbar_handle_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* === Input Widgets === */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {tokens.context_input_background};
        color: {tokens.foreground};
        border: 1px solid {tokens.context_input_border};
        border-radius: 3px;
        padding: 4px 6px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {tokens.border_focus};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        selection-background-color: {tokens.menu_hover};
        border: 1px solid {tokens.border};
    }}

    /* === Plain Text Edit (Log, Code Editor) === */
    QPlainTextEdit {{
        background-color: {tokens.log_background};
        color: {tokens.foreground};
        border: 1px solid {tokens.border};
        font-family: "Cascadia Code", "Consolas", "Fira Code", monospace;
        font-size: 12px;
    }}

    /* === Labels === */
    QLabel {{
        background-color: transparent;
        color: {tokens.foreground};
    }}

    /* === Push Button === */
    QPushButton {{
        background-color: {tokens.accent};
        color: {tokens.accent_foreground};
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {tokens.accent_hover};
    }}
    QPushButton:pressed {{
        background-color: {tokens.accent};
    }}
    QPushButton:disabled {{
        background-color: {tokens.background_tertiary};
        color: {tokens.foreground_secondary};
    }}

    /* === Checkbox === */
    QCheckBox {{
        color: {tokens.foreground};
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {tokens.border};
        border-radius: 3px;
        background-color: {tokens.context_input_background};
    }}
    QCheckBox::indicator:checked {{
        background-color: {tokens.accent};
        border-color: {tokens.accent};
    }}

    /* === Group Box === */
    QGroupBox {{
        border: 1px solid {tokens.border};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 16px;
        color: {tokens.foreground};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}

    /* === Splitter === */
    QSplitter::handle {{
        background-color: {tokens.border};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QSplitter::handle:vertical {{
        height: 2px;
    }}

    /* === Tooltip === */
    QToolTip {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        border: 1px solid {tokens.border};
        padding: 4px;
    }}
    """
