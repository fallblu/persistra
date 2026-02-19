import sys

from PySide6.QtWidgets import QApplication

from persistra.ui.main_window import MainWindow
from persistra.ui.theme import ThemeManager


def main():
    app = QApplication(sys.argv)

    # Apply the saved (or default) theme before showing any windows
    ThemeManager().apply()

    window = MainWindow()
    window.show()

    app.exec()

if __name__ == "__main__":
    main()
