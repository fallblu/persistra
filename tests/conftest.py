"""
tests/conftest.py

Shared pytest fixtures for Persistra's test suite.
"""
import pytest

from persistra.core.project import Project
from persistra.operations.io import DataGenerator
from persistra.operations.preprocessing import Normalize


@pytest.fixture
def empty_project():
    """Return a fresh, empty Project."""
    return Project()


@pytest.fixture
def sample_project():
    """Return a Project containing a DataGenerator → Normalize pipeline."""
    project = Project()
    gen_node = project.add_node(DataGenerator, position=(0, 0))
    norm_node = project.add_node(Normalize, position=(250, 0))
    project.connect(gen_node, "data", norm_node, "data")
    return project


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for the entire test session.

    pytest-qt's built-in ``qapp`` fixture does the same thing, so this is
    intentionally named the same to integrate with it.  If pytest-qt is
    available it will use its own fixture; otherwise this acts as a
    fallback so non-UI tests can still import Qt modules.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app