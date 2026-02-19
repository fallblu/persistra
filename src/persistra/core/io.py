"""
src/persistra/core/io.py

Handles reading and writing .persistra archive files (ZIP-based).
"""
from __future__ import annotations

import io
import json
import pickle
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import numpy as np
import pandas as pd

from persistra.core.objects import DataWrapper
from persistra.core.project import Node, NodeState, Operation, Project, Socket


def get_app_version() -> str:
    """Return the current Persistra version string."""
    try:
        from importlib.metadata import version

        return version("persistra")
    except Exception:
        return "0.2.0"


# ---------------------------------------------------------------------------
# Operation class lookup helper
# ---------------------------------------------------------------------------

def _resolve_operation_class(qualified_name: str) -> Type[Operation]:
    """Resolve an operation class from its fully-qualified module path.

    Falls back to the REGISTRY when the qualified path cannot be
    imported (e.g. user shortened it to the class name only).
    """
    # Try direct import first
    parts = qualified_name.rsplit(".", 1)
    if len(parts) == 2:
        module_path, class_name = parts
        try:
            import importlib

            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)
        except (ImportError, AttributeError):
            pass

    # Fallback: lookup in REGISTRY by class name
    from persistra.operations import REGISTRY

    class_name = parts[-1]
    if REGISTRY.get(class_name) is not None:
        return REGISTRY.get(class_name)

    raise ImportError(f"Cannot resolve operation class: {qualified_name}")


# ---------------------------------------------------------------------------
# Cache serialization helpers
# ---------------------------------------------------------------------------

def _serialize_cache(cached_outputs: Dict[str, Any]) -> bytes:
    """Serialize a node's cached outputs to bytes.

    Strategy:
    - numpy arrays → npz format
    - pandas DataFrame/Series → parquet format
    - DataWrapper → recursively serialize inner data, then pickle the wrapper
    - everything else → pickle fallback
    """
    buf = io.BytesIO()
    # We store a small JSON header indicating the format for each key,
    # followed by the binary blobs, all packed into a single zip.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as inner:
        manifest: Dict[str, str] = {}
        for key, value in cached_outputs.items():
            raw_value = value.data if isinstance(value, DataWrapper) else value
            if isinstance(raw_value, np.ndarray):
                arr_buf = io.BytesIO()
                np.savez_compressed(arr_buf, data=raw_value)
                inner.writestr(f"{key}.npz", arr_buf.getvalue())
                manifest[key] = "npz"
            elif isinstance(raw_value, (pd.DataFrame, pd.Series)):
                df = raw_value if isinstance(raw_value, pd.DataFrame) else raw_value.to_frame()
                if _has_parquet_engine():
                    pq_buf = io.BytesIO()
                    df.to_parquet(pq_buf)
                    inner.writestr(f"{key}.parquet", pq_buf.getvalue())
                    manifest[key] = "parquet"
                else:
                    inner.writestr(f"{key}.pkl", pickle.dumps(df))
                    manifest[key] = "pkl"
            else:
                inner.writestr(f"{key}.pkl", pickle.dumps(raw_value))
                manifest[key] = "pkl"

            # Also pickle the wrapper class name so we can reconstruct
            if isinstance(value, DataWrapper):
                manifest[f"{key}.__wrapper__"] = (
                    f"{type(value).__module__}.{type(value).__qualname__}"
                )
        inner.writestr("_manifest.json", json.dumps(manifest))
    return buf.getvalue()


def _deserialize_cache(data: bytes) -> Dict[str, Any]:
    """Restore cached outputs from bytes produced by ``_serialize_cache``."""
    buf = io.BytesIO(data)
    result: Dict[str, Any] = {}
    with zipfile.ZipFile(buf, "r") as inner:
        manifest: Dict[str, str] = json.loads(inner.read("_manifest.json"))
        for key, fmt in manifest.items():
            if key.endswith(".__wrapper__"):
                continue
            if fmt == "npz":
                arr_buf = io.BytesIO(inner.read(f"{key}.npz"))
                result[key] = np.load(arr_buf, allow_pickle=False)["data"]
            elif fmt == "parquet":
                pq_buf = io.BytesIO(inner.read(f"{key}.parquet"))
                result[key] = pd.read_parquet(pq_buf)
            elif fmt == "pkl":
                # Only deserializing data we serialized ourselves from user projects
                result[key] = pickle.loads(inner.read(f"{key}.pkl"))  # noqa: S301
            # Re-wrap in DataWrapper if we recorded the wrapper class
            wrapper_key = f"{key}.__wrapper__"
            if wrapper_key in manifest and key in result:
                wrapper_cls = _resolve_wrapper_class(manifest[wrapper_key])
                if wrapper_cls is not None:
                    try:
                        result[key] = wrapper_cls(result[key])
                    except Exception:
                        # If reconstruction fails, keep the raw value
                        pass
    return result


