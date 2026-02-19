"""
src/persistra/ui/dialogs/export_figure.py

Dialog for exporting figures (PNG, SVG, PDF) from visualization nodes.

- Triggered from File → Export Figure, or right-click on a visualization node.
- Allows selecting format, resolution (DPI for raster), and output path.
- Uses matplotlib.figure.Figure.savefig() for Matplotlib figures.
- For pyqtgraph 3D views, uses QWidget.grab() to capture a pixmap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import matplotlib.figure


class ExportFigureDialog(QDialog):
    """Dialog for exporting a Matplotlib figure to disk.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The figure to export.
    parent : QWidget, optional
        Parent widget.
    """

    _FORMAT_FILTERS = {
        "PNG": "PNG Image (*.png)",
        "SVG": "SVG Vector (*.svg)",
        "PDF": "PDF Document (*.pdf)",
    }

    def __init__(
        self,
        figure: Optional[matplotlib.figure.Figure] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Figure")
        self.setMinimumWidth(420)

        self._figure = figure

        # --- widgets ---
        self._format_combo = QComboBox()
        self._format_combo.addItems(list(self._FORMAT_FILTERS.keys()))

        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 1200)
        self._dpi_spin.setValue(150)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select output path…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(self._browse_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._do_export)
        buttons.rejected.connect(self.reject)

        # --- layout ---
        form = QFormLayout()
        form.addRow("Format:", self._format_combo)
        form.addRow("DPI (raster):", self._dpi_spin)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(path_row)
        layout.addWidget(buttons)

    # -- accessors ---------------------------------------------------------

    @property
    def selected_format(self) -> str:
        return self._format_combo.currentText().lower()

    @property
    def selected_dpi(self) -> int:
        return self._dpi_spin.value()

    @property
    def selected_path(self) -> str:
        return self._path_edit.text()

    # -- slots -------------------------------------------------------------

    def _browse(self) -> None:
        fmt = self._format_combo.currentText()
        file_filter = self._FORMAT_FILTERS.get(fmt, "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(self, "Export Figure", "", file_filter)
        if path:
            self._path_edit.setText(path)

    def _do_export(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Export Figure", "Please select an output path.")
            return
        try:
            export_figure(self._figure, Path(path), self.selected_format, self.selected_dpi)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))


# ---------------------------------------------------------------------------
# Standalone export helper (usable without the dialog)
# ---------------------------------------------------------------------------

def export_figure(
    figure: Union[matplotlib.figure.Figure, None],
    filepath: Path,
    fmt: str = "png",
    dpi: int = 150,
    widget: Optional[QWidget] = None,
) -> None:
    """Export a figure to disk.

    Parameters
    ----------
    figure : matplotlib.figure.Figure or None
        Matplotlib figure. If *None*, *widget* must be provided (pyqtgraph fallback).
    filepath : Path
        Destination file path.
    fmt : str
        One of ``"png"``, ``"svg"``, ``"pdf"``.
    dpi : int
        Resolution for raster formats.
    widget : QWidget, optional
        Fallback: grab a pixmap from a Qt widget (for pyqtgraph 3D views).
    """
    filepath = Path(filepath)
    if figure is not None:
        figure.savefig(str(filepath), format=fmt, dpi=dpi, bbox_inches="tight")
    elif widget is not None:
        pixmap = widget.grab()
        pixmap.save(str(filepath), fmt.upper())
    else:
        raise ValueError("Either a Matplotlib figure or a QWidget must be provided.")
