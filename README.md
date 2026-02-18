# Persistra

**An experimental data analysis tool.**

Persistra is a node-based visual environment that allows researchers and quantitative analysts to build data pipelines visually. Users can connect data sources, transformation algorithms, and visualizations without writing code for every experiment.

![Persistra Screenshot](docs/screenshot.png)
*(Screenshot coming soon)*

## Features

* **Node-Based Interface:** Drag-and-drop operations to create visual data flows.
* **Lazy Evaluation:** Efficient computation engine that only recalculates nodes when upstream data or parameters change.
* **Interactive Visualization:** View Time Series and Persistence Diagrams directly within the application.

## Installation

### Prerequisites
* Python 3.11 or higher

### Installing from Source
1.  Clone the repository:
    ```bash
    git clone [https://github.com/yourusername/persistra.git](https://github.com/yourusername/persistra.git)
    cd persistra
    ```

2.  Install the package dependencies:
    ```bash
    pip install .
    ```

## Usage

To launch the application, simply run the installed command:

```bash
persistra
```

Alternatively, you can run it as a module:

```bash
python -m persistra
```

### Basic Workflow

1. **Load Data:** Drag a `CSV Loader` node onto the canvas and select your dataset.
2. **Transform:** Connect it to a `Sliding Window` node to generate a point cloud.
3. **Analyze:** Connect the point cloud to a `Rips Persistence` node to compute homology.
4. **Visualize:** Output the results to a `Persistence Plot` node to view the diagram in the Viz Panel.

## Project Structure

* `src/persistra/core`: The graph model, node logic, and data wrappers.
* `src/persistra/operations`: The library of available tools (IO, TDA, Visualization).
* `src/persistra/ui`: The PyQt/PySide6 graphical user interface.

## License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

## Contact

**James Mallette** Email: jamesmallmw@gmail.com
