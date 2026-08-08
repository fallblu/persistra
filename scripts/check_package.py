"""Install the built wheel in a clean environment and smoke-test public imports."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

IMPORT_SMOKE = """\
import persistra
import persistra.analysis
import persistra.data
import persistra.errors
import persistra.model
import persistra.portfolio
import persistra.viz
assert persistra.__version__
"""


def main() -> None:
    """Install exactly one current wheel without development dependencies."""
    document = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version = document["project"]["version"]
    wheels = sorted(Path("dist").glob(f"persistra-{version}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one built wheel, found {len(wheels)}")
    wheel = wheels[0].resolve()
    with tempfile.TemporaryDirectory(prefix="persistra-package-check-") as directory:
        environment = Path(directory) / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(environment)],
            check=True,
        )
        python = environment / "bin" / "python"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)],
            check=True,
        )
        subprocess.run(
            [str(python), "-c", IMPORT_SMOKE],
            check=True,
            cwd=directory,
        )


if __name__ == "__main__":
    main()