def _resolve_wrapper_class(qualified_name: str) -> Optional[Type[DataWrapper]]:
    """Resolve a DataWrapper subclass from its qualified name."""
    parts = qualified_name.rsplit(".", 1)
    if len(parts) == 2:
        module_path, class_name = parts
        try:
            import importlib

            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            if isinstance(cls, type) and issubclass(cls, DataWrapper):
                return cls
        except (ImportError, AttributeError):
            pass
    return None


def _has_parquet_engine() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import fastparquet  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# ProjectSerializer — .persistra archive format
# ---------------------------------------------------------------------------

class ProjectSerializer:
    """Handles reading and writing .persistra archive files."""

    FORMAT_VERSION = "1.0"

    # -- public API --------------------------------------------------------

    def save(self, project: Project, filepath: Path) -> None:
        """Serialize the project to a .persistra archive."""
        filepath = Path(filepath)
        with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Write manifest
            manifest = {
                "format_version": self.FORMAT_VERSION,
                "persistra_version": get_app_version(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # 2. Serialize graph topology
            graph_data = self._serialize_graph(project)
            zf.writestr("graph.json", json.dumps(graph_data, indent=2))

            # 3. Serialize caches
            for node in project.nodes:
                if node._cached_outputs:
                    cache_bytes = _serialize_cache(node._cached_outputs)
                    zf.writestr(f"cache/{node.id}.bin", cache_bytes)

    def load(self, filepath: Path) -> Project:
        """Deserialize a project from a .persistra archive."""
        filepath = Path(filepath)
        with zipfile.ZipFile(filepath, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            graph_data = json.loads(zf.read("graph.json"))
            project = self._deserialize_graph(graph_data)

            # Restore caches
            for node in project.nodes:
                cache_path = f"cache/{node.id}.bin"
                if cache_path in zf.namelist():
                    try:
                        node._cached_outputs = _deserialize_cache(zf.read(cache_path))
                        node._is_dirty = False
                        node.state = NodeState.VALID
                    except Exception:
                        # Cache corrupted — mark dirty so node recomputes
                        node._is_dirty = True
                        node.state = NodeState.DIRTY

            return project

    # -- graph serialization -----------------------------------------------

    def _serialize_graph(self, project: Project) -> dict:
        """Convert the project graph to the graph.json dict."""
        nodes_data: List[dict] = []
        for node in project.nodes:
            op = node.operation
            op_qualified = f"{type(op).__module__}.{type(op).__qualname__}"
            nodes_data.append(
                {
                    "id": node.id,
                    "operation": op_qualified,
                    "position": list(node.position),
                    "parameters": {p.name: p.value for p in node.parameters},
                    "state": node.state.value,
                }
            )

        connections_data: List[dict] = []
        seen_connections: set = set()
        for node in project.nodes:
            for out_sock in node.output_sockets:
                for connected_input in out_sock.connections:
                    conn_key = (out_sock.node.id, out_sock.name,
                                connected_input.node.id, connected_input.name)
                    if conn_key not in seen_connections:
                        seen_connections.add(conn_key)
                        connections_data.append(
                            {
                                "source_node": out_sock.node.id,
                                "source_socket": out_sock.name,
                                "target_node": connected_input.node.id,
                                "target_socket": connected_input.name,
                            }
                        )

        settings = {
            "auto_compute": project.auto_compute,
            "autosave_interval_minutes": getattr(project, "autosave_interval_minutes", 5),
        }

        return {
            "version": self.FORMAT_VERSION,
            "nodes": nodes_data,
            "connections": connections_data,
            "settings": settings,
        }

    def _deserialize_graph(self, graph_data: dict) -> Project:
        """Reconstruct a Project from a graph.json dict."""
        project = Project()

        # Build nodes
        node_id_map: Dict[str, Node] = {}
        for node_data in graph_data.get("nodes", []):
            op_class = _resolve_operation_class(node_data["operation"])
            position = tuple(node_data.get("position", (0, 0)))
            node = project.add_node(op_class, position=position)

            # Override the auto-generated UUID with the saved one
            node.id = node_data["id"]

            # Restore parameter values
            saved_params = node_data.get("parameters", {})
            for param in node.parameters:
                if param.name in saved_params:
                    param.value = saved_params[param.name]

            # Restore state (default to DIRTY so nodes recompute if no cache)
            state_str = node_data.get("state", "dirty")
            try:
                node.state = NodeState(state_str)
            except ValueError:
                node.state = NodeState.DIRTY
            node._is_dirty = True  # Will be set to False when cache is loaded

            node_id_map[node.id] = node

        # Build connections
        for conn in graph_data.get("connections", []):
            src_node = node_id_map.get(conn["source_node"])
            tgt_node = node_id_map.get(conn["target_node"])
            if src_node and tgt_node:
                try:
                    project.connect(
                        src_node,
                        conn["source_socket"],
                        tgt_node,
                        conn["target_socket"],
                    )
                except (KeyError, TypeError, ValueError):
                    # Skip connections that can't be restored (e.g. schema change)
                    pass

        # Restore settings
        settings = graph_data.get("settings", {})
        project.auto_compute = settings.get("auto_compute", False)
        project.autosave_interval_minutes = settings.get("autosave_interval_minutes", 5)

        return project


