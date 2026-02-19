# Persistra — Comprehensive Improvement Plan

> **Version:** 1.0 — Initial Draft
> **Date:** 2026-02-19
> **Author:** GitHub Copilot, in collaboration with @fallblu

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phasing & Roadmap](#2-phasing--roadmap)
3. [Phase 0 — Foundation & Migration](#3-phase-0--foundation--migration)
4. [Phase 1 — Core Graph Model & Execution Engine](#4-phase-1--core-graph-model--execution-engine)
5. [Phase 2 — Project Persistence](#5-phase-2--project-persistence)
6. [Phase 3 — Operations Library Expansion](#6-phase-3--operations-library-expansion)
7. [Phase 4 — Visualization System](#7-phase-4--visualization-system)
8. [Phase 5 — UI/UX Overhaul & Theming](#8-phase-5--uiux-overhaul--theming)
9. [Phase 6 — Error Handling, Logging & Validation](#9-phase-6--error-handling-logging--validation)
10. [Phase 7 — Testing](#10-phase-7--testing)
11. [Phase 8 — Packaging, CI/CD & Documentation](#11-phase-8--packaging-cicd--documentation)
12. [Appendix A — Proposed Directory Structure](#appendix-a--proposed-directory-structure)
13. [Appendix B — Operations Catalog](#appendix-b--operations-catalog)
14. [Appendix C — Theme Color Tokens](#appendix-c--theme-color-tokens)

---

## 1. Executive Summary

Persistra is an early-prototype node-based visual analysis tool built with Python and Qt. The current codebase has a working proof-of-concept but requires a full overhaul to become a usable, extensible, general-purpose analysis application. This plan covers:

- **Migration** from mixed PyQt6/PySide6 imports to pure PySide6.
- **Core model** redesign with a richer type system, iterator loops, branch-level parallel execution, and composite (subgraph) nodes.
- **Project persistence** via a hybrid `.persistra` archive format (JSON graph + binary caches) with autosave.
- **Operations library** expansion from 5 operations to ~30+ across I/O, preprocessing, TDA, ML, and visualization categories, plus a plugin system.
- **Visualization** redesign with dedicated viz nodes (simple, composition, and 3D/interactive tiers), `Figure` as a first-class data type, and `pyqtgraph.opengl` for 3D.
- **UI/UX** overhaul including VS Code–inspired light/dark theming, a searchable Node Browser, menu bar, toolbar, and node editor enhancements (snap-to-grid, auto-layout, category coloring, copy-paste).
- **Error handling** with visual node indicators, a log tab with node filtering, graph validation, and structured Python logging.
- **Testing** with a full three-tier test suite (unit, integration, UI).
- **Infrastructure** with `pyproject.toml` updates, GitHub Actions CI/CD, and MkDocs documentation.

---

## 2. Phasing & Roadmap

The overhaul is organized into sequential phases. Some phases have internal parallelism, but each phase broadly depends on the ones before it.

| Phase | Name | Summary | Key Deliverables |
|-------|------|---------|-----------------|
| **0** | Foundation & Migration | PySide6 migration, project restructure, build config | All imports standardized; new directory layout; updated `pyproject.toml` |
| **1** | Core Model & Engine | Type system, execution engine, iterator nodes, composites | New `Socket`/`Node`/`Operation` model; task queue; loop construct; subgraph support |
| **2** | Project Persistence | Save/load, autosave, figure export | `.persistra` archive format; autosave service; export dialogs |
| **3** | Operations Library | ~30+ operations, registry redesign, plugin system | Full operations catalog; auto-registration; `~/.persistra/plugins/` loading |
| **4** | Visualization System | Viz nodes, 3D rendering, table inspector | Three-tier viz nodes; `pyqtgraph.opengl` integration; dynamic Viz Panel |
| **5** | UI/UX & Theming | Theme engine, menus, toolbar, node editor upgrades | VS Code light/dark themes; menu bar; toolbar; snap-to-grid; auto-layout |
| **6** | Error Handling & Logging | Log tab, node indicators, validation, `logging` | Structured logging; Log tab in Context Panel; Validate Graph action |
| **7** | Testing | Full test suite | Unit, integration, and UI tests with `pytest` and `pytest-qt` |
| **8** | Packaging & Docs | CI/CD, documentation site | GitHub Actions workflows; MkDocs site with API docs and user guide |

---

## 3. Phase 0 — Foundation & Migration

> **Status:** ✅ Complete

### 3.1 PySide6 Migration

**Problem:** `__main__.py` imports `PySide6` and sets `QT_API = "pyside6"`, but every other UI file imports from `PyQt6`. This is an incompatibility that would crash at runtime without a compatibility shim.

**Actions:**

1. ✅ **Replace all `PyQt6` imports** with their `PySide6` equivalents across every file in `src/persistra/ui/`.
   - *Done:* Replaced `from PyQt6.QtWidgets` → `from PySide6.QtWidgets`, `from PyQt6.QtCore` → `from PySide6.QtCore`, and `from PyQt6.QtGui` → `from PySide6.QtGui` in all 8 affected UI files.
2. ✅ **Signal/Slot syntax changes:**
   - `pyqtSignal` → `Signal` (from `PySide6.QtCore`)
   - `pyqtSlot` → `Slot` (from `PySide6.QtCore`)
   - *Done:* Replaced all `pyqtSignal` usages with `Signal` in `manager.py`, `scene.py`, and `worker.py`. No `pyqtSlot` usages were present.
3. ✅ **Enum access:** PySide6 generally uses the same enum patterns as PyQt6, but verify each usage. In particular, `QPainter.RenderHint.Antialiasing` and similar qualified enum paths should be tested.
   - *Done:* Verified all qualified enum paths (e.g., `QGraphicsView.DragMode.ScrollHandDrag`, `Qt.PenStyle.NoPen`, `QFont.Weight.Bold`, etc.) are compatible with PySide6. No changes were needed — PySide6 supports the same fully-qualified enum syntax.
4. ✅ **Remove the `QT_API` environment variable hack** from `__main__.py` — it's unnecessary when importing PySide6 directly.
   - *Done:* Removed `import os` and `os.environ["QT_API"] = "pyside6"` from `__main__.py`.
5. ✅ **Update `pyproject.toml`:** Replace `PyQt6` dependency with `PySide6>=6.6`.
   - *Already done prior to this phase:* `pyproject.toml` already specified `PySide6>=6.6`.

**Affected files:**
- `src/persistra/__main__.py`
- `src/persistra/ui/main_window.py`
- `src/persistra/ui/widgets/context_panel.py`
- `src/persistra/ui/widgets/node_browser.py`
- `src/persistra/ui/widgets/viz_panel.py`
- `src/persistra/ui/graph/items.py`
- `src/persistra/ui/graph/manager.py`
- `src/persistra/ui/graph/scene.py`
- `src/persistra/ui/graph/worker.py`

### 3.2 Project Restructure

Reorganize the source tree to accommodate the expanded scope. See [Appendix A](#appendix-a--proposed-directory-structure) for the full proposed layout.

Key changes:
- ✅ `src/persistra/core/` — Add `types.py`, `engine.py`, `composite.py`, `validation.py`.
  - *Already done prior to this phase:* These files already existed as placeholders.
- ✅ `src/persistra/operations/` — Split into subpackages by category: `io/`, `preprocessing/`, `tda/`, `ml/`, `viz/`.
  - *Done:* Migrated operation classes from flat files (`io.py`, `tda.py`, `viz.py`) into subpackage `__init__.py` files (`io/__init__.py`, `tda/__init__.py`, `viz/__init__.py`) and removed the old flat files. The `preprocessing/`, `ml/`, and `utility/` subpackages already existed as empty placeholders.
- ✅ `src/persistra/ui/` — Add `theme/`, `menus/`, and reorganize widget files.
  - *Already done prior to this phase:* `theme/`, `menus/`, and `dialogs/` directories already existed with `__init__.py` placeholders.
- ✅ `src/persistra/plugins/` — New module for plugin discovery and loading.
  - *Already done prior to this phase:* The `plugins/` directory already existed with `__init__.py`.
- ✅ `tests/` — New top-level test directory with `unit/`, `integration/`, `ui/` subdirectories.
  - *Done:* Created `tests/unit/`, `tests/integration/`, `tests/ui/` directories with `__init__.py` files. Added initial `test_phase0.py` in `tests/unit/`.
- ✅ `docs/` — New top-level directory for MkDocs.
  - *Done:* Created `docs/getting-started/`, `docs/user-guide/`, `docs/operations/`, `docs/developer-guide/`, `docs/api/` directories with `.gitkeep` files per the Appendix A layout.

### 3.3 Build Configuration

✅ Update `pyproject.toml`:

*Already done prior to this phase:* `pyproject.toml` already matched the target configuration exactly.

```toml
[build-system]
requires = ["setuptools>=68.0", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "persistra"
version = "0.2.0"  # Overhaul version
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.6",
    "numpy>=1.24",
    "pandas>=2.0",
    "matplotlib>=3.7",
    "pyqtgraph>=0.13",
]

[project.optional-dependencies]
tda = ["ripser", "persim", "giotto-tda", "gudhi", "scikit-tda"]
ml = ["scikit-learn"]
dev = ["pytest", "pytest-qt", "pytest-cov", "ruff", "black", "mypy", "mkdocs", "mkdocstrings[python]"]

[project.scripts]
persistra = "persistra.__main__:main"

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "UP"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
```

### 3.4 Fix Existing Bugs

Before proceeding with new features, address known bugs in the current codebase:

1. ✅ **Registry key mismatch:** `OPERATIONS_REGISTRY` uses category names as keys (e.g., `"Input / Output"`), but `MainWindow` iterates `OPERATIONS_REGISTRY.keys()` and passes them to `NodeBrowser.add_operation()`. When the user drags a "category name" onto the canvas, `add_node()` looks it up as an operation name and fails. The registry must be restructured (see Phase 3).
   - *Done:* Restructured `OPERATIONS_REGISTRY` in `src/persistra/operations/__init__.py` to use operation class names as keys (e.g., `"CSVLoader"`, `"SlidingWindow"`) mapped directly to operation classes. This allows `MainWindow` to iterate operation names correctly and `GraphManager.add_node()` to look them up successfully.
2. ✅ **Missing `update_visualization` method:** `MainWindow` connects `computation_finished` to `viz_panel.update_visualization`, but `VizPanel` has no such method. This would raise `AttributeError` at runtime.
   - *Done:* Added `update_visualization(self, node, result)` method to `VizPanel` in `src/persistra/ui/widgets/viz_panel.py`. The method resets views and delegates to `set_node()` for rendering.
3. ✅ **`ChoiceParam` attribute mismatch:** `ChoiceParam.__init__` stores `self.options`, but `ContextPanel._create_widget_for_param` reads `getattr(param, 'choices', [])`. This should read `options`.
   - *Done:* Changed `getattr(param, 'choices', [])` → `getattr(param, 'options', [])` in `src/persistra/ui/widgets/context_panel.py`.

---

## 4. Phase 1 — Core Graph Model & Execution Engine

> **Status:** ✅ Complete

### 4.1 Richer Type System

**File:** `src/persistra/core/types.py` (new)

#### 4.1.1 Design

> ✅ **Done:** Implemented `SocketType`, `ConcreteType`, `UnionType`, and `AnyType` in `src/persistra/core/types.py` exactly as specified. Each class includes `accepts()` for type compatibility checking, plus `__repr__` methods for debugging.

Replace the current simple `issubclass` check with a formal type descriptor system:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Type, Union


class SocketType:
    """Base class for all socket type descriptors."""

    def accepts(self, other: SocketType) -> bool:
        """Return True if data described by `other` can flow into a socket of this type."""
        raise NotImplementedError


class ConcreteType(SocketType):
    """Exact DataWrapper subclass, optionally with shape/dtype constraints."""

    def __init__(self, wrapper_cls: Type, *, dtype: Optional[str] = None,
                 shape: Optional[tuple] = None):
        self.wrapper_cls = wrapper_cls
        self.dtype = dtype      # e.g., "float64"
        self.shape = shape      # e.g., (None, 3) — None means "any size on that axis"

    def accepts(self, other: SocketType) -> bool:
        if isinstance(other, ConcreteType):
            if not issubclass(other.wrapper_cls, self.wrapper_cls):
                return False
            if self.dtype and other.dtype and self.dtype != other.dtype:
                return False
            if self.shape and other.shape:
                if len(self.shape) != len(other.shape):
                    return False
                for s_dim, o_dim in zip(self.shape, other.shape):
                    if s_dim is not None and s_dim != o_dim:
                        return False
            return True
        if isinstance(other, UnionType):
            return any(self.accepts(t) for t in other.types)
        if isinstance(other, AnyType):
            return True
        return False


class UnionType(SocketType):
    """Socket accepts any of several concrete types."""

    def __init__(self, *types: SocketType):
        self.types = types

    def accepts(self, other: SocketType) -> bool:
        return any(t.accepts(other) for t in self.types)


class AnyType(SocketType):
    """Socket accepts any DataWrapper."""

    def accepts(self, other: SocketType) -> bool:
        return True
```

#### 4.1.2 Runtime Validation

> ✅ **Done:** Added concrete `validate()` methods to `TimeSeries` (type check), `DistanceMatrix` (squareness assertion), and `PersistenceDiagram` (list type check) in `objects.py`. `Node.compute()` now calls `validate()` on every `DataWrapper` output after `Operation.execute()` returns, before caching.

Each `DataWrapper` subclass gains a `validate()` method that checks invariants (e.g., `DistanceMatrix` asserts squareness, `TimeSeries` checks for a datetime index). Validation is called automatically after `Operation.execute()` returns, before results are cached.

#### 4.1.3 Integration with Sockets

> ✅ **Done:** `Socket.__init__` now takes `socket_type: SocketType` and `required: bool` parameters. A backward-compatible `data_type` property is derived from `ConcreteType.wrapper_cls` for existing UI code. `connect_to()` uses `target.socket_type.accepts(source.socket_type)`. A `_socket_type_from_def()` helper transparently converts legacy dict definitions to the new system.

The `Socket` class is updated to store a `SocketType` instead of a raw `Type[DataWrapper]`:

```python
class Socket:
    def __init__(self, node, name, socket_type: SocketType, is_input: bool,
                 required: bool = True):
        self.socket_type = socket_type
        self.required = required
        # ... rest unchanged
```

Connection validation uses `target.socket_type.accepts(source.socket_type)`.

### 4.2 Execution Engine

**File:** `src/persistra/core/engine.py` (new)

#### 4.2.1 Branch-Level Parallel Execution

> ✅ **Done:** Implemented `ExecutionEngine`, `ExecutionPlanner`, `BranchTask`, and `ExecutionResult` in `src/persistra/core/engine.py`. Uses `threading.Thread` (pure Python) rather than `QThreadPool` to keep the engine Qt-independent. `ExecutionPlanner.topological_sort()` implements Kahn's algorithm; `identify_branches()` partitions sorted nodes by shared ancestry. The engine runs branches in parallel threads with configurable `max_workers`, falling back to sequential execution for single-branch graphs.

Replace the single `QThread` worker with a proper engine:

```
┌─────────────────────────────────────────────┐
│                ExecutionEngine               │
│                                              │
│  ┌─────────┐  ┌─────────────┐  ┌─────────┐  │
│  │ Planner │→ │  Task Queue  │→ │ Workers │  │
│  └─────────┘  └─────────────┘  └─────────┘  │
│                                              │
│  Planner: Topological sort → group into      │
│           independent branches → submit      │
│           branches as tasks                  │
│                                              │
│  Task Queue: QueuedBranch objects awaiting   │
│              execution                       │
│                                              │
│  Workers: QThreadPool with configurable      │
│           max workers (default: CPU count)   │
└─────────────────────────────────────────────┘
```

**Key classes:**

- **`ExecutionEngine`** — Owns a `QThreadPool`. Accepts a `Project` graph, plans execution, and dispatches work.
- **`ExecutionPlanner`** — Performs topological sort on the graph. Identifies independent branches (subgraphs with no shared dirty ancestors). Each branch becomes a `BranchTask`.
- **`BranchTask(QRunnable)`** — Executes a linear chain of nodes sequentially. Emits progress signals via a shared `QObject` signal relay (since `QRunnable` can't emit signals directly).
- **`ExecutionResult`** — Encapsulates success/failure, result data, timing info, and error tracebacks.

#### 4.2.2 Cancellation

> ✅ **Done:** `ExecutionEngine` owns a `threading.Event` (`_cancel_event`). `BranchTask.run()` checks the event before each node computation. `ExecutionEngine.cancel()` sets the event. `Operation.execute()` now accepts an optional `cancel_event` parameter for cooperative cancellation inside long-running computations.

Each `BranchTask` checks a shared `threading.Event` (`cancel_event`) between node computations. When the user clicks "Stop":

1. `ExecutionEngine.cancel()` sets the event.
2. Each running `BranchTask` checks the event before computing the next node in its chain.
3. If set, the task terminates early and reports a `CancelledError`.

For truly long-running single-node operations (e.g., Rips persistence on a large dataset), operations can optionally accept a `cancel_event` parameter and check it internally within their computation loops.

#### 4.2.3 Auto-Compute Toggle

> ✅ **Done:** Added `auto_compute: bool` attribute to `Project` (default `False`). UI integration (toolbar toggle, automatic re-run on parameter/connection changes) is deferred to Phase 5 (UI/UX).

- A global toggle in the toolbar (default: off).
- When enabled, any parameter change or upstream connection change triggers `ExecutionEngine.run(dirty_nodes_only=True)`.
- When disabled, computation only runs when the user clicks "Run" or presses a shortcut.
- Per-node override possible in the future but not in the initial overhaul.

### 4.3 Iterator / Loop Nodes

> ✅ **Done:** Implemented `IteratorNode` and `IteratorOperation` in `src/persistra/core/composite.py`.

**File:** `src/persistra/core/composite.py` (new, also handles subgraphs)

#### 4.3.1 Design: Iterator Node Pattern

> ✅ **Done:** `IteratorNode` wraps a `CompositeNode` body with `max_iter`, `tolerance`, and `mode` controls exposed as runtime parameters. Supports `"fixed_count"` and `"converge"` modes. Convergence is measured via `numpy.linalg.norm` on output deltas. The iteration loop invalidates the body, injects inputs via `_injected_inputs`, then re-computes. A static `_has_converged()` method handles delta checking.

A loop is represented by a special **`IteratorNode`** that wraps a subgraph:

```
┌─ IteratorNode ─────────────────────────────┐
│                                             │
│  [Input] ──► LoopBody (subgraph) ──► [Output]
│                  ▲          │               │
│                  └──────────┘               │
│              (feedback connection)           │
│                                             │
│  Parameters:                                │
│    - max_iterations: int                    │
│    - convergence_tolerance: float           │
│    - mode: "fixed_count" | "converge"       │
└─────────────────────────────────────────────┘
```

- The **loop body** is a self-contained subgraph (a `CompositeNode` — see §4.4).
- The iterator node has special **feedback sockets** that carry the previous iteration's output back to the loop body's input.
- Execution modes:
  - **Fixed count:** Run the body exactly N times.
  - **Convergence:** Run until the output delta (measured by a configurable metric) falls below a tolerance, or max iterations is reached.
- The rest of the outer graph remains a strict DAG. Cycles only exist *inside* the iterator construct, and the engine never recurses into them — the `IteratorNode.compute()` method handles the internal loop explicitly.

#### 4.3.2 Implementation Sketch

> ✅ **Done:** Full implementation follows the sketch below, with the addition of `_gather_inputs()` for upstream data collection, runtime parameter override reading, and proper `NodeState` transitions.

```python
class IteratorNode(Node):
    """A node that repeatedly executes an internal subgraph."""

    def __init__(self, body: CompositeNode, max_iter=100, tolerance=1e-6,
                 mode="fixed_count"):
        # The IteratorNode's inputs/outputs mirror the body's exposed sockets
        super().__init__(operation_cls=IteratorOperation)
        self.body = body
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.mode = mode

    def compute(self):
        # Gather external inputs
        external_inputs = self._gather_inputs()

        prev_output = None
        for i in range(self.max_iter):
            # Feed inputs (first iteration: external, subsequent: feedback)
            self.body.set_inputs(external_inputs if i == 0 else prev_output)
            self.body.invalidate_all()
            result = self.body.compute()

            if self.mode == "converge" and prev_output is not None:
                if self._has_converged(prev_output, result):
                    break
            prev_output = result

        self._cached_outputs = result
        self._is_dirty = False
        return self._cached_outputs
```

### 4.4 Composite / Subgraph Nodes

#### 4.4.1 Design

> ✅ **Done:** Implemented `CompositeNode` and `CompositeOperation` in `src/persistra/core/composite.py`. `CompositeNode` accepts a `sub_project`, `exposed_inputs`, `exposed_outputs`, and `exposed_params`. External sockets are built dynamically from the sub-graph's exposed definitions. `set_inputs()` injects data via `_injected_inputs` on internal nodes, and `compute()` executes the sub-graph and collects exposed outputs. `invalidate_all()` resets all internal nodes. Internal parameters are cloned with custom labels for external exposure.

A `CompositeNode` encapsulates a `Project` (sub-graph) and exposes selected sockets and parameters to the parent graph:

```python
class CompositeNode(Node):
    """A node that contains an internal sub-graph."""

    def __init__(self, sub_project: Project, exposed_inputs, exposed_outputs,
                 exposed_params):
        super().__init__(operation_cls=CompositeOperation)
        self.sub_project = sub_project
        # exposed_inputs: list of (internal_node, socket_name) tuples
        # exposed_outputs: list of (internal_node, socket_name) tuples
        # exposed_params: list of (internal_node, param_name, external_label) tuples
```

#### 4.4.2 Template Files

> ⏳ **Deferred:** Template file support (`.persistra-template` archives, `~/.persistra/templates/` loading, Node Browser integration) is deferred to Phase 2 (Project Persistence) and Phase 5 (UI/UX), as it depends on the archive serialization format and UI infrastructure.

- Templates are stored as `.persistra-template` files (same archive format as projects, but containing only the subgraph).
- Default location: `~/.persistra/templates/`.
- Templates appear in the Node Browser under a "Templates" category.
- The user can right-click a selection of nodes → "Create Template" to save.
- When loading a template, the user gets a `CompositeNode` with exposed parameters visible in the Context Panel.

### 4.5 Updated Operation Base Class

> ✅ **Done:** `Operation` in `project.py` now has `icon: Optional[str] = None` class attribute and `execute()` accepts `cancel_event: Optional[threading.Event] = None`. `SocketDef` dataclass added to `project.py`. Existing operations continue to work via `_socket_type_from_def()` which transparently converts legacy dict definitions. `inputs`/`outputs` accept both `list[SocketDef]` and `list[dict]`.

```python
class Operation:
    name: str = "Generic Operation"
    description: str = ""
    category: str = "General"
    icon: Optional[str] = None  # Path to icon file or built-in icon name

    def __init__(self):
        self.inputs: list[SocketDef] = []
        self.outputs: list[SocketDef] = []
        self.parameters: list[Parameter] = []

    def execute(self, inputs: dict[str, Any], params: dict[str, Any],
                cancel_event: Optional[threading.Event] = None) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class SocketDef:
    """Declarative socket definition used by Operation subclasses."""
    name: str
    socket_type: SocketType
    required: bool = True
    description: str = ""
```

### 4.6 Node State Machine

> ✅ **Done:** Added `NodeState` enum (IDLE, DIRTY, COMPUTING, VALID, ERROR, INVALID) to `project.py`. `Node` initializes in `IDLE`, transitions to `DIRTY` on `invalidate()`, to `COMPUTING` at the start of `compute()`, and then to `VALID` on success or `ERROR` on failure. The `_is_dirty` boolean is retained for backward compatibility but state transitions now use the enum.

Nodes transition through explicit states for UI rendering:

```
         ┌──────────┐
         │  IDLE     │  (clean, has cached output or no output yet)
         └────┬─────┘
              │ parameter change / upstream invalidation
              ▼
         ┌──────────┐
         │  DIRTY    │  (needs recomputation, grayed out in UI)
         └────┬─────┘
              │ engine starts computing
              ▼
         ┌──────────┐
         │ COMPUTING │  (spinner/animation in UI)
         └────┬─────┘
              │
       ┌──────┴───────┐
       ▼              ▼
  ┌────────┐    ┌─────────┐
  │  VALID │    │  ERROR  │  (red border in UI)
  └────────┘    └─────────┘
```

An additional state, **`INVALID`**, applies when required inputs are disconnected (grayed out, distinct from DIRTY).

---

## 5. Phase 2 — Project Persistence

### 5.1 Archive Format (`.persistra`)

A `.persistra` file is a ZIP archive with the following internal structure:

```
project.persistra (ZIP)
├── manifest.json        # Format version, creation date, Persistra version
├── graph.json           # Full graph topology, node positions, parameters
├── cache/               # Binary cached outputs (optional, for fast reload)
│   ├── <node-uuid>.npz
│   └── ...
└── templates/           # Embedded templates used by CompositeNodes
    └── ...
```

#### 5.1.1 `graph.json` Schema

```json
{
  "version": "1.0",
  "nodes": [
    {
      "id": "uuid-1",
      "operation": "persistra.operations.io.CSVLoader",
      "position": [120.0, 340.0],
      "parameters": {
        "filepath": "data.csv",
        "index_col": "0"
      },
      "state": "idle"
    }
  ],
  "connections": [
    {
      "source_node": "uuid-1",
      "source_socket": "data",
      "target_node": "uuid-2",
      "target_socket": "series"
    }
  ],
  "settings": {
    "auto_compute": false,
    "autosave_interval_minutes": 5
  }
}
```

#### 5.1.2 Cache Serialization

- Cached outputs are stored per-node as `.npz` (NumPy), `.parquet` (Pandas), or `.pkl` (generic fallback) files inside the `cache/` directory.
- On load, caches are restored and nodes are marked as VALID (skipping recomputation).
- Caches are optional — if missing or corrupted, nodes are marked DIRTY and will recompute on demand.

### 5.2 Save/Load Implementation

**File:** `src/persistra/core/io.py` (rewrite)

```python
import json
import zipfile
import tempfile
from pathlib import Path

class ProjectSerializer:
    """Handles reading and writing .persistra archive files."""

    FORMAT_VERSION = "1.0"

    def save(self, project: Project, filepath: Path):
        """Serialize the project to a .persistra archive."""
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. Write manifest
            manifest = {
                "format_version": self.FORMAT_VERSION,
                "persistra_version": get_app_version(),
                "created_at": datetime.utcnow().isoformat(),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # 2. Serialize graph topology
            graph_data = self._serialize_graph(project)
            zf.writestr("graph.json", json.dumps(graph_data, indent=2))

            # 3. Serialize caches
            for node in project.nodes:
                if node._cached_outputs:
                    cache_bytes = self._serialize_cache(node)
                    zf.writestr(f"cache/{node.id}.bin", cache_bytes)

    def load(self, filepath: Path) -> Project:
        """Deserialize a project from a .persistra archive."""
        with zipfile.ZipFile(filepath, 'r') as zf:
            manifest = json.loads(zf.read("manifest.json"))
            graph_data = json.loads(zf.read("graph.json"))
            project = self._deserialize_graph(graph_data)

            # Restore caches
            for node in project.nodes:
                cache_path = f"cache/{node.id}.bin"
                if cache_path in zf.namelist():
                    node._cached_outputs = self._deserialize_cache(
                        zf.read(cache_path)
                    )
                    node._is_dirty = False

            return project
```

### 5.3 Autosave Service

**File:** `src/persistra/core/autosave.py` (new)

- Uses a `QTimer` that fires at a configurable interval (default: 5 minutes, stored in project settings).
- Saves to a temporary `.persistra.autosave` file alongside the current project file.
- On startup, if an autosave file exists and is newer than the main file, prompt the user to recover.
- Autosave is disabled if no project file has been saved yet (untitled project).

### 5.4 Figure Export

**File:** `src/persistra/ui/dialogs/export_figure.py` (new)

- Triggered from File → Export Figure, or from a right-click on a visualization node.
- Dialog allows the user to select format (PNG, SVG, PDF), resolution (DPI for raster), and output path.
- Uses `matplotlib.figure.Figure.savefig()` for Matplotlib-based figures.
- For `pyqtgraph` 3D views, uses `QWidget.grab()` to capture a pixmap and save as PNG.

### 5.5 Recent Projects

- Recent project paths are stored in `~/.persistra/recent.json` (a simple JSON array of file paths).
- Maximum 10 entries, most recent first, pruned on load if files no longer exist.
- When no project is open, the Node Browser panel renders a `RecentProjectsList` widget (custom `QListWidget` subclass) showing project names, paths, and last-modified dates.
- Clicking an entry opens the project. A "New Project" button at the top creates a blank project and switches the browser to the operation tree.

---

## 6. Phase 3 — Operations Library Expansion

### 6.1 Registry Redesign

**File:** `src/persistra/operations/__init__.py` (rewrite)

Replace the current dict-of-lists with an auto-registration system:

```python
class OperationRegistry:
    """Central registry of all available operations."""

    def __init__(self):
        self._operations: dict[str, Type[Operation]] = {}

    def register(self, op_class: Type[Operation]):
        """Register an operation class. Uses op_class.name as the key."""
        if op_class.name in self._operations:
            raise ValueError(f"Duplicate operation name: {op_class.name}")
        self._operations[op_class.name] = op_class
        return op_class

    def get(self, name: str) -> Optional[Type[Operation]]:
        return self._operations.get(name)

    def all(self) -> dict[str, Type[Operation]]:
        return dict(self._operations)

    def by_category(self) -> dict[str, list[Type[Operation]]]:
        categories = {}
        for op in self._operations.values():
            categories.setdefault(op.category, []).append(op)
        return categories

    def search(self, query: str) -> list[Type[Operation]]:
        """Fuzzy search by name, description, and category."""
        query_lower = query.lower()
        results = []
        for op in self._operations.values():
            if (query_lower in op.name.lower() or
                query_lower in op.description.lower() or
                query_lower in op.category.lower()):
                results.append(op)
        return results


# Global singleton
REGISTRY = OperationRegistry()
```

Operations register themselves via a decorator:

```python
@REGISTRY.register
class CSVLoader(Operation):
    name = "CSV Loader"
    category = "Input / Output"
    # ...
```

### 6.2 Plugin System

**File:** `src/persistra/plugins/loader.py` (new)

- On startup, scan `~/.persistra/plugins/` for `.py` files.
- Each plugin file is expected to import from `persistra` and use the `@REGISTRY.register` decorator.
- Loading process:
  1. Validate file exists and is a `.py` file.
  2. Execute in a controlled namespace with `importlib.util.spec_from_file_location` / `module_from_spec`.
  3. Any operation classes decorated with `@REGISTRY.register` are automatically added to the registry.
  4. Log successes and failures.

```python
import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path.home() / ".persistra" / "plugins"

def load_plugins():
    """Discover and load all plugin files."""
    if not PLUGIN_DIR.exists():
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        return

    for plugin_path in sorted(PLUGIN_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(
                f"persistra_plugin_{plugin_path.stem}", plugin_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.info(f"Loaded plugin: {plugin_path.name}")
        except Exception:
            logger.exception(f"Failed to load plugin: {plugin_path.name}")
```

### 6.3 Operations Catalog

See [Appendix B](#appendix-b--operations-catalog) for the full list. Summary of new operations by category:

#### 6.3.1 Input / Output (3 new, 1 existing)

| Operation | Description |
|-----------|-------------|
| `CSV Loader` | *(existing)* Load CSV files |
| `Manual Data Entry` | Editable spreadsheet in the Viz Panel; outputs a DataFrame |
| `Data Generator` | Synthetic signals: sine, cosine, white noise, random walk, Brownian motion, statistical distributions, sphere sampling. Configurable via dropdown + parameters |
| `CSV Writer` | Export a DataFrame to a CSV file at a specified path |

#### 6.3.2 Preprocessing (7 new)

| Operation | Description |
|-----------|-------------|
| `Normalize` | Min-max or z-score normalization (dropdown) |
| `Differencing` | First or Nth-order differencing |
| `Returns` | Simple returns: `(x[t] - x[t-1]) / x[t-1]` |
| `Log Transform` | Element-wise natural or base-10 log |
| `Log Returns` | `log(x[t] / x[t-1])` |
| `Rolling Statistics` | Rolling mean, std, min, max, sum (configurable window + statistic) |
| `Python Expression` | User-supplied arbitrary Python code (see §6.3.8) |

#### 6.3.3 TDA (6 new, 2 existing)

| Operation | Description |
|-----------|-------------|
| `Sliding Window` | *(existing)* Takens' embedding |
| `Rips Persistence` | *(existing)* Vietoris-Rips complex via `ripser` |
| `Alpha Persistence` | Alpha complex persistence (via `gudhi`) |
| `Čech Persistence` | Čech complex persistence (via `gudhi`) |
| `Cubical Persistence` | Cubical complex persistence (via `gudhi`) |
| `Persistence Landscape` | Vectorization via landscapes (via `giotto-tda` or `scikit-tda`) |
| `Persistence Image` | Vectorization via persistence images |
| `Diagram Distance` | Wasserstein or Bottleneck distance between two diagrams (via `persim`) |

#### 6.3.4 Machine Learning (4 new)

| Operation | Description |
|-----------|-------------|
| `K-Means Clustering` | `sklearn.cluster.KMeans` with configurable k |
| `PCA` | `sklearn.decomposition.PCA` with configurable n_components |
| `Linear Regression` | `sklearn.linear_model.LinearRegression` — fit and predict |
| `Logistic Regression` | `sklearn.linear_model.LogisticRegression` — fit and predict |

#### 6.3.5 Visualization (8 new, 2 existing — see Phase 4 for details)

See [§7.2](#72-tier-1--simple-plot-nodes) through [§7.4](#74-tier-3--interactive--3d-nodes).

#### 6.3.6 Utility (2 new)

| Operation | Description |
|-----------|-------------|
| `Column Selector` | Picks specific columns from a DataFrame by name or index |
| `Merge / Join` | Joins two DataFrames on a key column or index |

#### 6.3.7 Export (1 new — beyond CSV Writer)

| Operation | Description |
|-----------|-------------|
| `Export Figure` | Takes a `Figure` wrapper and saves it to disk (PNG/SVG/PDF). Path and format as parameters. |

#### 6.3.8 Python Expression Node — Detail

**UI Integration:**
- When the Python Expression node is selected, the Viz Panel displays a simple code editor (a `QPlainTextEdit` with monospace font and basic syntax highlighting).
- The editor content is stored as a `StringParam` on the node.

**Execution Model:**
- The user writes a function body. The following variables are pre-injected into the namespace:
  - `inputs` — a dict of input socket values (unwrapped data).
  - `params` — a dict of parameter values.
  - `np` — NumPy.
  - `pd` — Pandas.
- The code must assign to a `result` variable or use `return` (if wrapped in a function).
- Full Python access — no sandboxing.

```python
class PythonExpression(Operation):
    name = "Python Expression"
    category = "Utility"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef("data", AnyType(), required=False)]
        self.outputs = [SocketDef("result", AnyType())]
        self.parameters = [
            StringParam("code", "Code", default="result = inputs.get('data')")
        ]

    def execute(self, inputs, params, cancel_event=None):
        code = params["code"]
        namespace = {"inputs": inputs, "params": params,
                     "np": np, "pd": pd, "result": None}
        exec(code, namespace)
        return {"result": namespace["result"]}
```

---

## 7. Phase 4 — Visualization System

### 7.1 `Figure` as a First-Class Data Type

**File:** Update `src/persistra/core/objects.py`

```python
class FigureWrapper(DataWrapper):
    """Wraps a Matplotlib Figure for display and downstream use."""
    def __init__(self, data: matplotlib.figure.Figure, metadata=None):
        super().__init__(data, metadata)

class InteractiveFigure(DataWrapper):
    """Wraps data for pyqtgraph/plotly interactive rendering."""
    def __init__(self, data: Any, renderer: str = "pyqtgraph", metadata=None):
        super().__init__(data, metadata)
        self.renderer = renderer  # "pyqtgraph" or "plotly"
```

Both types flow through sockets like any other data. Downstream nodes (e.g., `Export Figure`, `Subplot Grid`) can consume them.

### 7.2 Tier 1 — Simple Plot Nodes

Each node takes one data input and outputs a `FigureWrapper`.

| Node | Input Type | Parameters |
|------|-----------|------------|
| `Line Plot` | `TimeSeries` | Title, color, grid toggle |
| `Scatter Plot` | `DataFrame` (2+ columns) | X column, Y column, color, point size |
| `Histogram` | `TimeSeries` or numeric array | Bins, color, density toggle |
| `Persistence Diagram Plot` | `PersistenceDiagram` | Dimensions to show (H0, H1, …) |
| `Barcode Plot` | `PersistenceDiagram` | Dimensions to show |
| `Heatmap` | 2D array / `DistanceMatrix` | Colormap, annotation toggle |

### 7.3 Tier 2 — Composition Nodes

#### `Overlay Plot`

- **Inputs:** Variable-length list of `FigureWrapper` inputs (start with 2, allow adding more via a "+" button on the node or a parameter).
- **Parameters:** Shared title, legend toggle, shared axis labels.
- **Logic:** Extracts plot data from each input figure's axes and re-draws them on shared axes in a new figure. (Alternatively, uses a simpler approach: each input provides raw data + style, and the overlay node creates the combined plot from scratch.)

**Implementation consideration:** Extracting plot data from an existing Matplotlib figure is brittle. A cleaner approach: Tier 1 nodes output both a `FigureWrapper` *and* a structured `PlotData` object (containing the raw data + style metadata). Composition nodes consume `PlotData` instead of `FigureWrapper`, enabling clean re-rendering.

```python
@dataclass
class PlotData:
    """Structured plot data for composition."""
    x: np.ndarray
    y: np.ndarray
    plot_type: str  # "line", "scatter", "bar", etc.
    style: dict     # color, linewidth, marker, label, etc.
```

Tier 1 nodes would then have two outputs:
- `plot` → `FigureWrapper` (for direct display)
- `plot_data` → `PlotData` (for composition)

#### `Subplot Grid`

- **Inputs:** N `FigureWrapper` inputs.
- **Parameters:** Rows, columns, shared axes toggle, figure size.
- **Logic:** Creates a new figure with `plt.subplots(rows, cols)` and embeds each input figure into a subplot.

### 7.4 Tier 3 — Interactive / 3D Nodes

#### `3D Scatter`

- **Input:** `PointCloud` (N×3 array) or any DataFrame with 3+ numeric columns.
- **Output:** `InteractiveFigure` with `renderer="pyqtgraph"`.
- **Parameters:** X/Y/Z column selection (if DataFrame), point size, color, colormap (if 4th column for color).
- **Rendering:** The Viz Panel detects `InteractiveFigure` with `renderer="pyqtgraph"` and creates a `pyqtgraph.opengl.GLViewWidget` with a `GLScatterPlotItem`.

#### `Interactive Plot`

- **Input:** `TimeSeries` or `DataFrame`.
- **Output:** `InteractiveFigure` with `renderer="plotly"`.
- **Rendering:** The Viz Panel creates a `QWebEngineView` and renders the Plotly figure as HTML.
- **Note:** This adds `plotly` and `PyQt6-WebEngine` (or PySide6 equivalent) as optional dependencies.

### 7.5 Viz Panel Overhaul

**File:** `src/persistra/ui/widgets/viz_panel.py` (rewrite)

The Viz Panel becomes a dynamic renderer that inspects the selected node's output type and chooses the appropriate display:

```python
class VizPanel(QWidget):
    """Dynamic visualization panel."""

    def __init__(self):
        super().__init__()
        self.stack = QStackedLayout(self)

        # Pre-created views
        self.matplotlib_view = MatplotlibView()     # FigureCanvasQTAgg
        self.table_view = DataTableView()            # QTableView with PandasModel
        self.gl_view = PointCloudView()              # pyqtgraph GLViewWidget
        self.code_editor = CodeEditorView()          # For PythonExpression node
        self.spreadsheet_view = SpreadsheetView()    # For Manual Data Entry node
        self.placeholder = PlaceholderView()         # "Select a node to view"

        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.matplotlib_view)
        self.stack.addWidget(self.table_view)
        self.stack.addWidget(self.gl_view)
        self.stack.addWidget(self.code_editor)
        self.stack.addWidget(self.spreadsheet_view)

    def display_node(self, node: Node):
        """Inspect the node and switch to the appropriate view."""
        if node is None:
            self.stack.setCurrentWidget(self.placeholder)
            return

        # Special node types with custom editors
        if isinstance(node.operation, PythonExpression):
            self.code_editor.set_node(node)
            self.stack.setCurrentWidget(self.code_editor)
            return

        if isinstance(node.operation, ManualDataEntry):
            self.spreadsheet_view.set_node(node)
            self.stack.setCurrentWidget(self.spreadsheet_view)
            return

        # Check cached outputs
        outputs = node._cached_outputs
        if not outputs:
            # Node hasn't been computed — show table of parameters or placeholder
            self.stack.setCurrentWidget(self.placeholder)
            return

        # Route based on output data type
        first_output = next(iter(outputs.values()), None)

        if isinstance(first_output, FigureWrapper):
            self.matplotlib_view.set_figure(first_output.data)
            self.stack.setCurrentWidget(self.matplotlib_view)

        elif isinstance(first_output, InteractiveFigure):
            if first_output.renderer == "pyqtgraph":
                self.gl_view.set_data(first_output.data)
                self.stack.setCurrentWidget(self.gl_view)

        elif isinstance(first_output, (TimeSeries, DataWrapper)):
            # Show as table
            self.table_view.set_data(first_output.data)
            self.stack.setCurrentWidget(self.table_view)

        else:
            self.stack.setCurrentWidget(self.placeholder)
```

---

## 8. Phase 5 — UI/UX Overhaul & Theming

### 8.1 Theme Engine

**File:** `src/persistra/ui/theme/` (new package)

#### 8.1.1 Architecture

```
src/persistra/ui/theme/
├── __init__.py          # ThemeManager class
├── tokens.py            # Color/spacing token definitions
├── dark_modern.py       # VS Code Dark Modern token values
├── light_modern.py      # VS Code Light Modern token values
└── stylesheets.py       # QSS generation from tokens
```

**`ThemeManager`:**
- Singleton that holds the current theme.
- Emits a `theme_changed` signal when toggled.
- All widgets connect to this signal and re-apply styles.
- Stores preference in `~/.persistra/settings.json`.

**`tokens.py`:**
- Defines a `ThemeTokens` dataclass with named colors for every UI element (see [Appendix C](#appendix-c--theme-color-tokens)).
- Each theme (dark/light) provides a concrete instance of `ThemeTokens`.

**`stylesheets.py`:**
- Generates complete QSS from a `ThemeTokens` instance using string templating.
- Applied globally via `QApplication.setStyleSheet()`.

#### 8.1.2 Node Editor Theming

The node editor canvas, node items, wires, and sockets all read from `ThemeManager.current_tokens` for their colors:

- **Canvas background:** `tokens.editor_background`
- **Grid lines:** `tokens.editor_grid` / `tokens.editor_grid_major`
- **Node body:** `tokens.node_background`
- **Node header:** Colored by category (see §8.4)
- **Node border (selected):** `tokens.accent`
- **Node border (error):** `tokens.error`
- **Node text:** `tokens.foreground`
- **Wire:** `tokens.wire_default`
- **Draft wire:** `tokens.accent` + dashed

See [Appendix C](#appendix-c--theme-color-tokens) for specific color values.

### 8.2 Menu Bar

**File:** `src/persistra/ui/menus/menu_bar.py` (new)

| Menu | Actions |
|------|---------|
| **File** | New Project · Open Project · Save (`Ctrl+S`) · Save As (`Ctrl+Shift+S`) · Export Figure · Recent Projects (submenu) · Quit (`Ctrl+Q`) |
| **Edit** | Copy (`Ctrl+C`) · Paste (`Ctrl+V`) · Delete (`Del`) · Select All (`Ctrl+A`) |
| **View** | Toggle Light/Dark Mode · Zoom In (`Ctrl+=`) · Zoom Out (`Ctrl+-`) · Zoom to Fit (`Ctrl+0`) · Toggle Auto-Compute |
| **Help** | About Persistra · Documentation (opens browser) · Check for Updates |

### 8.3 Toolbar

**File:** `src/persistra/ui/menus/toolbar.py` (new)

Buttons (left to right): **New** · **Open** · **Save** · **|** · **Run** · **Stop** · **Validate Graph** · **|** · **Zoom to Fit** · **|** · **Theme Toggle** (sun/moon icon)

- Icons: Use Qt built-in icons (`QStyle.StandardPixmap`) or a small bundled icon set (e.g., Material Design icons as SVGs, themed by the ThemeManager).

### 8.4 Node Browser Overhaul

**File:** `src/persistra/ui/widgets/node_browser.py` (rewrite)

Replace the flat `QListWidget` with a searchable `QTreeWidget`:

```
┌─────────────────────────────┐
│ 🔍 [Search operations...]   │
├─────────────────────────────┤
│ ▼ Input / Output            │
│     CSV Loader              │
│     Manual Data Entry       │
│     Data Generator          │
│     CSV Writer              │
│ ▼ Preprocessing             │
│     Normalize               │
│     Differencing            │
│     ...                     │
│ ▼ TDA                       │
│     Sliding Window          │
│     Rips Persistence        │
│     ...                     │
│ ▼ Machine Learning          │
│     ...                     │
│ ▼ Visualization             │
│     Line Plot               │
│     ...                     │
│ ▼ Templates                 │
│     (user-saved templates)  │
│ ▼ Plugins                   │
│     (loaded from ~/.persistra/plugins/) │
└─────────────────────────────┘
```

- **Search:** Typing in the search bar filters the tree in real-time (matches against operation name, description, and category).
- **Drag:** Drag from any leaf item onto the canvas to create a node.
- **Category coloring:** Each category has a distinct accent color used for the tree item icon and the corresponding node header on the canvas.

**Category color assignments** (these adapt to light/dark theme):

| Category | Dark Mode Header | Light Mode Header |
|----------|-----------------|-------------------|
| Input / Output | `#4A9EBF` (steel blue) | `#2E7D9E` |
| Preprocessing | `#6A9F5B` (sage green) | `#4E8A3E` |
| TDA | `#9B6BB5` (muted purple) | `#7E4F9A` |
| Machine Learning | `#BF8A4A` (amber) | `#A0713A` |
| Visualization | `#BF5A5A` (soft red) | `#A04040` |
| Utility | `#7A7A8A` (neutral gray) | `#5A5A6A` |
| Templates | `#5AAFAF` (teal) | `#3E8A8A` |
| Plugins | `#AF8A5A` (warm tan) | `#8A6A3E` |

### 8.5 Node Editor Enhancements

#### 8.5.1 Snap-to-Grid

When a node is dropped or moved, snap its position to the nearest grid intersection:

```python
def snap_to_grid(pos: QPointF, grid_size: int = 20) -> QPointF:
    x = round(pos.x() / grid_size) * grid_size
    y = round(pos.y() / grid_size) * grid_size
    return QPointF(x, y)
```

Applied in `NodeItem.mouseReleaseEvent()` or `NodeItem.itemChange()` when position changes.

#### 8.5.2 Auto-Layout

Implement a Sugiyama-style layered layout (left-to-right flow direction):

1. **Layer assignment:** Assign each node to a layer based on its longest path from a source node. Sources (no inputs connected) go to layer 0.
2. **Ordering:** Within each layer, order nodes to minimize edge crossings (barycenter heuristic).
3. **Positioning:** Space nodes evenly within each layer. Layers are spaced horizontally; nodes within a layer are spaced vertically.

Triggered via View menu → "Auto Layout" or a toolbar button. Animate the transition for polish (using `QPropertyAnimation` on node positions).

#### 8.5.3 Category-Based Node Coloring

The node header color is set from the category color table (§8.4). `NodeItem.paint()` reads the operation's category and looks up the color from `ThemeManager`.

#### 8.5.4 Copy-Paste

- **Copy (`Ctrl+C`):** Serialize selected nodes (positions, operation types, parameters, internal connections) to a JSON structure stored on the application clipboard.
- **Paste (`Ctrl+V`):** Deserialize and create new nodes with new UUIDs, offset from original positions by (20, 20) pixels. Internal connections between pasted nodes are preserved; connections to non-copied nodes are dropped.

### 8.6 Context Panel Updates

The Context Panel retains its role as a parameter inspector for the selected node. Add a **tab bar** at the top:

| Tab | Content |
|-----|---------|
| **Parameters** | The existing form-based parameter editor |
| **Info** | Node name, operation description, input/output socket types, current state |
| **Log** | Filtered log output (see Phase 6) |

---

## 9. Phase 6 — Error Handling, Logging & Validation

### 9.1 Structured Logging

**File:** `src/persistra/core/logging.py` (new)

```python
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".persistra" / "logs"

def setup_logging(level=logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("persistra")
    root_logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root_logger.addHandler(console)

    # File handler (rotating, 5MB max, 3 backups)
    file_handler = RotatingFileHandler(
        LOG_DIR / "persistra.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(logging.DEBUG)  # Always capture DEBUG to file
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    ))
    root_logger.addHandler(file_handler)

    return root_logger
```

Replace all `print()` statements throughout the codebase with `logger.info()`, `logger.debug()`, `logger.error()`, etc.

### 9.2 Log Tab in Context Panel

**File:** `src/persistra/ui/widgets/log_view.py` (new)

- A `QPlainTextEdit` (read-only) that receives log records via a custom `logging.Handler` subclass (`QLogHandler`) which emits a `Signal(str)`.
- **Node filter:** A dropdown at the top of the log tab allows filtering by:
  - "All Nodes" (global)
  - Specific node name/ID (populated from the current graph's nodes)
- **Auto-scroll:** Enabled by default, can be paused if the user scrolls up.
- **Level coloring:** ERROR = red, WARNING = yellow, INFO = white/black, DEBUG = gray.

### 9.3 Visual Node Indicators

Update `NodeItem.paint()` to render state indicators:

| State | Visual |
|-------|--------|
| **IDLE / VALID** | Normal border (theme default) |
| **DIRTY** | Dashed border or slight transparency to body |
| **COMPUTING** | Pulsing accent-color border (animated with `QTimer`) |
| **ERROR** | Solid red border (`tokens.error`), small ⚠ icon in header |
| **INVALID** | Grayed-out body and text (reduced opacity), no border highlight |

### 9.4 Graph Validation

**File:** `src/persistra/core/validation.py` (new)

```python
@dataclass
class ValidationMessage:
    level: str          # "error", "warning", "info"
    node_id: str
    message: str

class GraphValidator:
    """Validates a Project graph before execution."""

    def validate(self, project: Project) -> list[ValidationMessage]:
        messages = []
        messages.extend(self._check_required_inputs(project))
        messages.extend(self._check_type_mismatches(project))
        messages.extend(self._check_illegal_cycles(project))
        messages.extend(self._check_orphan_nodes(project))
        messages.extend(self._check_missing_parameters(project))
        return messages
```

**Checks:**

1. **Disconnected required inputs:** Any `Socket` with `required=True` and no connections → ERROR.
2. **Type mismatches:** Connected sockets where `target.socket_type.accepts(source.socket_type)` is `False` → ERROR.
3. **Illegal cycles:** Cycles that exist outside of an `IteratorNode` construct → ERROR. Uses DFS with back-edge detection, ignoring edges internal to `IteratorNode` bodies.
4. **Orphan nodes:** Nodes with zero connections (neither input nor output connected) → WARNING.
5. **Missing parameters:** Parameters with `None` or empty-string values on nodes that require them (e.g., `filepath` on `CSVLoader`) → WARNING.

**UI Integration:**
- Triggered via Edit → Validate Graph, or toolbar button, or automatically before "Run."
- Results are displayed in the Log tab and as visual indicators on affected nodes.
- If any ERROR-level messages exist, execution is blocked (with a dialog explaining why).

---

## 10. Phase 7 — Testing

### 10.1 Test Infrastructure

**Directory:** `tests/`

```
tests/
├── conftest.py              # Shared fixtures (sample data, mock projects, QApplication)
├── unit/
│   ├── test_types.py        # SocketType accepts/rejects logic
│   ├── test_objects.py      # DataWrapper validation
│   ├── test_node.py         # Node state transitions, compute, invalidate
│   ├── test_socket.py       # Connection/disconnection logic
│   ├── test_project.py      # Add/remove nodes, clear
│   ├── test_engine.py       # ExecutionPlanner, BranchTask, cancellation
│   ├── test_serializer.py   # ProjectSerializer save/load round-trip
│   ├── test_registry.py     # OperationRegistry register/get/search
│   ├── test_plugin_loader.py # Plugin discovery and loading
│   ├── test_validation.py   # GraphValidator checks
│   └── operations/
│       ├── test_csv_loader.py
│       ├── test_normalize.py
│       ├── test_sliding_window.py
│       ├── test_rips_persistence.py
│       ├── test_python_expression.py
│       ├── test_data_generator.py
│       └── ...              # One test file per operation
├── integration/
│   ├── test_pipeline_csv_to_plot.py      # End-to-end: CSV → Normalize → LinePlot
│   ├── test_pipeline_tda.py              # End-to-end: CSV → SlidingWindow → Rips → PersistencePlot
│   ├── test_pipeline_ml.py               # End-to-end: CSV → PCA → KMeans
│   ├── test_composite_node.py            # Create, save, load, and execute a CompositeNode
│   ├── test_iterator_node.py             # Loop convergence and fixed-count modes
│   ├── test_save_load_roundtrip.py       # Save project → Load → Verify equality
│   └── test_autosave.py                  # Autosave triggers correctly
└── ui/
    ├── test_main_window.py               # Window creation, menu/toolbar presence
    ├── test_node_browser.py              # Search, drag initiation, category tree
    ├── test_graph_scene.py               # Node creation, wire drawing, selection
    ├── test_viz_panel.py                 # View switching based on data type
    ├── test_context_panel.py             # Parameter editing, tab switching
    └── test_theme.py                     # Theme toggle, style application
```

### 10.2 Shared Fixtures

**File:** `tests/conftest.py`

This file provides reusable fixtures that are shared across all test tiers. Using `pytest` fixtures keeps tests DRY and ensures consistent test data.

```python
import pytest
import tempfile
import numpy as np
import pandas as pd
from pathlib import Path
from PySide6.QtWidgets import QApplication

from persistra.core.project import Project, Node, Operation
from persistra.core.objects import TimeSeries, DataWrapper
from persistra.core.types import ConcreteType, AnyType, SocketDef


# --- QApplication Fixture (required for all UI tests) ---

@pytest.fixture(scope="session")
def qapp():
    """Create a single QApplication instance for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# --- Sample Data Fixtures ---

@pytest.fixture
def sample_dataframe():
    """A simple 100-row, 3-column DataFrame for general testing."""
    np.random.seed(42)
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=100, freq="D"),
        "price": np.cumsum(np.random.randn(100)) + 100,
        "volume": np.random.randint(100, 10000, 100),
    }).set_index("time")


@pytest.fixture
def sample_timeseries(sample_dataframe):
    """A TimeSeries wrapper around the sample DataFrame."""
    return TimeSeries(sample_dataframe)


@pytest.fixture
def sample_csv_path(sample_dataframe, tmp_path):
    """Write the sample DataFrame to a CSV and return the path."""
    path = tmp_path / "test_data.csv"
    sample_dataframe.to_csv(path)
    return path


@pytest.fixture
def sample_point_cloud():
    """A 50x3 random point cloud for TDA tests."""
    np.random.seed(42)
    return np.random.randn(50, 3)


# --- Mock Operation Fixtures ---

class PassthroughOperation(Operation):
    """Minimal operation that passes input through unchanged."""
    name = "Passthrough"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.inputs = [SocketDef("data", AnyType())]
        self.outputs = [SocketDef("data", AnyType())]
        self.parameters = []

    def execute(self, inputs, params, cancel_event=None):
        return {"data": inputs.get("data")}


class SourceOperation(Operation):
    """Minimal source operation that outputs a fixed value."""
    name = "Source"
    category = "Test"

    def __init__(self):
        super().__init__()
        self.inputs = []
        self.outputs = [SocketDef("data", AnyType())]
        self.parameters = []

    def execute(self, inputs, params, cancel_event=None):
        return {"data": DataWrapper(42)}


@pytest.fixture
def sample_operation_cls():
    return SourceOperation


@pytest.fixture
def passthrough_operation_cls():
    return PassthroughOperation


# --- Graph Fixtures ---

@pytest.fixture
def empty_project():
    return Project()


@pytest.fixture
def two_connected_nodes(empty_project):
    """A project with Source → Passthrough, already connected."""
    source = empty_project.add_node(SourceOperation)
    passthrough = empty_project.add_node(PassthroughOperation)
    source_out = source.get_output_socket("data")
    passthrough_in = passthrough.get_input_socket("data")
    source_out.connect_to(passthrough_in)
    return source, passthrough


@pytest.fixture
def three_node_chain(empty_project):
    """Source → Passthrough → Passthrough chain."""
    n1 = empty_project.add_node(SourceOperation)
    n2 = empty_project.add_node(PassthroughOperation)
    n3 = empty_project.add_node(PassthroughOperation)
    n1.get_output_socket("data").connect_to(n2.get_input_socket("data"))
    n2.get_output_socket("data").connect_to(n3.get_input_socket("data"))
    return n1, n2, n3


# --- Temporary Directory Fixtures ---

@pytest.fixture
def plugin_dir(tmp_path):
    """Create a temporary plugin directory with a sample plugin file."""
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    return plugins


@pytest.fixture
def persistra_home(tmp_path, monkeypatch):
    """Override the ~/.persistra directory for isolated testing."""
    home = tmp_path / ".persistra"
    home.mkdir()
    (home / "plugins").mkdir()
    (home / "templates").mkdir()
    (home / "logs").mkdir()
    monkeypatch.setenv("PERSISTRA_HOME", str(home))
    return home
```

### 10.3 Unit Test Strategy

Each unit test file targets a single module or class. Tests are organized by behavior, not by method.

#### 10.3.1 Type System Tests

**File:** `tests/unit/test_types.py`

```python
import pytest
from persistra.core.types import ConcreteType, UnionType, AnyType
from persistra.core.objects import TimeSeries, DistanceMatrix, DataWrapper, PointCloud


class TestConcreteType:
    def test_exact_match_accepts(self):
        ts_type = ConcreteType(TimeSeries)
        assert ts_type.accepts(ConcreteType(TimeSeries)) is True

    def test_subclass_accepts(self):
        base_type = ConcreteType(DataWrapper)
        assert base_type.accepts(ConcreteType(TimeSeries)) is True

    def test_unrelated_type_rejects(self):
        ts_type = ConcreteType(TimeSeries)
        assert ts_type.accepts(ConcreteType(DistanceMatrix)) is False

    def test_shape_constraint_accepts_matching(self):
        constrained = ConcreteType(PointCloud, shape=(None, 3))
        unconstrained = ConcreteType(PointCloud, shape=(50, 3))
        assert constrained.accepts(unconstrained) is True

    def test_shape_constraint_rejects_mismatch(self):
        constrained = ConcreteType(PointCloud, shape=(None, 3))
        wrong_shape = ConcreteType(PointCloud, shape=(50, 2))
        assert constrained.accepts(wrong_shape) is False

    def test_dtype_constraint(self):
        f64 = ConcreteType(TimeSeries, dtype="float64")
        f32 = ConcreteType(TimeSeries, dtype="float32")
        assert f64.accepts(f32) is False
        assert f64.accepts(ConcreteType(TimeSeries, dtype="float64")) is True


class TestUnionType:
    def test_accepts_any_member(self):
        union = UnionType(ConcreteType(TimeSeries), ConcreteType(DistanceMatrix))
        assert union.accepts(ConcreteType(TimeSeries)) is True
        assert union.accepts(ConcreteType(DistanceMatrix)) is True

    def test_rejects_non_member(self):
        union = UnionType(ConcreteType(TimeSeries), ConcreteType(DistanceMatrix))
        assert union.accepts(ConcreteType(PointCloud)) is False


class TestAnyType:
    def test_accepts_everything(self):
        any_type = AnyType()
        assert any_type.accepts(ConcreteType(TimeSeries)) is True
        assert any_type.accepts(ConcreteType(DistanceMatrix)) is True
        assert any_type.accepts(AnyType()) is True
```

#### 10.3.2 Node & Graph Model Tests

**File:** `tests/unit/test_node.py`

```python
import pytest
from persistra.core.project import Node


class TestNodeLifecycle:
    def test_new_node_is_dirty(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        assert node._is_dirty is True

    def test_compute_marks_clean(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        node.compute()
        assert node._is_dirty is False

    def test_compute_returns_cached_on_second_call(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        result1 = node.compute()
        result2 = node.compute()
        assert result1 is result2  # Same object, not recomputed

    def test_invalidate_marks_dirty(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        node.compute()
        node.invalidate()
        assert node._is_dirty is True
        assert node._cached_outputs == {}


class TestNodePropagation:
    def test_invalidate_propagates_downstream(self, two_connected_nodes):
        upstream, downstream = two_connected_nodes
        upstream.compute()
        downstream.compute()
        assert downstream._is_dirty is False
        upstream.invalidate()
        assert downstream._is_dirty is True

    def test_parameter_change_invalidates(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        node.compute()
        # If the operation has parameters, changing one should invalidate
        # For SourceOperation with no params, test with a parameterized op instead
        assert node._is_dirty is False

    def test_chain_propagation(self, three_node_chain):
        n1, n2, n3 = three_node_chain
        n1.compute()
        n2.compute()
        n3.compute()
        n1.invalidate()
        assert n2._is_dirty is True
        assert n3._is_dirty is True


class TestNodeSockets:
    def test_get_input_socket_by_name(self, passthrough_operation_cls):
        node = Node(passthrough_operation_cls)
        sock = node.get_input_socket("data")
        assert sock is not None
        assert sock.name == "data"

    def test_get_nonexistent_socket_returns_none(self, sample_operation_cls):
        node = Node(sample_operation_cls)
        assert node.get_input_socket("nonexistent") is None
```

#### 10.3.3 Operation Tests

Each operation gets its own test file. The pattern is consistent: instantiate the operation, provide known inputs via dicts, call `execute()`, and assert on the output.

**File:** `tests/unit/operations/test_csv_loader.py`

```python
import pytest
import pandas as pd
from persistra.operations.io import CSVLoader
from persistra.core.objects import TimeSeries


class TestCSVLoader:
    def test_loads_valid_csv(self, sample_csv_path):
        op = CSVLoader()
        result = op.execute({}, {"filepath": str(sample_csv_path), "index_col": "0"})
        assert "data" in result
        assert isinstance(result["data"], TimeSeries)
        assert isinstance(result["data"].data, pd.DataFrame)
        assert len(result["data"].data) > 0

    def test_raises_on_missing_file(self, tmp_path):
        op = CSVLoader()
        with pytest.raises(FileNotFoundError):
            op.execute({}, {"filepath": str(tmp_path / "nonexistent.csv"), "index_col": "0"})

    def test_string_index_col(self, sample_csv_path):
        op = CSVLoader()
        result = op.execute({}, {"filepath": str(sample_csv_path), "index_col": "time"})
        assert result["data"].data.index.name == "time"

    def test_none_index_col(self, sample_csv_path):
        op = CSVLoader()
        result = op.execute({}, {"filepath": str(sample_csv_path), "index_col": None})
        assert isinstance(result["data"].data.index, pd.RangeIndex)
```

**File:** `tests/unit/operations/test_normalize.py`

```python
import pytest
import numpy as np
import pandas as pd
from persistra.operations.preprocessing import Normalize
from persistra.core.objects import TimeSeries


class TestNormalize:
    def test_minmax_output_range(self):
        op = Normalize()
        ts = TimeSeries(pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}))
        result = op.execute({"data": ts}, {"method": "min-max"})
        output = result["data"].data
        assert output.min().min() == pytest.approx(0.0)
        assert output.max().max() == pytest.approx(1.0)

    def test_zscore_mean_std(self):
        op = Normalize()
        np.random.seed(42)
        ts = TimeSeries(pd.DataFrame({"a": np.random.randn(1000)}))
        result = op.execute({"data": ts}, {"method": "z-score"})
        output = result["data"].data
        assert output.mean().iloc[0] == pytest.approx(0.0, abs=0.05)
        assert output.std().iloc[0] == pytest.approx(1.0, abs=0.05)

    def test_constant_column_minmax(self):
        """Min-max on a constant column should produce all zeros (0/0 edge case)."""
        op = Normalize()
        ts = TimeSeries(pd.DataFrame({"a": [5.0, 5.0, 5.0]}))
        result = op.execute({"data": ts}, {"method": "min-max"})
        output = result["data"].data
        assert output.isna().all().all() or (output == 0).all().all()
```

**File:** `tests/unit/operations/test_python_expression.py`

```python
import pytest
import pandas as pd
import numpy as np
from persistra.operations.utility import PythonExpression
from persistra.core.objects import TimeSeries


class TestPythonExpression:
    def test_simple_passthrough(self):
        op = PythonExpression()
        ts = TimeSeries(pd.DataFrame({"a": [1, 2, 3]}))
        result = op.execute(
            {"data": ts},
            {"code": "result = inputs['data']"}
        )
        assert result["result"] is ts

    def test_numpy_available(self):
        op = PythonExpression()
        result = op.execute({}, {"code": "result = np.array([1, 2, 3])"})
        assert np.array_equal(result["result"], np.array([1, 2, 3]))

    def test_pandas_available(self):
        op = PythonExpression()
        result = op.execute({}, {"code": "result = pd.DataFrame({'x': [1]})"})
        assert isinstance(result["result"], pd.DataFrame)

    def test_syntax_error_raises(self):
        op = PythonExpression()
        with pytest.raises(SyntaxError):
            op.execute({}, {"code": "def incomplete("})

    def test_runtime_error_raises(self):
        op = PythonExpression()
        with pytest.raises(NameError):
            op.execute({}, {"code": "result = undefined_variable"})
```

#### 10.3.4 Serialization Tests

**File:** `tests/unit/test_serializer.py`

```python
import pytest
from pathlib import Path
from persistra.core.io import ProjectSerializer
from persistra.core.project import Project
from persistra.operations.io import CSVLoader
from persistra.operations.preprocessing import Normalize


class TestProjectSerializer:
    def test_save_creates_file(self, empty_project, tmp_path):
        filepath = tmp_path / "test.persistra"
        serializer = ProjectSerializer()
        serializer.save(empty_project, filepath)
        assert filepath.exists()

    def test_roundtrip_preserves_node_count(self, tmp_path):
        project = Project()
        project.add_node(CSVLoader)
        project.add_node(Normalize)

        filepath = tmp_path / "test.persistra"
        serializer = ProjectSerializer()
        serializer.save(project, filepath)
        loaded = serializer.load(filepath)
        assert len(loaded.nodes) == 2

    def test_roundtrip_preserves_parameters(self, tmp_path):
        project = Project()
        node = project.add_node(CSVLoader)
        node.set_parameter("filepath", "/some/path.csv")

        filepath = tmp_path / "test.persistra"
        serializer = ProjectSerializer()
        serializer.save(project, filepath)
        loaded = serializer.load(filepath)
        loaded_node = loaded.nodes[0]
        param_value = next(
            p.value for p in loaded_node.parameters if p.name == "filepath"
        )
        assert param_value == "/some/path.csv"

    def test_roundtrip_preserves_connections(self, tmp_path):
        project = Project()
        n1 = project.add_node(CSVLoader)
        n2 = project.add_node(Normalize)
        n1.get_output_socket("data").connect_to(n2.get_input_socket("data"))

        filepath = tmp_path / "test.persistra"
        serializer = ProjectSerializer()
        serializer.save(project, filepath)
        loaded = serializer.load(filepath)

        loaded_n2_input = loaded.nodes[1].get_input_socket("data")
        assert len(loaded_n2_input.connections) == 1

    def test_roundtrip_restores_cache(self, tmp_path, sample_csv_path):
        project = Project()
        node = project.add_node(CSVLoader)
        node.set_parameter("filepath", str(sample_csv_path))
        node.compute()
        assert not node._is_dirty

        filepath = tmp_path / "test.persistra"
        serializer = ProjectSerializer()
        serializer.save(project, filepath)
        loaded = serializer.load(filepath)
        assert not loaded.nodes[0]._is_dirty
        assert "data" in loaded.nodes[0]._cached_outputs
```

#### 10.3.5 Validation Tests

**File:** `tests/unit/test_validation.py`

```python
import pytest
from persistra.core.validation import GraphValidator, ValidationMessage
from persistra.core.project import Project
from persistra.operations.io import CSVLoader
from persistra.operations.preprocessing import Normalize


class TestGraphValidator:
    def test_disconnected_required_input_is_error(self):
        project = Project()
        project.add_node(Normalize)  # Has required "data" input, not connected
        validator = GraphValidator()
        messages = validator.validate(project)
        errors = [m for m in messages if m.level == "error"]
        assert len(errors) >= 1
        assert "required" in errors[0].message.lower() or "disconnected" in errors[0].message.lower()

    def test_valid_graph_has_no_errors(self, sample_csv_path):
        project = Project()
        n1 = project.add_node(CSVLoader)
        n1.set_parameter("filepath", str(sample_csv_path))
        n2 = project.add_node(Normalize)
        n1.get_output_socket("data").connect_to(n2.get_input_socket("data"))

        validator = GraphValidator()
        messages = validator.validate(project)
        errors = [m for m in messages if m.level == "error"]
        assert len(errors) == 0

    def test_orphan_node_is_warning(self):
        project = Project()
        project.add_node(CSVLoader)
        project.add_node(Normalize)  # Both disconnected from each other
        validator = GraphValidator()
        messages = validator.validate(project)
        warnings = [m for m in messages if m.level == "warning"]
        # At least one orphan warning expected
        assert any("orphan" in w.message.lower() for w in warnings)

    def test_missing_parameter_is_warning(self):
        project = Project()
        node = project.add_node(CSVLoader)
        node.set_parameter("filepath", "")  # Empty required param
        validator = GraphValidator()
        messages = validator.validate(project)
        warnings = [m for m in messages if m.level == "warning"]
        assert len(warnings) >= 1
```

#### 10.3.6 Registry & Plugin Tests

**File:** `tests/unit/test_registry.py`

```python
import pytest
from persistra.operations import OperationRegistry
from persistra.core.project import Operation


class TestOperationRegistry:
    def test_register_and_get(self):
        registry = OperationRegistry()

        class TestOp(Operation):
            name = "Test Op"
            category = "Test"
        
        registry.register(TestOp)
        assert registry.get("Test Op") is TestOp

    def test_duplicate_name_raises(self):
        registry = OperationRegistry()

        class TestOp(Operation):
            name = "Dup"
            category = "Test"

        registry.register(TestOp)
        with pytest.raises(ValueError, match="Duplicate"):
            registry.register(TestOp)

    def test_search_by_name(self):
        registry = OperationRegistry()

        class FooOp(Operation):
            name = "Foo Bar"
            description = "Does foo"
            category = "Test"

        registry.register(FooOp)
        results = registry.search("foo")
        assert FooOp in results

    def test_by_category(self):
        registry = OperationRegistry()

        class OpA(Operation):
            name = "A"
            category = "Cat1"

        class OpB(Operation):
            name = "B"
            category = "Cat2"

        registry.register(OpA)
        registry.register(OpB)
        cats = registry.by_category()
        assert "Cat1" in cats
        assert "Cat2" in cats
        assert OpA in cats["Cat1"]
```

**File:** `tests/unit/test_plugin_loader.py`

```python
import pytest
from pathlib import Path
from persistra.plugins.loader import load_plugins
from persistra.operations import REGISTRY


class TestPluginLoader:
    def test_loads_valid_plugin(self, plugin_dir, monkeypatch):
        monkeypatch.setattr("persistra.plugins.loader.PLUGIN_DIR", plugin_dir)

        plugin_code = '''
from persistra.operations import REGISTRY
from persistra.core.project import Operation

@REGISTRY.register
class PluginTestOp(Operation):
    name = "Plugin Test Op"
    category = "Plugins"
    def execute(self, inputs, params, cancel_event=None):
        return {}
'''
        (plugin_dir / "test_plugin.py").write_text(plugin_code)
        load_plugins()
        assert REGISTRY.get("Plugin Test Op") is not None

    def test_invalid_plugin_does_not_crash(self, plugin_dir, monkeypatch):
        monkeypatch.setattr("persistra.plugins.loader.PLUGIN_DIR", plugin_dir)
        (plugin_dir / "bad_plugin.py").write_text("raise RuntimeError('broken')")
        # Should log an error but not raise
        load_plugins()

    def test_non_python_files_ignored(self, plugin_dir, monkeypatch):
        monkeypatch.setattr("persistra.plugins.loader.PLUGIN_DIR", plugin_dir)
        (plugin_dir / "readme.txt").write_text("not a plugin")
        load_plugins()  # Should not raise
```

### 10.4 Integration Test Strategy

Integration tests build multi-node graphs programmatically, execute them end-to-end, and verify the final outputs. They test the interaction between the core model, the execution engine, and real operations.

**File:** `tests/integration/test_pipeline_csv_to_plot.py`

```python
import pytest
import matplotlib.figure
from persistra.core.project import Project
from persistra.operations.io import CSVLoader
from persistra.operations.preprocessing import Normalize
from persistra.operations.viz import LinePlot
from persistra.core.objects import FigureWrapper


class TestCSVToPlotPipeline:
    def test_csv_normalize_lineplot(self, sample_csv_path):
        project = Project()
        loader = project.add_node(CSVLoader)
        loader.set_parameter("filepath", str(sample_csv_path))
        loader.set_parameter("index_col", "0")

        norm = project.add_node(Normalize)
        norm.set_parameter("method", "min-max")

        plot = project.add_node(LinePlot)

        loader.get_output_socket("data").connect_to(norm.get_input_socket("data"))
        norm.get_output_socket("data").connect_to(plot.get_input_socket("data"))

        result = plot.compute()
        assert "plot" in result
        assert isinstance(result["plot"], FigureWrapper)
        assert isinstance(result["plot"].data, matplotlib.figure.Figure)
```

**File:** `tests/integration/test_pipeline_tda.py`

```python
import pytest
from persistra.core.project import Project
from persistra.operations.io import CSVLoader
from persistra.operations.tda import SlidingWindow, RipsPersistence
from persistra.core.objects import PersistenceDiagram


class TestTDAPipeline:
    def test_csv_to_persistence_diagram(self, sample_csv_path):
        project = Project()
        loader = project.add_node(CSVLoader)
        loader.set_parameter("filepath", str(sample_csv_path))
        loader.set_parameter("index_col", "0")

        window = project.add_node(SlidingWindow)
        window.set_parameter("window_size", 10)
        window.set_parameter("step", 1)

        rips = project.add_node(RipsPersistence)
        rips.set_parameter("max_dim", 1)

        loader.get_output_socket("data").connect_to(window.get_input_socket("series"))
        window.get_output_socket("cloud").connect_to(rips.get_input_socket("cloud"))

        result = rips.compute()
        assert "diagram" in result
        assert isinstance(result["diagram"], PersistenceDiagram)
        assert len(result["diagram"].data) >= 1  # At least H0

    def test_recomputation_on_parameter_change(self, sample_csv_path):
        """Changing a parameter should invalidate downstream and produce new results."""
        project = Project()
        loader = project.add_node(CSVLoader)
        loader.set_parameter("filepath", str(sample_csv_path))

        window = project.add_node(SlidingWindow)
        window.set_parameter("window_size", 10)

        rips = project.add_node(RipsPersistence)
        rips.set_parameter("max_dim", 1)

        loader.get_output_socket("data").connect_to(window.get_input_socket("series"))
        window.get_output_socket("cloud").connect_to(rips.get_input_socket("cloud"))

        result1 = rips.compute()
        window.set_parameter("window_size", 20)
        assert rips._is_dirty is True

        result2 = rips.compute()
        # Results should differ because the window size changed
        assert result1 is not result2
```

**File:** `tests/integration/test_save_load_roundtrip.py`

```python
import pytest
from persistra.core.project import Project
from persistra.core.io import ProjectSerializer
from persistra.operations.io import CSVLoader
from persistra.operations.tda import SlidingWindow


class TestSaveLoadRoundtrip:
    def test_full_pipeline_roundtrip(self, sample_csv_path, tmp_path):
        """Build a pipeline, compute, save, load, and verify state."""
        # Build
        project = Project()
        loader = project.add_node(CSVLoader)
        loader.set_parameter("filepath", str(sample_csv_path))
        window = project.add_node(SlidingWindow)
        window.set_parameter("window_size", 10)
        loader.get_output_socket("data").connect_to(window.get_input_socket("series"))

        # Compute
        window.compute()
        assert not window._is_dirty

        # Save
        filepath = tmp_path / "pipeline.persistra"
        serializer = ProjectSerializer()
        serializer.save(project, filepath)

        # Load
        loaded = serializer.load(filepath)

        # Verify
        assert len(loaded.nodes) == 2
        loaded_window = loaded.nodes[1]
        assert not loaded_window._is_dirty
        assert "cloud" in loaded_window._cached_outputs
```

**File:** `tests/integration/test_iterator_node.py`

```python
import pytest
import numpy as np
from persistra.core.composite import IteratorNode, CompositeNode
from persistra.core.project import Project


class TestIteratorNode:
    def test_fixed_count_executes_n_times(self):
        """The iterator should execute its body exactly N times in fixed_count mode."""
        # Setup: a body that increments a counter each iteration
        # (Implementation details depend on the final CompositeNode API)
        pass  # Placeholder — flesh out once CompositeNode is implemented

    def test_convergence_mode_stops_early(self):
        """The iterator should stop when output delta falls below tolerance."""
        pass  # Placeholder

    def test_max_iterations_prevents_infinite_loop(self):
        """Even in convergence mode, should stop at max_iterations."""
        pass  # Placeholder
```

**File:** `tests/integration/test_composite_node.py`

```python
import pytest
from persistra.core.composite import CompositeNode
from persistra.core.project import Project
from persistra.operations.preprocessing import Normalize


class TestCompositeNode:
    def test_create_and_execute(self):
        """Create a composite node, execute it, and verify outputs."""
        pass  # Placeholder — depends on CompositeNode implementation

    def test_save_and_load_template(self, tmp_path):
        """Save a composite as a .persistra-template and reload it."""
        pass  # Placeholder

    def test_exposed_parameters(self):
        """Verify that exposed inner parameters are accessible from outside."""
        pass  # Placeholder
```

### 10.5 UI Test Strategy

UI tests use `pytest-qt` and the `qapp` fixture to verify widget behavior. They do not rely on visual appearance — they test programmatic interactions, signal emissions, and widget state.

**File:** `tests/ui/test_main_window.py`

```python
import pytest
from persistra.ui.main_window import MainWindow


class TestMainWindow:
    def test_window_creates_without_error(self, qapp):
        window = MainWindow()
        assert window is not None
        assert window.windowTitle() == "Persistra - Visual Analysis Tool"

    def test_menu_bar_exists(self, qapp):
        window = MainWindow()
        menu_bar = window.menuBar()
        assert menu_bar is not None
        # Check that expected menus are present
        menu_titles = [a.text() for a in menu_bar.actions()]
        assert "File" in menu_titles
        assert "Edit" in menu_titles
        assert "View" in menu_titles
        assert "Help" in menu_titles

    def test_toolbar_exists(self, qapp):
        window = MainWindow()
        toolbars = window.findChildren(window.__class__.__mro__[0])
        # At least one toolbar should exist
        assert len(window.findChildren(type(window.toolbar))) >= 1

    def test_central_panels_exist(self, qapp):
        window = MainWindow()
        assert window.node_browser is not None
        assert window.viz_panel is not None
        assert window.context_panel is not None
        assert window.view is not None
```

**File:** `tests/ui/test_node_browser.py`

```python
import pytest
from PySide6.QtCore import Qt
from persistra.ui.widgets.node_browser import NodeBrowser


class TestNodeBrowser:
    def test_operations_populated(self, qapp):
        browser = NodeBrowser()
        # After initialization with registry, should have items
        assert browser.topLevelItemCount() > 0  # Categories as top-level items

    def test_search_filters_results(self, qapp):
        browser = NodeBrowser()
        browser.search_bar.setText("CSV")
        # Only items matching "CSV" should be visible
        visible_items = []
        for i in range(browser.tree.topLevelItemCount()):
            cat = browser.tree.topLevelItem(i)
            if not cat.isHidden():
                for j in range(cat.childCount()):
                    if not cat.child(j).isHidden():
                        visible_items.append(cat.child(j).text(0))
        assert any("CSV" in name for name in visible_items)

    def test_search_no_match_shows_empty(self, qapp):
        browser = NodeBrowser()
        browser.search_bar.setText("zzzznonexistent")
        # All items should be hidden
        visible = False
        for i in range(browser.tree.topLevelItemCount()):
            cat = browser.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                if not cat.child(j).isHidden():
                    visible = True
        assert not visible
```

**File:** `tests/ui/test_viz_panel.py`

```python
import pytest
import numpy as np
import pandas as pd
import matplotlib.figure
from PySide6.QtWidgets import QStackedLayout
from persistra.ui.widgets.viz_panel import VizPanel
from persistra.core.project import Node
from persistra.core.objects import FigureWrapper, TimeSeries
from persistra.operations.viz import LinePlot
from persistra.operations.io import CSVLoader


class TestVizPanel:
    def test_shows_placeholder_initially(self, qapp):
        panel = VizPanel()
        assert panel.stack.currentWidget() == panel.placeholder

    def test_shows_placeholder_on_none(self, qapp):
        panel = VizPanel()
        panel.display_node(None)
        assert panel.stack.currentWidget() == panel.placeholder

    def test_shows_matplotlib_for_figure_output(self, qapp, sample_csv_path):
        """When a viz node has a cached FigureWrapper, show the matplotlib view."""
        panel = VizPanel()
        # Create and compute a LinePlot node
        node = Node(LinePlot)
        # Manually set cached output for testing
        fig = matplotlib.figure.Figure()
        node._cached_outputs = {"plot": FigureWrapper(fig)}
        node._is_dirty = False

        panel.display_node(node)
        assert panel.stack.currentWidget() == panel.matplotlib_view

    def test_shows_table_for_data_output(self, qapp):
        """When a data node has a cached TimeSeries, show the table view."""
        panel = VizPanel()
        node = Node(CSVLoader)
        ts = TimeSeries(pd.DataFrame({"a": [1, 2, 3]}))
        node._cached_outputs = {"data": ts}
        node._is_dirty = False

        panel.display_node(node)
        assert panel.stack.currentWidget() == panel.table_view
```

**File:** `tests/ui/test_theme.py`

```python
import pytest
from persistra.ui.theme import ThemeManager


class TestThemeManager:
    def test_default_theme_is_dark(self, qapp):
        tm = ThemeManager()
        assert tm.current_theme == "dark"

    def test_toggle_changes_theme(self, qapp):
        tm = ThemeManager()
        tm.toggle()
        assert tm.current_theme == "light"
        tm.toggle()
        assert tm.current_theme == "dark"

    def test_signal_emitted_on_toggle(self, qapp, qtbot):
        tm = ThemeManager()
        with qtbot.waitSignal(tm.theme_changed, timeout=1000):
            tm.toggle()

    def test_tokens_differ_between_themes(self, qapp):
        tm = ThemeManager()
        dark_bg = tm.current_tokens.editor_background
        tm.toggle()
        light_bg = tm.current_tokens.editor_background
        assert dark_bg != light_bg
```

### 10.6 Test Configuration

**File:** `pyproject.toml` (additions)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = [
    "--strict-markers",
    "--tb=short",
    "-q",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "tda: marks tests requiring TDA libraries (ripser, gudhi, etc.)",
    "ui: marks UI tests requiring a display server",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage]
[tool.coverage.run]
source = ["src/persistra"]
omit = ["tests/*"]

[tool.coverage.report]
show_missing = true
fail_under = 70
```

### 10.7 Test Execution Commands

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only UI tests
pytest tests/ui/

# Run with coverage
pytest --cov=persistra --cov-report=html

# Skip slow TDA tests (if ripser not installed)
pytest -m "not tda"

# Skip UI tests (e.g., in headless CI)
pytest -m "not ui"
```

---

## 11. Phase 8 — Packaging, CI/CD & Documentation

### 11.1 CI/CD with GitHub Actions

**File:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint & Format Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install ruff black mypy

      - name: Ruff lint
        run: ruff check src/ tests/

      - name: Black format check
        run: black --check --diff src/ tests/

      - name: Mypy type check
        run: mypy src/persistra/ --ignore-missing-imports

  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install system dependencies (Qt)
        run: |
          sudo apt-get update
          sudo apt-get install -y libgl1-mesa-glx libegl1 libxkbcommon0 libdbus-1-3

      - name: Install package with dev dependencies
        run: |
          pip install -e ".[dev,tda,ml]"

      - name: Run unit and integration tests
        run: |
          pytest tests/unit/ tests/integration/ --cov=persistra --cov-report=xml -m "not ui"

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  test-ui:
    name: UI Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y libgl1-mesa-glx libegl1 libxkbcommon0 libdbus-1-3 xvfb

      - name: Install package
        run: pip install -e ".[dev]"

      - name: Run UI tests with virtual display
        run: |
          xvfb-run pytest tests/ui/ -m "ui"

  release:
    name: Build & Release
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: pip install build

      - name: Build package
        run: python -m build

      - name: Upload to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

### 11.2 Documentation with MkDocs

#### 11.2.1 Directory Structure

```
docs/
├── index.md                    # Landing page
├── getting-started/
│   ├── installation.md         # Install instructions (pip, from source)
│   └── quickstart.md           # First pipeline tutorial
├── user-guide/
│   ├── interface-overview.md   # Panels, menus, toolbar
│   ├── building-pipelines.md   # Creating nodes, connecting, running
│   ├── visualization.md        # Viz nodes, 3D, plot composition
│   ├── saving-loading.md       # Project files, autosave, export
│   └── settings.md             # Theme, autosave interval, etc.
├── operations/
│   ├── index.md                # Category overview
│   ├── io.md                   # I/O operations reference
│   ├── preprocessing.md        # Preprocessing operations reference
│   ├── tda.md                  # TDA operations reference
│   ├── ml.md                   # ML operations reference
│   └── visualization.md        # Viz operations reference
├── developer-guide/
│   ├── architecture.md         # Core model, engine, type system
│   ├── creating-operations.md  # How to write a new operation
│   ├── plugin-development.md   # How to create and install plugins
│   └── contributing.md         # Code style, PR process, testing
└── api/                        # Auto-generated from docstrings
    ├── core.md
    ├── operations.md
    └── ui.md
```

#### 11.2.2 MkDocs Configuration

**File:** `mkdocs.yml`

```yaml
site_name: Persistra Documentation
site_description: Visual node-based data analysis tool
repo_url: https://github.com/fallblu/persistra
repo_name: fallblu/persistra

theme:
  name: material
  palette:
    - scheme: default
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-4
        name: Switch to light mode
  features:
    - navigation.sections
    - navigation.expand
    - search.suggest
    - content.code.copy

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true
            show_root_heading: true
            docstring_style: google

nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/installation.md
    - Quick Start: getting-started/quickstart.md
  - User Guide:
    - Interface Overview: user-guide/interface-overview.md
    - Building Pipelines: user-guide/building-pipelines.md
    - Visualization: user-guide/visualization.md
    - Saving & Loading: user-guide/saving-loading.md
    - Settings: user-guide/settings.md
  - Operations Reference:
    - Overview: operations/index.md
    - Input / Output: operations/io.md
    - Preprocessing: operations/preprocessing.md
    - TDA: operations/tda.md
    - Machine Learning: operations/ml.md
    - Visualization: operations/visualization.md
  - Developer Guide:
    - Architecture: developer-guide/architecture.md
    - Creating Operations: developer-guide/creating-operations.md
    - Plugin Development: developer-guide/plugin-development.md
    - Contributing: developer-guide/contributing.md
  - API Reference:
    - Core: api/core.md
    - Operations: api/operations.md
    - UI: api/ui.md

markdown_extensions:
  - admonitions
  - pymdownx.highlight
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - toc:
      permalink: true
```

#### 11.2.3 API Reference Pages

Each API reference page uses `mkdocstrings` to auto-generate documentation from docstrings:

**File:** `docs/api/core.md`

```markdown
# Core API Reference

## Project

::: persistra.core.project.Project

## Node

::: persistra.core.project.Node

## Socket

::: persistra.core.project.Socket

## Operation

::: persistra.core.project.Operation

## Type System

::: persistra.core.types

## Data Objects

::: persistra.core.objects

## Execution Engine

::: persistra.core.engine

## Validation

::: persistra.core.validation
```

#### 11.2.4 Documentation Build Commands

```bash
# Install docs dependencies
pip install mkdocs-material mkdocstrings[python]

# Serve locally with hot-reload
mkdocs serve

# Build static site
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy
```

### 11.3 Updated `pyproject.toml` (Final)

Incorporating all phases, the final build configuration:

```toml
[build-system]
requires = ["setuptools>=68.0", "setuptools-scm"]
build-backend = "setuptools.build_meta"

[project]
name = "persistra"
dynamic = ["version"]
description = "A node-based visual data analysis tool"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
authors = [
    {name = "James Mallette", email = "jamesmallmw@gmail.com"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Visualization",
]
dependencies = [
    "PySide6>=6.6",
    "numpy>=1.24",
    "pandas>=2.0",
    "matplotlib>=3.7",
    "pyqtgraph>=0.13",
    "OpenGL",
]

[project.optional-dependencies]
tda = [
    "ripser",
    "persim",
    "giotto-tda",
    "gudhi",
    "scikit-tda",
]
ml = [
    "scikit-learn>=1.3",
]
interactive = [
    "plotly",
]
dev = [
    "pytest>=7.0",
    "pytest-qt>=4.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "black>=23.0",
    "mypy>=1.5",
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.24",
]

[project.scripts]
persistra = "persistra.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools_scm]

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "UP"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--tb=short", "-q"]
markers = [
    "slow: marks tests as slow",
    "tda: marks tests requiring TDA libraries",
    "ui: marks UI tests requiring a display server",
]
filterwarnings = ["ignore::DeprecationWarning"]

[tool.coverage.run]
source = ["src/persistra"]
omit = ["tests/*"]

[tool.coverage.report]
show_missing = true
fail_under = 70
```

---

## Appendix A — Proposed Directory Structure

```
persistra/
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/
│   ├── index.md
│   ├── getting-started/
│   ├── user-guide/
│   ├── operations/
│   ├── developer-guide/
│   └── api/
├── mkdocs.yml
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── persistra/
│       ├── __init__.py
│       ├── __main__.py                  # Application entry point
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── project.py               # Project, Node, Socket, Operation
│       │   ├── types.py                 # SocketType, ConcreteType, UnionType, AnyType
│       │   ├── objects.py               # DataWrapper subclasses, Parameter subclasses
│       │   ├── engine.py                # ExecutionEngine, ExecutionPlanner, BranchTask
│       │   ├── composite.py             # CompositeNode, IteratorNode
│       │   ├── validation.py            # GraphValidator
│       │   ├── io.py                    # ProjectSerializer (save/load .persistra)
│       │   ├── autosave.py              # AutosaveService
│       │   ├── logging.py               # Logging setup
│       │   └── settings.py              # Application settings (theme, autosave, etc.)
│       │
│       ├── operations/
│       │   ├── __init__.py              # OperationRegistry, auto-discovery
│       │   ├── io/
│       │   │   ├── __init__.py
│       │   │   ├── csv_loader.py
│       │   │   ├── csv_writer.py
│       │   │   ├── manual_data_entry.py
│       │   │   └── data_generator.py
│       │   ├── preprocessing/
│       │   │   ├── __init__.py
│       │   │   ├── normalize.py
│       │   │   ├── differencing.py
│       │   │   ├── returns.py
│       │   │   ├── log_transform.py
│       │   │   ├── log_returns.py
│       │   │   └── rolling_statistics.py
│       │   ├── tda/
│       │   │   ├── __init__.py
│       │   │   ├── sliding_window.py
│       │   │   ├── rips_persistence.py
│       │   │   ├── alpha_persistence.py
│       │   │   ├── cech_persistence.py
│       │   │   ├── cubical_persistence.py
│       │   │   ├── persistence_landscape.py
│       │   │   ├── persistence_image.py
│       │   │   └── diagram_distance.py
│       │   ├── ml/
│       │   │   ├── __init__.py
│       │   │   ├── kmeans.py
│       │   │   ├── pca.py
│       │   │   ├── linear_regression.py
│       │   │   └── logistic_regression.py
│       │   ├── viz/
│       │   │   ├── __init__.py
│       │   │   ├── line_plot.py
│       │   │   ├── scatter_plot.py
│       │   │   ├── histogram.py
│       │   │   ├── persistence_diagram_plot.py
│       │   │   ├── barcode_plot.py
│       │   │   ├── heatmap.py
│       │   │   ├── overlay_plot.py
│       │   │   ├── subplot_grid.py
│       │   │   ├── scatter_3d.py
│       │   │   └── interactive_plot.py
│       │   └── utility/
│       │       ├── __init__.py
│       │       ├── python_expression.py
│       │       ├── column_selector.py
│       │       ├── merge_join.py
│       │       └── export_figure.py
│       │
│       ├── plugins/
│       │   ├── __init__.py
│       │   └── loader.py                # Plugin discovery from ~/.persistra/plugins/
│       │
│       └── ui/
│           ├── __init__.py
│           ├── main_window.py           # MainWindow (assembles all panels)
│           │
│           ├── theme/
│           │   ├── __init__.py          # ThemeManager
│           │   ├── tokens.py            # ThemeTokens dataclass
│           │   ├── dark_modern.py       # VS Code Dark Modern values
│           │   ├── light_modern.py      # VS Code Light Modern values
│           │   └── stylesheets.py       # QSS generation from tokens
│           │
│           ├── menus/
│           │   ├── __init__.py
│           │   ├── menu_bar.py          # File, Edit, View, Help menus
│           │   └── toolbar.py           # Main toolbar
│           │
│           ├── graph/
│           │   ├── __init__.py
│           │   ├── scene.py             # GraphScene (grid, interaction)
│           │   ├── items.py             # NodeItem, SocketItem, WireItem
│           │   ├── manager.py           # GraphManager (controller)
│           │   ├── layout.py            # Auto-layout (Sugiyama algorithm)
│           │   └── clipboard.py         # Copy/paste serialization
│           │
│           ├── widgets/
│           │   ├── __init__.py
│           │   ├── node_browser.py      # Searchable QTreeWidget
│           │   ├── viz_panel.py         # Dynamic QStackedLayout viewer
│           │   ├── context_panel.py     # Tabbed: Parameters, Info, Log
│           │   ├── log_view.py          # Log tab with node filtering
│           │   ├── code_editor.py       # QPlainTextEdit for PythonExpression
│           │   ├── spreadsheet_view.py  # Editable table for ManualDataEntry
│           │   └── matplotlib_view.py   # FigureCanvasQTAgg wrapper
│           │
│           └── dialogs/
│               ├── __init__.py
│               ├── export_figure.py     # Figure export dialog (PNG/SVG/PDF)
│               ├── settings.py          # Settings dialog
│               └── about.py             # About dialog
│
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_types.py
    │   ├── test_objects.py
    │   ├── test_node.py
    │   ├── test_socket.py
    │   ├── test_project.py
    │   ├── test_engine.py
    │   ├── test_serializer.py
    │   ├── test_registry.py
    │   ├── test_plugin_loader.py
    │   ├── test_validation.py
    │   └── operations/
    │       ├── test_csv_loader.py
    │       ├── test_csv_writer.py
    │       ├── test_data_generator.py
    │       ├── test_normalize.py
    │       ├── test_differencing.py
    │       ├── test_returns.py
    │       ├── test_log_transform.py
    │       ├── test_log_returns.py
    │       ├── test_rolling_statistics.py
    │       ├── test_sliding_window.py
    │       ├── test_rips_persistence.py
    │       ├── test_alpha_persistence.py
    │       ├── test_cech_persistence.py
    │       ├── test_cubical_persistence.py
    │       ├── test_persistence_landscape.py
    │       ├── test_persistence_image.py
    │       ├── test_diagram_distance.py
    │       ├── test_kmeans.py
    │       ├── test_pca.py
    │       ├── test_linear_regression.py
    │       ├── test_logistic_regression.py
    │       ├── test_python_expression.py
    │       ├── test_column_selector.py
    │       └── test_merge_join.py
    ├── integration/
    │   ├── test_pipeline_csv_to_plot.py
    │   ├── test_pipeline_tda.py
    │   ├── test_pipeline_ml.py
    │   ├── test_composite_node.py
    │   ├── test_iterator_node.py
    │   ├── test_save_load_roundtrip.py
    │   └── test_autosave.py
    └── ui/
        ├── test_main_window.py
        ├── test_node_browser.py
        ├── test_graph_scene.py
        ├── test_viz_panel.py
        ├── test_context_panel.py
        └── test_theme.py
```

---

## Appendix B — Operations Catalog

Complete catalog of all operations planned for the initial overhaul, organized by category.

### B.1 Input / Output

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 1 | **CSV Loader** | — | `data: TimeSeries` | `filepath: String`, `index_col: String` | *Existing, updated* |
| 2 | **Manual Data Entry** | — | `data: TimeSeries` | (Editable spreadsheet in Viz Panel) | Viz Panel shows `SpreadsheetView` when selected; data stored as a hidden `StringParam` (serialized JSON) |
| 3 | **Data Generator** | — | `data: TimeSeries` | `signal_type: Choice[sine, cosine, white_noise, random_walk, brownian, distribution, sphere]`, `length: Int`, `frequency: Float` (sine/cosine), `amplitude: Float` (sine/cosine), `mean: Float` (noise/distribution), `std: Float` (noise/distribution), `dimensions: Int` (sphere), `seed: Int` | Single node with conditional parameter visibility based on `signal_type` |
| 4 | **CSV Writer** | `data: TimeSeries` | — | `filepath: String`, `include_index: Bool` | Exports a DataFrame to disk; executes as a side-effect operation |

### B.2 Preprocessing

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 5 | **Normalize** | `data: TimeSeries` | `data: TimeSeries` | `method: Choice[min-max, z-score]` | Min-max scales to [0, 1]; z-score centers to mean=0, std=1 |
| 6 | **Differencing** | `data: TimeSeries` | `data: TimeSeries` | `order: Int (default=1, min=1, max=10)` | Applies `df.diff(order)` and drops resulting NaN rows |
| 7 | **Returns** | `data: TimeSeries` | `data: TimeSeries` | — | Simple returns: `(x[t] - x[t-1]) / x[t-1]`; equivalent to `df.pct_change()`; drops first NaN row |
| 8 | **Log Transform** | `data: TimeSeries` | `data: TimeSeries` | `base: Choice[natural, base10]` | Element-wise `np.log()` or `np.log10()`; raises on non-positive values |
| 9 | **Log Returns** | `data: TimeSeries` | `data: TimeSeries` | — | `np.log(x[t] / x[t-1])`; equivalent to `np.log(df / df.shift(1))`; drops first NaN row |
| 10 | **Rolling Statistics** | `data: TimeSeries` | `data: TimeSeries` | `window: Int (default=10)`, `statistic: Choice[mean, std, min, max, sum, median]` | Uses `df.rolling(window).{statistic}()`; drops leading NaN rows |

### B.3 TDA

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 11 | **Sliding Window** | `series: TimeSeries` | `cloud: PointCloud` | `window_size: Int`, `step: Int` | *Existing, updated*. Takens' embedding via NumPy stride tricks |
| 12 | **Rips Persistence** | `cloud: PointCloud` | `diagram: PersistenceDiagram` | `max_dim: Int (default=1)`, `threshold: Float (default=inf)` | *Existing, updated*. Uses `ripser`. Requires `[tda]` extra |
| 13 | **Alpha Persistence** | `cloud: PointCloud` | `diagram: PersistenceDiagram` | `max_dim: Int (default=1)` | Uses `gudhi.AlphaComplex`. Generally faster than Rips for low-dimensional point clouds. Requires `[tda]` extra |
| 14 | **Čech Persistence** | `cloud: PointCloud` | `diagram: PersistenceDiagram` | `max_dim: Int (default=1)`, `max_radius: Float` | Uses `gudhi`. Exact Čech computation; computationally expensive for large inputs. Requires `[tda]` extra |
| 15 | **Cubical Persistence** | `image: DataWrapper` (2D/3D array) | `diagram: PersistenceDiagram` | `max_dim: Int (default=1)` | Uses `gudhi.CubicalComplex`. Designed for grid/image data rather than point clouds. Input socket accepts a 2D or 3D NumPy array wrapped in a `DataWrapper`. Requires `[tda]` extra |
| 16 | **Persistence Landscape** | `diagram: PersistenceDiagram` | `landscape: DataWrapper` (2D array) | `num_landscapes: Int (default=5)`, `resolution: Int (default=100)`, `homology_dim: Int (default=1)` | Vectorization of persistence diagrams into functional summaries. Uses `giotto-tda` or `scikit-tda`. Output is a 2D array of shape `(num_landscapes, resolution)`. Requires `[tda]` extra |
| 17 | **Persistence Image** | `diagram: PersistenceDiagram` | `image: DataWrapper` (2D array) | `resolution: Int (default=20)`, `sigma: Float (default=0.1)`, `homology_dim: Int (default=1)` | Vectorization via Gaussian-weighted pixel grids. Uses `persim.PersistenceImager`. Output is a 2D array of shape `(resolution, resolution)`. Requires `[tda]` extra |
| 18 | **Diagram Distance** | `diagram_a: PersistenceDiagram`, `diagram_b: PersistenceDiagram` | `distance: DataWrapper` (scalar float) | `metric: Choice[wasserstein, bottleneck]`, `homology_dim: Int (default=1)`, `order: Float (default=2.0)` (Wasserstein only) | Computes pairwise distance between two persistence diagrams. Uses `persim.wasserstein` or `persim.bottleneck`. Requires `[tda]` extra |

### B.4 Machine Learning

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 19 | **K-Means Clustering** | `data: DataWrapper` (2D array or DataFrame) | `labels: DataWrapper` (1D array), `centroids: DataWrapper` (2D array) | `n_clusters: Int (default=3, min=2, max=100)`, `max_iter: Int (default=300)`, `random_state: Int (default=42)` | Wraps `sklearn.cluster.KMeans`. Input is unwrapped to a NumPy array. Outputs integer cluster labels and centroid coordinates. Requires `[ml]` extra |
| 20 | **PCA** | `data: DataWrapper` (2D array or DataFrame) | `transformed: DataWrapper` (2D array), `components: DataWrapper` (2D array) | `n_components: Int (default=2, min=1, max=100)` | Wraps `sklearn.decomposition.PCA`. First output is the projected data `(N, n_components)`. Second output is the principal component vectors `(n_components, M)` for inspection. Requires `[ml]` extra |
| 21 | **Linear Regression** | `X: DataWrapper` (2D array or DataFrame), `y: DataWrapper` (1D array or Series) | `predictions: DataWrapper` (1D array), `coefficients: DataWrapper` (1D array), `r_squared: DataWrapper` (scalar float) | — | Wraps `sklearn.linear_model.LinearRegression`. Fits on inputs and returns predictions, fitted coefficients, and R² score. Requires `[ml]` extra |
| 22 | **Logistic Regression** | `X: DataWrapper` (2D array or DataFrame), `y: DataWrapper` (1D array or Series) | `predictions: DataWrapper` (1D array), `probabilities: DataWrapper` (2D array), `accuracy: DataWrapper` (scalar float) | `C: Float (default=1.0, min=0.001, max=1000.0)`, `max_iter: Int (default=100)` | Wraps `sklearn.linear_model.LogisticRegression`. Outputs predicted labels, class probabilities, and accuracy score. Requires `[ml]` extra |

### B.5 Visualization

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 23 | **Line Plot** | `data: TimeSeries` | `plot: FigureWrapper`, `plot_data: PlotData` | `title: String`, `color: String (default="auto")`, `grid: Bool (default=True)`, `line_width: Float (default=1.5)` | *Existing, rewritten*. Dual output: `FigureWrapper` for direct display, `PlotData` for composition |
| 24 | **Scatter Plot** | `data: DataWrapper` (DataFrame with 2+ columns) | `plot: FigureWrapper`, `plot_data: PlotData` | `x_column: String`, `y_column: String`, `color: String (default="auto")`, `point_size: Float (default=20.0)`, `title: String` | Selects two columns for X and Y axes. If `color` is `"auto"`, uses theme accent |
| 25 | **Histogram** | `data: TimeSeries` or `DataWrapper` (numeric) | `plot: FigureWrapper`, `plot_data: PlotData` | `bins: Int (default=30)`, `color: String (default="auto")`, `density: Bool (default=False)`, `title: String` | Single-column histogram. If input has multiple columns, uses the first |
| 26 | **Persistence Diagram Plot** | `diagram: PersistenceDiagram` | `plot: FigureWrapper`, `plot_data: PlotData` | `dimensions: String (default="all")`, `title: String` | *Existing, rewritten*. Uses `persim.plot_diagrams()` if available, falls back to manual scatter + diagonal. `dimensions` can be `"all"`, `"0"`, `"1"`, `"0,1"`, etc. |
| 27 | **Barcode Plot** | `diagram: PersistenceDiagram` | `plot: FigureWrapper`, `plot_data: PlotData` | `dimensions: String (default="all")`, `title: String` | Horizontal bar chart where each bar represents a feature's birth-to-death interval. Separate color per homology dimension |
| 28 | **Heatmap** | `data: DataWrapper` (2D array) or `DistanceMatrix` | `plot: FigureWrapper`, `plot_data: PlotData` | `colormap: Choice[viridis, plasma, inferno, magma, cividis, coolwarm]`, `annotate: Bool (default=False)`, `title: String` | Uses `matplotlib.pyplot.imshow()`. If `annotate` is True, overlays cell values as text |
| 29 | **Overlay Plot** | `plot_data_1: PlotData`, `plot_data_2: PlotData` (expandable to N) | `plot: FigureWrapper` | `title: String`, `show_legend: Bool (default=True)`, `shared_x_label: String`, `shared_y_label: String` | Consumes `PlotData` objects from Tier 1 nodes and re-renders them on shared axes. Initial version supports 2 inputs; architecture supports N via dynamic socket addition |
| 30 | **Subplot Grid** | `figure_1: FigureWrapper`, `figure_2: FigureWrapper` (expandable to N) | `plot: FigureWrapper` | `rows: Int (default=1)`, `cols: Int (default=2)`, `shared_axes: Bool (default=False)`, `figure_width: Float (default=10.0)`, `figure_height: Float (default=6.0)` | Arranges multiple figures into a grid. Creates a new `plt.Figure` with `plt.subplots(rows, cols)` and re-draws each input's content into a subplot cell. Initial version supports up to 4 inputs; expandable |
| 31 | **3D Scatter** | `cloud: PointCloud` or `DataWrapper` (N×3+ array) | `viz: InteractiveFigure` | `x_col: Int (default=0)`, `y_col: Int (default=1)`, `z_col: Int (default=2)`, `point_size: Float (default=5.0)`, `color: String (default="auto")`, `colormap: Choice[viridis, plasma, coolwarm]` | Renders via `pyqtgraph.opengl.GLScatterPlotItem`. If input has 4+ columns, the 4th can be used for color mapping. Viz Panel switches to `PointCloudView` (GLViewWidget) |
| 32 | **Interactive Plot** | `data: TimeSeries` or `DataWrapper` (DataFrame) | `viz: InteractiveFigure` | `plot_type: Choice[line, scatter, bar]`, `title: String` | Renders via Plotly in a `QWebEngineView`. Supports hover tooltips, zoom, pan, and box selection. Requires `[interactive]` extra |

### B.6 Utility

| # | Operation | Inputs | Outputs | Parameters | Notes |
|---|-----------|--------|---------|------------|-------|
| 33 | **Python Expression** | `data: Any (optional)` | `result: Any` | `code: String` (multi-line, edited in Viz Panel code editor) | Full Python access. Pre-injected namespace: `inputs`, `params`, `np`, `pd`. User assigns to `result`. See §6.3.8 for full design |
| 34 | **Column Selector** | `data: TimeSeries` or `DataWrapper` (DataFrame) | `data: TimeSeries` | `columns: String` (comma-separated names or indices) | Parses `columns` parameter: if all values are digits, treats as integer indices; otherwise treats as column names. Returns a new DataFrame with only the selected columns |
| 35 | **Merge / Join** | `left: TimeSeries`, `right: TimeSeries` | `data: TimeSeries` | `how: Choice[inner, outer, left, right]`, `on: String (optional)`, `left_index: Bool (default=False)`, `right_index: Bool (default=False)` | Wraps `pd.merge()`. If `on` is empty and both `left_index`/`right_index` are True, joins on index |
| 36 | **Export Figure** | `figure: FigureWrapper` | — | `filepath: String`, `format: Choice[png, svg, pdf]`, `dpi: Int (default=150)` | Side-effect operation that saves the figure to disk. For `pyqtgraph` `InteractiveFigure` inputs, falls back to widget screenshot via `QWidget.grab()` |

### B.7 Operations Summary

| Category | Count | New | Updated | Requires Extra |
|----------|-------|-----|---------|----------------|
| Input / Output | 4 | 3 | 1 | — |
| Preprocessing | 6 | 6 | — | — |
| TDA | 8 | 6 | 2 | `[tda]` |
| Machine Learning | 4 | 4 | — | `[ml]` |
| Visualization | 10 | 8 | 2 | `[interactive]` (Interactive Plot only) |
| Utility | 4 | 4 | — | — |
| **Total** | **36** | **31** | **5** | |

---

## Appendix C — Theme Color Tokens

The theme system uses a `ThemeTokens` dataclass that defines every color used across the application. Both the QSS stylesheet generator and the node editor's `paint()` methods read from this single source of truth.

### C.1 Token Definitions

```python
from dataclasses import dataclass


@dataclass
class ThemeTokens:
    """Complete set of color and style tokens for a Persistra theme."""

    # --- Global ---
    name: str                          # "dark" or "light"
    foreground: str                    # Primary text color
    foreground_secondary: str          # Secondary/muted text
    background: str                    # Main window background
    background_secondary: str          # Panel/widget background
    background_tertiary: str           # Nested/inset areas
    border: str                        # Default border color
    border_focus: str                  # Focused widget border

    # --- Accent & Semantic ---
    accent: str                        # Primary accent (selection, highlights)
    accent_hover: str                  # Accent on hover
    accent_foreground: str             # Text on accent backgrounds
    error: str                         # Error indicators
    error_foreground: str              # Text on error backgrounds
    warning: str                       # Warning indicators
    success: str                       # Success indicators
    info: str                          # Informational indicators

    # --- Graph Editor ---
    editor_background: str             # Canvas background
    editor_grid: str                   # Fine grid lines
    editor_grid_major: str             # Major grid lines
    node_background: str               # Node body fill
    node_background_selected: str      # Node body when selected
    node_border: str                   # Node border (default)
    node_border_selected: str          # Node border (selected)
    node_border_error: str             # Node border (error state)
    node_text: str                     # Node title and label text
    socket_default: str                # Socket circle fill
    socket_hover: str                  # Socket circle on hover
    wire_default: str                  # Wire color
    wire_draft: str                    # Draft/temporary wire color
    wire_selected: str                 # Wire color when connected nodes selected

    # --- Node Category Header Colors ---
    category_io: str                   # Input / Output
    category_preprocessing: str        # Preprocessing
    category_tda: str                  # TDA
    category_ml: str                   # Machine Learning
    category_viz: str                  # Visualization
    category_utility: str              # Utility
    category_templates: str            # Templates
    category_plugins: str              # Plugins

    # --- Panels ---
    panel_header_background: str       # Panel header bar
    panel_header_foreground: str       # Panel header text

    # --- Node Browser ---
    browser_background: str            # Tree background
    browser_alternate: str             # Alternating row color
    browser_selected: str              # Selected item
    browser_hover: str                 # Hovered item
    browser_text: str                  # Item text

    # --- Context Panel ---
    context_background: str            # Context panel background
    context_header: str                # Header bar background
    context_input_background: str      # Input field backgrounds (spinbox, lineedit)
    context_input_border: str          # Input field borders

    # --- Viz Panel ---
    viz_background: str                # Viz panel background
    viz_tab_active: str                # Active tab indicator
    viz_tab_inactive: str              # Inactive tab background

    # --- Log View ---
    log_background: str                # Log text area background
    log_error: str                     # ERROR level text color
    log_warning: str                   # WARNING level text color
    log_info: str                      # INFO level text color
    log_debug: str                     # DEBUG level text color

    # --- Toolbar & Menu ---
    toolbar_background: str            # Toolbar background
    toolbar_separator: str             # Toolbar separator line
    menu_background: str               # Menu dropdown background
    menu_hover: str                    # Menu item hover
    menu_text: str                     # Menu text

    # --- Scrollbar ---
    scrollbar_background: str          # Scrollbar track
    scrollbar_handle: str              # Scrollbar thumb
    scrollbar_handle_hover: str        # Scrollbar thumb on hover

    # --- Status Bar ---
    statusbar_background: str          # Status bar background
    statusbar_text: str                # Status bar text
```

### C.2 Dark Modern Theme (VS Code–Inspired)

**File:** `src/persistra/ui/theme/dark_modern.py`

```python
from persistra.ui.theme.tokens import ThemeTokens

DARK_MODERN = ThemeTokens(
    # --- Global ---
    name="dark",
    foreground="#CCCCCC",
    foreground_secondary="#8A8A8A",
    background="#1F1F1F",
    background_secondary="#252526",
    background_tertiary="#2D2D2D",
    border="#3E3E42",
    border_focus="#007ACC",

    # --- Accent & Semantic ---
    accent="#007ACC",
    accent_hover="#1A8AD4",
    accent_foreground="#FFFFFF",
    error="#F14C4C",
    error_foreground="#FFFFFF",
    warning="#CCA700",
    success="#89D185",
    info="#3794FF",

    # --- Graph Editor ---
    editor_background="#1E1E1E",
    editor_grid="#2A2A2A",
    editor_grid_major="#1A1A1A",
    node_background="#252526",
    node_background_selected="#2D2D30",
    node_border="#3E3E42",
    node_border_selected="#007ACC",
    node_border_error="#F14C4C",
    node_text="#CCCCCC",
    socket_default="#B0B0B0",
    socket_hover="#FF9800",
    wire_default="#888888",
    wire_draft="#FF9800",
    wire_selected="#007ACC",

    # --- Node Category Header Colors ---
    category_io="#3A7CA5",
    category_preprocessing="#5A8A4A",
    category_tda="#7E5A9F",
    category_ml="#A07030",
    category_viz="#A04545",
    category_utility="#6A6A7A",
    category_templates="#4A9A9A",
    category_plugins="#9A7A4A",

    # --- Panels ---
    panel_header_background="#333333",
    panel_header_foreground="#CCCCCC",

    # --- Node Browser ---
    browser_background="#252526",
    browser_alternate="#2A2A2E",
    browser_selected="#37373D",
    browser_hover="#2E2E33",
    browser_text="#CCCCCC",

    # --- Context Panel ---
    context_background="#252526",
    context_header="#333333",
    context_input_background="#3C3C3C",
    context_input_border="#3E3E42",

    # --- Viz Panel ---
    viz_background="#1E1E1E",
    viz_tab_active="#007ACC",
    viz_tab_inactive="#2D2D2D",

    # --- Log View ---
    log_background="#1E1E1E",
    log_error="#F14C4C",
    log_warning="#CCA700",
    log_info="#CCCCCC",
    log_debug="#6A6A6A",

    # --- Toolbar & Menu ---
    toolbar_background="#2D2D2D",
    toolbar_separator="#3E3E42",
    menu_background="#2D2D30",
    menu_hover="#094771",
    menu_text="#CCCCCC",

    # --- Scrollbar ---
    scrollbar_background="#1E1E1E",
    scrollbar_handle="#424242",
    scrollbar_handle_hover="#4F4F4F",

    # --- Status Bar ---
    statusbar_background="#007ACC",
    statusbar_text="#FFFFFF",
)
```

### C.3 Light Modern Theme (VS Code–Inspired)

**File:** `src/persistra/ui/theme/light_modern.py`

```python
from persistra.ui.theme.tokens import ThemeTokens

LIGHT_MODERN = ThemeTokens(
    # --- Global ---
    name="light",
    foreground="#3B3B3B",
    foreground_secondary="#6E6E6E",
    background="#FFFFFF",
    background_secondary="#F3F3F3",
    background_tertiary="#E8E8E8",
    border="#CECECE",
    border_focus="#005FB8",

    # --- Accent & Semantic ---
    accent="#005FB8",
    accent_hover="#0070D1",
    accent_foreground="#FFFFFF",
    error="#E51400",
    error_foreground="#FFFFFF",
    warning="#BF8803",
    success="#388A34",
    info="#005FB8",

    # --- Graph Editor ---
    editor_background="#F8F8F8",
    editor_grid="#E8E8E8",
    editor_grid_major="#D0D0D0",
    node_background="#FFFFFF",
    node_background_selected="#E8F0FE",
    node_border="#CECECE",
    node_border_selected="#005FB8",
    node_border_error="#E51400",
    node_text="#3B3B3B",
    socket_default="#6E6E6E",
    socket_hover="#E07000",
    wire_default="#999999",
    wire_draft="#E07000",
    wire_selected="#005FB8",

    # --- Node Category Header Colors ---
    category_io="#2E7D9E",
    category_preprocessing="#4E8A3E",
    category_tda="#7E4F9A",
    category_ml="#A0713A",
    category_viz="#A04040",
    category_utility="#5A5A6A",
    category_templates="#3E8A8A",
    category_plugins="#8A6A3E",

    # --- Panels ---
    panel_header_background="#E8E8E8",
    panel_header_foreground="#3B3B3B",

    # --- Node Browser ---
    browser_background="#F3F3F3",
    browser_alternate="#ECECEC",
    browser_selected="#CCE4F7",
    browser_hover="#E0E0E0",
    browser_text="#3B3B3B",

    # --- Context Panel ---
    context_background="#F3F3F3",
    context_header="#E8E8E8",
    context_input_background="#FFFFFF",
    context_input_border="#CECECE",

    # --- Viz Panel ---
    viz_background="#FFFFFF",
    viz_tab_active="#005FB8",
    viz_tab_inactive="#E8E8E8",

    # --- Log View ---
    log_background="#FFFFFF",
    log_error="#E51400",
    log_warning="#BF8803",
    log_info="#3B3B3B",
    log_debug="#999999",

    # --- Toolbar & Menu ---
    toolbar_background="#F3F3F3",
    toolbar_separator="#CECECE",
    menu_background="#F3F3F3",
    menu_hover="#CCE4F7",
    menu_text="#3B3B3B",

    # --- Scrollbar ---
    scrollbar_background="#F3F3F3",
    scrollbar_handle="#C1C1C1",
    scrollbar_handle_hover="#A0A0A0",

    # --- Status Bar ---
    statusbar_background="#005FB8",
    statusbar_text="#FFFFFF",
)
```

### C.4 QSS Stylesheet Generation

**File:** `src/persistra/ui/theme/stylesheets.py`

The stylesheet generator takes a `ThemeTokens` instance and produces a complete QSS string that is applied globally via `QApplication.setStyleSheet()`. This ensures every standard Qt widget and all custom-styled widgets use consistent colors.

```python
from persistra.ui.theme.tokens import ThemeTokens


def generate_stylesheet(tokens: ThemeTokens) -> str:
    """Generate a complete QSS stylesheet from theme tokens."""
    return f"""
    /* === Global === */
    QWidget {{
        background-color: {tokens.background};
        color: {tokens.foreground};
        font-family: "Segoe UI", "SF Pro", "Helvetica Neue", sans-serif;
        font-size: 13px;
    }}

    /* === Main Window === */
    QMainWindow {{
        background-color: {tokens.background};
    }}

    /* === Menu Bar === */
    QMenuBar {{
        background-color: {tokens.toolbar_background};
        color: {tokens.menu_text};
        border-bottom: 1px solid {tokens.border};
        padding: 2px;
    }}
    QMenuBar::item:selected {{
        background-color: {tokens.menu_hover};
    }}
    QMenu {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        border: 1px solid {tokens.border};
    }}
    QMenu::item:selected {{
        background-color: {tokens.menu_hover};
    }}
    QMenu::separator {{
        height: 1px;
        background: {tokens.border};
        margin: 4px 8px;
    }}

    /* === Toolbar === */
    QToolBar {{
        background-color: {tokens.toolbar_background};
        border-bottom: 1px solid {tokens.border};
        spacing: 4px;
        padding: 2px;
    }}
    QToolBar::separator {{
        width: 1px;
        background: {tokens.toolbar_separator};
        margin: 4px 2px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px;
        color: {tokens.foreground};
    }}
    QToolButton:hover {{
        background-color: {tokens.menu_hover};
        border: 1px solid {tokens.border};
    }}
    QToolButton:pressed {{
        background-color: {tokens.accent};
        color: {tokens.accent_foreground};
    }}

    /* === Status Bar === */
    QStatusBar {{
        background-color: {tokens.statusbar_background};
        color: {tokens.statusbar_text};
        border-top: 1px solid {tokens.border};
    }}

    /* === Tab Widget === */
    QTabWidget::pane {{
        border: 1px solid {tokens.border};
        background-color: {tokens.background_secondary};
    }}
    QTabBar::tab {{
        background-color: {tokens.viz_tab_inactive};
        color: {tokens.foreground_secondary};
        border: 1px solid {tokens.border};
        padding: 6px 12px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {tokens.background_secondary};
        color: {tokens.foreground};
        border-bottom: 2px solid {tokens.viz_tab_active};
    }}
    QTabBar::tab:hover {{
        background-color: {tokens.menu_hover};
    }}

    /* === Tree Widget (Node Browser) === */
    QTreeWidget {{
        background-color: {tokens.browser_background};
        alternate-background-color: {tokens.browser_alternate};
        color: {tokens.browser_text};
        border: 1px solid {tokens.border};
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 4px 8px;
    }}
    QTreeWidget::item:selected {{
        background-color: {tokens.browser_selected};
        color: {tokens.foreground};
    }}
    QTreeWidget::item:hover {{
        background-color: {tokens.browser_hover};
    }}
    QTreeWidget::branch {{
        background-color: {tokens.browser_background};
    }}

    /* === List Widget (Recent Projects) === */
    QListWidget {{
        background-color: {tokens.browser_background};
        alternate-background-color: {tokens.browser_alternate};
        color: {tokens.browser_text};
        border: 1px solid {tokens.border};
    }}
    QListWidget::item {{
        padding: 6px 8px;
    }}
    QListWidget::item:selected {{
        background-color: {tokens.browser_selected};
    }}
    QListWidget::item:hover {{
        background-color: {tokens.browser_hover};
    }}

    /* === Table View === */
    QTableView {{
        background-color: {tokens.background_secondary};
        alternate-background-color: {tokens.background_tertiary};
        color: {tokens.foreground};
        gridline-color: {tokens.border};
        border: 1px solid {tokens.border};
        selection-background-color: {tokens.accent};
        selection-color: {tokens.accent_foreground};
    }}
    QHeaderView::section {{
        background-color: {tokens.panel_header_background};
        color: {tokens.panel_header_foreground};
        border: 1px solid {tokens.border};
        padding: 4px 8px;
        font-weight: bold;
    }}

    /* === Scroll Area === */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    /* === Scrollbar === */
    QScrollBar:vertical {{
        background: {tokens.scrollbar_background};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {tokens.scrollbar_handle};
        min-height: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {tokens.scrollbar_handle_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {tokens.scrollbar_background};
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {tokens.scrollbar_handle};
        min-width: 30px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {tokens.scrollbar_handle_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* === Input Widgets === */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {tokens.context_input_background};
        color: {tokens.foreground};
        border: 1px solid {tokens.context_input_border};
        border-radius: 3px;
        padding: 4px 6px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {tokens.border_focus};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        selection-background-color: {tokens.menu_hover};
        border: 1px solid {tokens.border};
    }}

    /* === Plain Text Edit (Log, Code Editor) === */
    QPlainTextEdit {{
        background-color: {tokens.log_background};
        color: {tokens.foreground};
        border: 1px solid {tokens.border};
        font-family: "Cascadia Code", "Consolas", "Fira Code", monospace;
        font-size: 12px;
    }}

    /* === Labels === */
    QLabel {{
        background-color: transparent;
        color: {tokens.foreground};
    }}

    /* === Push Button === */
    QPushButton {{
        background-color: {tokens.accent};
        color: {tokens.accent_foreground};
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {tokens.accent_hover};
    }}
    QPushButton:pressed {{
        background-color: {tokens.accent};
    }}
    QPushButton:disabled {{
        background-color: {tokens.background_tertiary};
        color: {tokens.foreground_secondary};
    }}

    /* === Checkbox === */
    QCheckBox {{
        color: {tokens.foreground};
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {tokens.border};
        border-radius: 3px;
        background-color: {tokens.context_input_background};
    }}
    QCheckBox::indicator:checked {{
        background-color: {tokens.accent};
        border-color: {tokens.accent};
    }}

    /* === Group Box === */
    QGroupBox {{
        border: 1px solid {tokens.border};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 16px;
        color: {tokens.foreground};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}

    /* === Splitter === */
    QSplitter::handle {{
        background-color: {tokens.border};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QSplitter::handle:vertical {{
        height: 2px;
    }}

    /* === Tooltip === */
    QToolTip {{
        background-color: {tokens.menu_background};
        color: {tokens.menu_text};
        border: 1px solid {tokens.border};
        padding: 4px;
    }}
    """
```

### C.5 ThemeManager Implementation

**File:** `src/persistra/ui/theme/__init__.py`

```python
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from persistra.ui.theme.tokens import ThemeTokens
from persistra.ui.theme.dark_modern import DARK_MODERN
from persistra.ui.theme.light_modern import LIGHT_MODERN
from persistra.ui.theme.stylesheets import generate_stylesheet

SETTINGS_PATH = Path.home() / ".persistra" / "settings.json"

THEMES = {
    "dark": DARK_MODERN,
    "light": LIGHT_MODERN,
}


class ThemeManager(QObject):
    """
    Singleton manager for application theming.
    Emits `theme_changed` when the theme is toggled so that custom-painted
    widgets (e.g., NodeItem, GraphScene) can refresh their colors.
    """
    theme_changed = Signal(str)  # Emits the new theme name

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        super().__init__()
        self._initialized = True
        self.current_theme = self._load_preference()
        self.current_tokens: ThemeTokens = THEMES[self.current_theme]

    def apply(self):
        """Apply the current theme's stylesheet to the entire application."""
        app = QApplication.instance()
        if app:
            stylesheet = generate_stylesheet(self.current_tokens)
            app.setStyleSheet(stylesheet)

    def toggle(self):
        """Switch between dark and light themes."""
        if self.current_theme == "dark":
            self.current_theme = "light"
        else:
            self.current_theme = "dark"

        self.current_tokens = THEMES[self.current_theme]
        self.apply()
        self._save_preference()
        self.theme_changed.emit(self.current_theme)

    def get_category_color(self, category: str) -> str:
        """Return the header color for a given operation category."""
        mapping = {
            "Input / Output": self.current_tokens.category_io,
            "Preprocessing": self.current_tokens.category_preprocessing,
            "TDA": self.current_tokens.category_tda,
            "Machine Learning": self.current_tokens.category_ml,
            "Visualization": self.current_tokens.category_viz,
            "Utility": self.current_tokens.category_utility,
            "Templates": self.current_tokens.category_templates,
            "Plugins": self.current_tokens.category_plugins,
        }
        return mapping.get(category, self.current_tokens.category_utility)

    def _load_preference(self) -> str:
        """Load saved theme preference, defaulting to 'dark'."""
        try:
            if SETTINGS_PATH.exists():
                settings = json.loads(SETTINGS_PATH.read_text())
                return settings.get("theme", "dark")
        except (json.JSONDecodeError, OSError):
            pass
        return "dark"

    def _save_preference(self):
        """Persist theme preference to settings file."""
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            settings = {}
            if SETTINGS_PATH.exists():
                settings = json.loads(SETTINGS_PATH.read_text())
            settings["theme"] = self.current_theme
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        except (json.JSONDecodeError, OSError):
            pass
```

### C.6 Usage in Custom-Painted Widgets

For widgets that use `QPainter` directly (e.g., `NodeItem`, `GraphScene`, `SocketItem`, `WireItem`), colors are read from `ThemeManager` at paint time rather than from hardcoded values:

```python
# Example: NodeItem.paint() reading from ThemeManager
from persistra.ui.theme import ThemeManager


class NodeItem(QGraphicsItem):
    def paint(self, painter, option, widget):
        tm = ThemeManager()
        tokens = tm.current_tokens

        # Node body
        if self.isSelected():
            painter.setPen(QPen(QColor(tokens.node_border_selected), 2))
            painter.setBrush(QBrush(QColor(tokens.node_background_selected)))
        elif self._has_error:
            painter.setPen(QPen(QColor(tokens.node_border_error), 2))
            painter.setBrush(QBrush(QColor(tokens.node_background)))
        else:
            painter.setPen(QPen(QColor(tokens.node_border), 1))
            painter.setBrush(QBrush(QColor(tokens.node_background)))

        # ... draw body ...

        # Node header (colored by category)
        category = self.node_data.operation.category
        header_color = tm.get_category_color(category)
        painter.setBrush(QBrush(QColor(header_color)))

        # ... draw header ...

        # Text
        painter.setPen(QColor(tokens.node_text))
        # ... draw labels ...
```

Widgets connect to `ThemeManager.theme_changed` to trigger repaints:

```python
class GraphScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        tm = ThemeManager()
        tm.theme_changed.connect(self._on_theme_changed)
        self._apply_theme()

    def _on_theme_changed(self, theme_name):
        self._apply_theme()
        self.update()  # Triggers full repaint

    def _apply_theme(self):
        tm = ThemeManager()
        self.setBackgroundBrush(QColor(tm.current_tokens.editor_background))
```

---
