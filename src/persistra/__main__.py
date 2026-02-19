import sys

from PySide6.QtWidgets import QApplication

from persistra.core.logging import setup_logging
from persistra.plugins.loader import load_plugins
from persistra.ui.main_window import MainWindow
from persistra.ui.theme import ThemeManager


def main():
    setup_logging()

    app = QApplication(sys.argv)

    # Load user plugins before showing any windows
    load_plugins()

    # Apply the saved (or default) theme before showing any windows
    ThemeManager().apply()

    window = MainWindow()
    window.show()

    app.exec()

if __name__ == "__main__":
    main()
