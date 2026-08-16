"""Install the built wheel in a clean environment and smoke-test public imports."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

PUBLIC_TOP_LEVEL_NAMESPACES = (
    "persistra",
    "persistra.analysis",
    "persistra.data",
    "persistra.errors",
    "persistra.integrations",
    "persistra.model",
    "persistra.portfolio",
    "persistra.research",
    "persistra.viz",
)


def source_top_level_namespaces(package: Path = Path("src/persistra")) -> tuple[str, ...]:
    """Return the public top-level namespaces present in the source package."""
    namespaces = {"persistra"}
    for path in package.iterdir():
        if path.name.startswith("_"):
            continue
        if path.is_dir() and (path / "__init__.py").is_file():
            namespaces.add(f"persistra.{path.name}")
        elif path.is_file() and path.suffix == ".py":
            namespaces.add(f"persistra.{path.stem}")
    return tuple(sorted(namespaces))


def installed_smoke_program(expected_version: str) -> str:
    """Return an isolated smoke program for one installed distribution."""
    return f"""\
from importlib import import_module, metadata, resources
from pathlib import Path
import pkgutil
import sys

namespaces = {PUBLIC_TOP_LEVEL_NAMESPACES!r}
for namespace in namespaces:
    import_module(namespace)

persistra = import_module("persistra")
expected_version = {expected_version!r}
assert persistra.__version__ == expected_version
assert metadata.version("persistra") == expected_version
assert resources.files("persistra").joinpath("py.typed").is_file()
assert Path(persistra.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())

expected_children = {{namespace.removeprefix("persistra.") for namespace in namespaces[1:]}}
installed_children = {{
    module.name
    for module in pkgutil.iter_modules(persistra.__path__)
    if not module.name.startswith("_")
}}
assert installed_children == expected_children
"""


def main() -> None:
    """Install exactly one current wheel without development dependencies."""
    document = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version = document["project"]["version"]
    if not isinstance(version, str):
        raise SystemExit("project version must be a string")
    source_namespaces = source_top_level_namespaces()
    if source_namespaces != PUBLIC_TOP_LEVEL_NAMESPACES:
        raise SystemExit(
            "public package smoke namespaces differ from source: "
            f"declared {PUBLIC_TOP_LEVEL_NAMESPACES!r}; found {source_namespaces!r}"
        )
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
            [str(python), "-I", "-c", installed_smoke_program(version)],
            check=True,
            cwd=directory,
        )


if __name__ == "__main__":
    main()
