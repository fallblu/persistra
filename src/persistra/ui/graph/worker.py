from PyQt6.QtCore import QThread, pyqtSignal
import traceback

class Worker(QThread):
    """
    Background thread to execute node computation.
    Ref: README.md Section 2.2 (Execution Flow)
    """
    finished = pyqtSignal(object) # Emits the result (or None on failure)
    error = pyqtSignal(str)       # Emits error message

    def __init__(self, node):
        super().__init__()
        self.node = node

    def run(self):
        try:
            # Recursive pull: This triggers computation of upstream nodes if needed
            result = self.node.compute()
            self.finished.emit(result)
        except Exception as e:
            # Capture full traceback for debugging
            tb = traceback.format_exc()
            self.error.emit(f"Error computing {self.node}:\n{tb}")
