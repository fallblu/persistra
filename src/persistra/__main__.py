import os

os.environ["QT_API"] = "pyside6"

import sys

from PySide6.QtWidgets import QApplication

from persistra.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()

if __name__ == "__main__":
    main()
