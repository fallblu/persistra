"""
Theme engine for Persistra.

Provides a singleton ThemeManager that holds the current theme,
emits a theme_changed signal when toggled, and applies QSS globally.
Stores preference in ~/.persistra/settings.json.
"""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from persistra.ui.theme.dark_modern import DARK_MODERN
from persistra.ui.theme.light_modern import LIGHT_MODERN
from persistra.ui.theme.stylesheets import generate_stylesheet
from persistra.ui.theme.tokens import ThemeTokens

SETTINGS_PATH = Path.home() / ".persistra" / "settings.json"

THEMES = {
    "dark": DARK_MODERN,
    "light": LIGHT_MODERN,
}


class ThemeManager(QObject):
    """
    Singleton manager for application theming.
    Emits ``theme_changed`` when the theme is toggled so that custom-painted
    widgets (e.g., NodeItem, GraphScene) can refresh their colors.
    """

    theme_changed = Signal(str)  # Emits the new theme name

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        super().__init__()
        self._initialized = True
        self.current_theme = self._load_preference()
        self.current_tokens: ThemeTokens = THEMES[self.current_theme]

    def apply(self):
        """Apply the current theme's stylesheet to the entire application."""
        app = QApplication.instance()
        if app:
            stylesheet = generate_stylesheet(self.current_tokens)
            app.setStyleSheet(stylesheet)

    def toggle(self):
        """Switch between dark and light themes."""
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"

        self.current_tokens = THEMES[self.current_theme]
        self.apply()
        self._save_preference()
        self.theme_changed.emit(self.current_theme)

    def get_category_color(self, category: str) -> str:
        """Return the header color for a given operation category."""
        mapping = {
            "Input / Output": self.current_tokens.category_io,
            "Preprocessing": self.current_tokens.category_preprocessing,
            "TDA": self.current_tokens.category_tda,
            "Machine Learning": self.current_tokens.category_ml,
            "Visualization": self.current_tokens.category_viz,
            "Utility": self.current_tokens.category_utility,
            "Templates": self.current_tokens.category_templates,
            "Plugins": self.current_tokens.category_plugins,
        }
        return mapping.get(category, self.current_tokens.category_utility)

    def _load_preference(self) -> str:
        """Load saved theme preference, defaulting to 'dark'."""
        try:
            if SETTINGS_PATH.exists():
                settings = json.loads(SETTINGS_PATH.read_text())
                return settings.get("theme", "dark")
        except (json.JSONDecodeError, OSError):
            pass
        return "dark"

    def _save_preference(self):
        """Persist theme preference to settings file."""
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            settings = {}
            if SETTINGS_PATH.exists():
                settings = json.loads(SETTINGS_PATH.read_text())
            settings["theme"] = self.current_theme
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        except (json.JSONDecodeError, OSError):
            pass