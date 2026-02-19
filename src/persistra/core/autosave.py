"""
src/persistra/core/autosave.py

QTimer-based autosave service for Persistra projects.

- Saves to a temporary ``.persistra.autosave`` file alongside the current
  project file.
- On startup, if an autosave file exists and is newer than the main file,
  the caller should prompt the user to recover.
- Autosave is disabled if no project file has been saved yet (untitled).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer, Signal

if TYPE_CHECKING:
    from persistra.core.project import Project


class AutosaveService(QObject):
    """Periodically saves the current project to a sidecar autosave file.

    Parameters
    ----------
    parent : QObject, optional
        Qt parent for the timer.
    """

    # Emitted when an autosave completes successfully.
    autosave_completed = Signal(str)
    # Emitted when an autosave fails.
    autosave_failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._do_autosave)
        self._project: Optional[Project] = None
        self._project_path: Optional[Path] = None
        self._interval_ms: int = 5 * 60 * 1000  # default 5 minutes

    # -- configuration -----------------------------------------------------

    def set_project(self, project: Project, filepath: Optional[Path] = None) -> None:
        """Bind a project and its on-disk path to the autosave service."""
        self._project = project
        self._project_path = Path(filepath) if filepath else None

    def set_interval_minutes(self, minutes: int) -> None:
        """Change the autosave interval (in minutes)."""
        self._interval_ms = max(1, minutes) * 60 * 1000
        if self._timer.isActive():
            self._timer.start(self._interval_ms)

    # -- start / stop ------------------------------------------------------

    def start(self) -> None:
        """Begin periodic autosaving (no-op if no project path is set)."""
        if self._project_path is None:
            return
        self._timer.start(self._interval_ms)

    def stop(self) -> None:
        """Stop the autosave timer."""
        self._timer.stop()

    @property
    def is_active(self) -> bool:
        return self._timer.isActive()

    # -- autosave logic ----------------------------------------------------

    @staticmethod
    def autosave_path_for(project_path: Path) -> Path:
        """Return the sidecar autosave path for a given project file."""
        return project_path.with_suffix(project_path.suffix + ".autosave")

    @staticmethod
    def has_autosave(project_path: Path) -> bool:
        """Check whether an autosave file exists and is newer than the project."""
        auto_path = AutosaveService.autosave_path_for(project_path)
        if not auto_path.exists():
            return False
        if not project_path.exists():
            return True
        return auto_path.stat().st_mtime > project_path.stat().st_mtime

    @staticmethod
    def remove_autosave(project_path: Path) -> None:
        """Delete the autosave sidecar if it exists."""
        auto_path = AutosaveService.autosave_path_for(project_path)
        if auto_path.exists():
            auto_path.unlink()

    def _do_autosave(self) -> None:
        """Perform a single autosave cycle."""
        if self._project is None or self._project_path is None:
            return
        auto_path = self.autosave_path_for(self._project_path)
        try:
            from persistra.core.io import ProjectSerializer

            ProjectSerializer().save(self._project, auto_path)
            self.autosave_completed.emit(str(auto_path))
        except Exception as exc:
            self.autosave_failed.emit(str(exc))
