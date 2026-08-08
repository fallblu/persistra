"""Execute output-free study notebooks without saving provider-derived results."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import nbformat
from check_studies import EXPECTED_NOTEBOOKS, check_notebook
from nbclient import NotebookClient


def main() -> None:
    """Execute selected notebooks in memory and report status only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "notebooks",
        nargs="*",
        choices=EXPECTED_NOTEBOOKS,
        help="notebook filenames; omit to execute the complete suite",
    )
    parser.add_argument("--timeout", type=int, default=600, help="per-cell timeout in seconds")
    arguments = parser.parse_args()
    os.environ.setdefault("MPLBACKEND", "Agg")
    root = Path(__file__).resolve().parents[1]
    selected = tuple(arguments.notebooks) or EXPECTED_NOTEBOOKS
    previous_temp_root = os.environ.get("PERSISTRA_STUDY_TEMP_ROOT")
    try:
        with TemporaryDirectory(prefix="persistra-study-suite-") as temporary_root:
            os.environ["PERSISTRA_STUDY_TEMP_ROOT"] = temporary_root
            for name in selected:
                path = root / "studies" / name
                failures = check_notebook(path)
                if failures:
                    raise SystemExit("\n".join(failures))
                notebook = nbformat.read(path, as_version=4)
                client = NotebookClient(
                    notebook,
                    timeout=arguments.timeout,
                    startup_timeout=120,
                    kernel_name="python3",
                    allow_errors=False,
                    store_widget_state=False,
                    resources={"metadata": {"path": str(root)}},
                )
                client.execute()
                print(f"{name}: passed")
    finally:
        if previous_temp_root is None:
            os.environ.pop("PERSISTRA_STUDY_TEMP_ROOT", None)
        else:
            os.environ["PERSISTRA_STUDY_TEMP_ROOT"] = previous_temp_root


if __name__ == "__main__":
    main()
