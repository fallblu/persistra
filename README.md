# Persistra: Implementation Plan

## 1. Project Overview

**Persistra** is a node-based visual analysis tool designed for quantitative financial research and Topological Data Analysis (TDA). It enables users to build data pipelines visually, connecting data sources, transformation algorithms, and visualizations without writing code for every experiment.

---

## 2. Architecture & Design Patterns

### 2.1 Architectural Style: MVC with a Graph Model

We utilize a strict **Model-View-Controller (MVC)** pattern to decouple the mathematical core from the GUI.

* **The Model (Core):** Pure Python classes (`Project`, `Node`, `Socket`) that define the data topology. These rely on **Composition** (generic Nodes holding specific `Operation` logic) and have **zero** dependencies on Qt.
* **The View (GUI):** A `QGraphicsScene` visualization of the graph. Nodes are rendered as generic boxes; their specific "Type" is visual metadata derived from the Model.
* **The Controller (Logic):** A `GraphManager` that mediates between the Model and View. It handles connection validation, parameter updates, and orchestrates the execution flow.

### 2.2 Execution Flow: The "Pull" System with Background Workers

Data flow is **lazy**, **event-driven**, and **asynchronous**.

1.  **Invalidation (Push):**
    * **Structural Change:** Connecting/Disconnecting wires marks the downstream chain as `dirty`.
    * **Parameter Change:** Editing a value in the *Context Panel* marks the specific Node as `dirty` and propagates invalidation downstream.
2.  **Computation (Pull):**
    * **Trigger:** The user explicitly requests a result (e.g., viewing a plot in the *Viz Panel*).
    * **Execution:** The Controller spawns a `QThread` (Worker). The Worker calls `node.compute()`, which recursively pulls data from upstream.
    * **UI State:** The GUI remains responsive but displays a "Computing..." spinner/status until the Worker emits a `finished` signal.

---

## 3. The Core Model (Back-End)

**Status:** *Implemented & Tested*
**Location:** `src/persistra/core/`

### 3.1 Class Hierarchy

1.  **`Project`**: The root container.
    * *Role:* Holds the list of all `Node` instances.
    * *Serialization:* Uses standard `pickle` to save/load `.pstra` files.

2.  **`Node` (Generic Container)**:
    * *Role:* A wrapper for an `Operation`. It manages the input/output sockets, parameter state, and caching (`_cached_outputs`).
    * *Identity:* A Node is defined by the `Operation` class it instantiates (e.g., "This Node holds a `CSVLoader` operation").

3.  **`Operation` (The Logic)**:
    * *Role:* Abstract base class for all functionality.
    * *Responsibility:* Defines `inputs` (names/types), `outputs` (names/types), `parameters` (list of `Parameter` objects), and the `execute()` method.

4.  **`DataWrapper` (The Currency)**:
    * *Role:* Wraps raw data to ensure type safety at Sockets.
    * *Types:*
        * `TimeSeries` (wraps `pandas.DataFrame`)
        * `DistanceMatrix` (wraps `numpy.ndarray`)
        * `PersistenceDiagram` (wraps list of tuples)
        * `FigureWrapper` (wraps `matplotlib.figure.Figure` for visualization)

---

## 4. User Interface (Front-End)

**Status:** *Pending Implementation*

### 4.1 Layout Strategy

**Static Grid Layout:** 16x10 Units (Target Aspect Ratio: 1.6:1).

| Section | Location | Dimensions | Responsibility |
| :--- | :--- | :--- | :--- |
| **Node Browser** | Top-Left | 6W x 4H | Lists available Operations. Allows Drag-and-Drop onto the Canvas. |
| **Graph Editor** | Bottom-Left | 6W x 6H | The primary workspace. Pan/Zoom enabled. |
| **Viz Panel** | Top-Right | 10W x 6H | Tabbed view. Displays results (Plots or Data Tables) of the *selected* node. |
| **Context Panel** | Bottom-Right | 10W x 4H | Displays parameters for the *selected* node. Changes dynamically. |

