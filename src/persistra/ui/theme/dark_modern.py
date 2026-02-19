"""VS Code Dark Modern theme token values."""

from persistra.ui.theme.tokens import ThemeTokens

DARK_MODERN = ThemeTokens(
    # --- Global ---
    name="dark",
    foreground="#CCCCCC",
    foreground_secondary="#8A8A8A",
    background="#1F1F1F",
    background_secondary="#252526",
    background_tertiary="#2D2D2D",
    border="#3E3E42",
    border_focus="#007ACC",

    # --- Accent & Semantic ---
    accent="#007ACC",
    accent_hover="#1A8AD4",
    accent_foreground="#FFFFFF",
    error="#F14C4C",
    error_foreground="#FFFFFF",
    warning="#CCA700",
    success="#89D185",
    info="#3794FF",

    # --- Graph Editor ---
    editor_background="#1E1E1E",
    editor_grid="#2A2A2A",
    editor_grid_major="#1A1A1A",
    node_background="#252526",
    node_background_selected="#2D2D30",
    node_border="#3E3E42",
    node_border_selected="#007ACC",
    node_border_error="#F14C4C",
    node_text="#CCCCCC",
    socket_default="#B0B0B0",
    socket_hover="#FF9800",
    wire_default="#888888",
    wire_draft="#FF9800",
    wire_selected="#007ACC",

    # --- Node Category Header Colors ---
    category_io="#3A7CA5",
    category_preprocessing="#5A8A4A",
    category_tda="#7E5A9F",
    category_ml="#A07030",
    category_viz="#A04545",
    category_utility="#6A6A7A",
    category_templates="#4A9A9A",
    category_plugins="#9A7A4A",

    # --- Panels ---
    panel_header_background="#333333",
    panel_header_foreground="#CCCCCC",

    # --- Node Browser ---
    browser_background="#252526",
    browser_alternate="#2A2A2E",
    browser_selected="#37373D",
    browser_hover="#2E2E33",
    browser_text="#CCCCCC",

    # --- Context Panel ---
    context_background="#252526",
    context_header="#333333",
    context_input_background="#3C3C3C",
    context_input_border="#3E3E42",

    # --- Viz Panel ---
    viz_background="#1E1E1E",
    viz_tab_active="#007ACC",
    viz_tab_inactive="#2D2D2D",

    # --- Log View ---
    log_background="#1E1E1E",
    log_error="#F14C4C",
    log_warning="#CCA700",
    log_info="#CCCCCC",
    log_debug="#6A6A6A",

    # --- Toolbar & Menu ---
    toolbar_background="#2D2D2D",
    toolbar_separator="#3E3E42",
    menu_background="#2D2D30",
    menu_hover="#094771",
    menu_text="#CCCCCC",

    # --- Scrollbar ---
    scrollbar_background="#1E1E1E",
    scrollbar_handle="#424242",
    scrollbar_handle_hover="#4F4F4F",

    # --- Status Bar ---
    statusbar_background="#007ACC",
    statusbar_text="#FFFFFF",
)
