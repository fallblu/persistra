"""
src/persistra/plugins/loader.py

Discovers and loads user plugins from ``~/.persistra/plugins/``.
Each plugin file is expected to import from ``persistra`` and use the
``@REGISTRY.register`` decorator to register custom operations.
"""
import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path.home() / ".persistra" / "plugins"


def load_plugins():
    """Discover and load all plugin files from *PLUGIN_DIR*."""
    if not PLUGIN_DIR.exists():
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        return

    for plugin_path in sorted(PLUGIN_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(
                f"persistra_plugin_{plugin_path.stem}", plugin_path
            )
            if spec is None or spec.loader is None:
                logger.warning("Could not create module spec for plugin: %s", plugin_path.name)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.info("Loaded plugin: %s", plugin_path.name)
        except Exception:
            logger.exception("Failed to load plugin: %s", plugin_path.name)