### 4.2 The Graph Editor Engine (`src/persistra/ui/graph/`)

We will build a custom `QGraphicsView` implementation.

* **`GraphScene(QGraphicsScene)`**:
    * Draws an infinite grid background.
    * Handles "Draft Wire" interaction (drawing a line from a socket to the mouse cursor).
* **`NodeItem(QGraphicsItem)`**:
    * Generic visual representation.
    * Dynamic height based on the number of sockets.
    * **Interaction:** Clicking selects the node -> Controller updates *Context Panel* & *Viz Panel*.
* **`WireItem(QGraphicsPathItem)`**:
    * Cubic Bezier curve connecting two sockets.
    * Updates automatically when nodes move.

### 4.3 Key UI Components

1.  **Context Panel (The Inspector):**
    * Listens for `selectionChanged` signals from the Scene.
    * Iterates through `node.operation.parameters`.
    * **Factory Pattern:** Generates correct widget (`QSpinBox` for `IntParam`, `QComboBox` for `ChoiceParam`) automatically.
    * **Two-Way Binding:** Editing a widget immediately calls `node.set_parameter()`.

2.  **Viz Panel (The Viewer):**
    * **Tab 1: Plot Viewer:** Embeds a `FigureCanvasQTAgg`. Active if the selected node outputs a `FigureWrapper`.
    * **Tab 2: Table Viewer:** Embeds a `QTableView` with a generic `PandasModel`. Active if the selected node outputs `TimeSeries` or `DistanceMatrix`.

---

## 5. Operations Registry

**Status:** *Implemented & Tested*
**Location:** `src/persistra/operations/`

We have implemented a registry system that allows the UI to dynamically discover available tools.

### 5.1 MVP Operation List

**Source:**
* **`CSVLoader`**: Reads `.csv` files into `TimeSeries`.
    * *Params:* File Path (String), Index Column (String/Int).

**Transformation:**
* **`SlidingWindow`**: Converts `TimeSeries` -> `PointCloud`.
    * *Params:* Window Size (Int), Step (Int).
* **`RipsPersistence`**: Converts `PointCloud` -> `PersistenceDiagram`.
    * *Params:* Max Dimension (Int), Threshold (Float).

**Visualization:**
* **`PersistencePlot`**: Converts `PersistenceDiagram` -> `FigureWrapper`.
    * *Params:* Style (Choice: Scatter/Barcode).
* **`LinePlot`**: Converts `TimeSeries` -> `FigureWrapper`.
    * *Params:* (None for MVP).

---

## 6. Directory Structure

```text
persistra/
├── pyproject.toml              # Build config
├── src/
│   └── persistra/
│       ├── __init__.py
│       ├── __main__.py
│       ├── core/               # [IMPLEMENTED]
│       │   ├── __init__.py
│       │   ├── project.py      # Project, Node, Socket classes
│       │   ├── objects.py      # DataWrapper, Parameter definitions
│       │   └── io.py           # Pickle logic
│       │
│       ├── operations/         # [IMPLEMENTED]
│       │   ├── __init__.py     # Registry (list of active Operations)
│       │   ├── io.py           # CSVLoader, etc.
│       │   ├── tda.py          # Rips, SlidingWindow logic
│       │   └── viz.py          # Plotting logic
│       │
│       └── ui/                 # [NEXT STEP]
│           ├── __init__.py
│           ├── main_window.py
│           ├── widgets/          
│           │   ├── __init__.py
│           │   ├── context_panel.py  # Parameter Inspector
│           │   ├── viz_panel.py      # Plot/Table Viewer
│           │   ├── node_browser.py   # Drag-and-drop list
│           │   └── canvas.py         # The QGraphicsView wrapper
│           └── graph/          
│               ├── __init__.py
│               ├── scene.py
│               ├── items.py          # NodeItem, WireItem
│               ├── manager.py        # Controller (Connection Logic)
│               └── worker.py         # QThread for background compute
└── tests/                      # [IMPLEMENTED]
    ├── test_core.py            # Graph logic tests
    └── test_operations.py      # Math/IO tests
