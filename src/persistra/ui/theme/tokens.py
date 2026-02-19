"""
Theme token definitions for the Persistra UI.

Defines a ThemeTokens dataclass with named colors for every UI element.
Each theme (dark/light) provides a concrete instance of ThemeTokens.
"""

from dataclasses import dataclass


@dataclass
class ThemeTokens:
    """Complete set of color and style tokens for a Persistra theme."""

    # --- Global ---
    name: str                          # "dark" or "light"
    foreground: str                    # Primary text color
    foreground_secondary: str          # Secondary/muted text
    background: str                    # Main window background
    background_secondary: str          # Panel/widget background
    background_tertiary: str           # Nested/inset areas
    border: str                        # Default border color
    border_focus: str                  # Focused widget border

    # --- Accent & Semantic ---
    accent: str                        # Primary accent (selection, highlights)
    accent_hover: str                  # Accent on hover
    accent_foreground: str             # Text on accent backgrounds
    error: str                         # Error indicators
    error_foreground: str              # Text on error backgrounds
    warning: str                       # Warning indicators
    success: str                       # Success indicators
    info: str                          # Informational indicators

    # --- Graph Editor ---
    editor_background: str             # Canvas background
    editor_grid: str                   # Fine grid lines
    editor_grid_major: str             # Major grid lines
    node_background: str               # Node body fill
    node_background_selected: str      # Node body when selected
    node_border: str                   # Node border (default)
    node_border_selected: str          # Node border (selected)
    node_border_error: str             # Node border (error state)
    node_text: str                     # Node title and label text
    socket_default: str                # Socket circle fill
    socket_hover: str                  # Socket circle on hover
    wire_default: str                  # Wire color
    wire_draft: str                    # Draft/temporary wire color
    wire_selected: str                 # Wire color when connected nodes selected

    # --- Node Category Header Colors ---
    category_io: str                   # Input / Output
    category_preprocessing: str        # Preprocessing
    category_tda: str                  # TDA
    category_ml: str                   # Machine Learning
    category_viz: str                  # Visualization
    category_utility: str              # Utility
    category_templates: str            # Templates
    category_plugins: str              # Plugins

    # --- Panels ---
    panel_header_background: str       # Panel header bar
    panel_header_foreground: str       # Panel header text

    # --- Node Browser ---
    browser_background: str            # Tree background
    browser_alternate: str             # Alternating row color
    browser_selected: str              # Selected item
    browser_hover: str                 # Hovered item
    browser_text: str                  # Item text

    # --- Context Panel ---
    context_background: str            # Context panel background
    context_header: str                # Header bar background
    context_input_background: str      # Input field backgrounds (spinbox, lineedit)
    context_input_border: str          # Input field borders

    # --- Viz Panel ---
    viz_background: str                # Viz panel background
    viz_tab_active: str                # Active tab indicator
    viz_tab_inactive: str              # Inactive tab background

    # --- Log View ---
    log_background: str                # Log text area background
    log_error: str                     # ERROR level text color
    log_warning: str                   # WARNING level text color
    log_info: str                      # INFO level text color
    log_debug: str                     # DEBUG level text color

    # --- Toolbar & Menu ---
    toolbar_background: str            # Toolbar background
    toolbar_separator: str             # Toolbar separator line
    menu_background: str               # Menu dropdown background
    menu_hover: str                    # Menu item hover
    menu_text: str                     # Menu text

    # --- Scrollbar ---
    scrollbar_background: str          # Scrollbar track
    scrollbar_handle: str              # Scrollbar thumb
    scrollbar_handle_hover: str        # Scrollbar thumb on hover

    # --- Status Bar ---
    statusbar_background: str          # Status bar background
    statusbar_text: str                # Status bar text
