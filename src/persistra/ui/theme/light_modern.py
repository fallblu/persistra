"""VS Code Light Modern theme token values."""

from persistra.ui.theme.tokens import ThemeTokens

LIGHT_MODERN = ThemeTokens(
    # --- Global ---
    name="light",
    foreground="#3B3B3B",
    foreground_secondary="#6E6E6E",
    background="#FFFFFF",
    background_secondary="#F3F3F3",
    background_tertiary="#E8E8E8",
    border="#CECECE",
    border_focus="#005FB8",

    # --- Accent & Semantic ---
    accent="#005FB8",
    accent_hover="#0070D1",
    accent_foreground="#FFFFFF",
    error="#E51400",
    error_foreground="#FFFFFF",
    warning="#BF8803",
    success="#388A34",
    info="#005FB8",

    # --- Graph Editor ---
    editor_background="#F8F8F8",
    editor_grid="#E8E8E8",
    editor_grid_major="#D0D0D0",
    node_background="#FFFFFF",
    node_background_selected="#E8F0FE",
    node_border="#CECECE",
    node_border_selected="#005FB8",
    node_border_error="#E51400",
    node_text="#3B3B3B",
    socket_default="#6E6E6E",
    socket_hover="#E07000",
    wire_default="#999999",
    wire_draft="#E07000",
    wire_selected="#005FB8",

    # --- Node Category Header Colors ---
    category_io="#2E7D9E",
    category_preprocessing="#4E8A3E",
    category_tda="#7E4F9A",
    category_ml="#A0713A",
    category_viz="#A04040",
    category_utility="#5A5A6A",
    category_templates="#3E8A8A",
    category_plugins="#8A6A3E",

    # --- Panels ---
    panel_header_background="#E8E8E8",
    panel_header_foreground="#3B3B3B",

    # --- Node Browser ---
    browser_background="#F3F3F3",
    browser_alternate="#ECECEC",
    browser_selected="#CCE4F7",
    browser_hover="#E0E0E0",
    browser_text="#3B3B3B",

    # --- Context Panel ---
    context_background="#F3F3F3",
    context_header="#E8E8E8",
    context_input_background="#FFFFFF",
    context_input_border="#CECECE",

    # --- Viz Panel ---
    viz_background="#FFFFFF",
    viz_tab_active="#005FB8",
    viz_tab_inactive="#E8E8E8",

    # --- Log View ---
    log_background="#FFFFFF",
    log_error="#E51400",
    log_warning="#BF8803",
    log_info="#3B3B3B",
    log_debug="#999999",

    # --- Toolbar & Menu ---
    toolbar_background="#F3F3F3",
    toolbar_separator="#CECECE",
    menu_background="#F3F3F3",
    menu_hover="#CCE4F7",
    menu_text="#3B3B3B",

    # --- Scrollbar ---
    scrollbar_background="#F3F3F3",
    scrollbar_handle="#C1C1C1",
    scrollbar_handle_hover="#A0A0A0",

    # --- Status Bar ---
    statusbar_background="#005FB8",
    statusbar_text="#FFFFFF",
)
