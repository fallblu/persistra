"""Execute the maintained notebooks without network access."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

NOTEBOOKS = (
    Path("docs/notebooks/01-cross-asset.ipynb"),
    Path("docs/notebooks/02-historical-options.ipynb"),
)

NETWORK_GUARD = """\
import socket

def _persistra_no_network(*args, **kwargs):
    raise RuntimeError("network access is disabled for documentation notebooks")

socket.create_connection = _persistra_no_network
socket.socket.connect = _persistra_no_network
"""


def main() -> None:
    """Execute clean copies of both notebooks in isolated kernels."""
    for path in NOTEBOOKS:
        notebook = nbformat.read(path, as_version=4)
        for cell in notebook.cells:
            if cell.cell_type == "code" and (cell.outputs or cell.execution_count is not None):
                raise SystemExit(f"{path}: committed code cells must not contain outputs")
        notebook.cells.insert(0, nbformat.v4.new_code_cell(NETWORK_GUARD))
        client = NotebookClient(
            notebook,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(Path.cwd())}},
        )
        client.execute()


if __name__ == "__main__":
    main()
