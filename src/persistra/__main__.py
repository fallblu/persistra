import sys

from PyQt6.QtWidgets import QApplication

from persistra.ui.MainWindow import MainWindow

def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()

if __name__ == "__main__":
    main()
