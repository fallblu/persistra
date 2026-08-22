"""Verify wheel boundaries, source-distribution policy, and clean installations."""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from email.message import Message

PUBLIC_TOP_LEVEL_NAMESPACES = (
    "persistra",
    "persistra.analysis",
    "persistra.data",
    "persistra.errors",
    "persistra.integrations",
    "persistra.model",
    "persistra.portfolio",
    "persistra.project",
    "persistra.research",
    "persistra.validation",
    "persistra.viz",
)

CORE_TOP_LEVEL_NAMESPACES = tuple(
    namespace for namespace in PUBLIC_TOP_LEVEL_NAMESPACES if namespace != "persistra.viz"
)

SDIST_ROOT_FILES = {
    ".gitignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "Makefile",
    "PKG-INFO",
    "README.md",
    "mkdocs.yml",
    "pyproject.toml",
    "uv.lock",
}
SDIST_DIRECTORY_PREFIXES = ("docs/", "scripts/", "src/", "tests/")

EXPECTED_PROJECT_URLS = {
    "Changelog": "https://github.com/fallblu/persistra/blob/main/CHANGELOG.md",
    "Documentation": "https://fallblu.github.io/persistra/",
    "Homepage": "https://fallblu.github.io/persistra/",
    "Issues": "https://github.com/fallblu/persistra/issues",
    "Source": "https://github.com/fallblu/persistra",
}


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


def installed_smoke_program(expected_version: str, extra: str | None) -> str:
    """Return an isolated smoke program for one installed dependency boundary."""
    return f"""\
from contextlib import redirect_stdout
from importlib import import_module, metadata, resources
from io import StringIO
from pathlib import Path
import json
import pkgutil
import sys
import tempfile

core_namespaces = {CORE_TOP_LEVEL_NAMESPACES!r}
all_namespaces = {PUBLIC_TOP_LEVEL_NAMESPACES!r}
for namespace in core_namespaces:
    import_module(namespace)

persistra = import_module("persistra")
expected_version = {expected_version!r}
assert persistra.__version__ == expected_version
assert metadata.version("persistra") == expected_version
assert resources.files("persistra").joinpath("py.typed").is_file()
assert Path(persistra.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())

expected_children = {{namespace.removeprefix("persistra.") for namespace in all_namespaces[1:]}}
installed_children = {{
    module.name
    for module in pkgutil.iter_modules(persistra.__path__)
    if not module.name.startswith("_")
}}
assert installed_children == expected_children

extra = {extra!r}
if extra is None:
    cli = import_module("persistra._cli")
    data = import_module("persistra.data")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        data.DuckDBStore.create(directory / "data.duckdb").close()
        output = StringIO()
        with redirect_stdout(output):
            status = cli.run(["inspect", str(directory), "--list", "--json"])
        inventory = json.loads(output.getvalue())
        assert status == 0
        assert inventory["inventory_version"] == 1
        assert inventory["store_count"] == 1
    try:
        import_module("persistra.viz")
    except ImportError as error:
        assert "install persistra[viz]" in str(error)
    else:
        raise AssertionError("base installation imported persistra.viz")
    for distribution in ("plotly", "pillow", "panel"):
        try:
            metadata.version(distribution)
        except metadata.PackageNotFoundError:
            pass
        else:
            raise AssertionError(f"base installation included {{distribution}}")
elif extra == "viz":
    import_module("persistra.viz")
    metadata.version("plotly")
    for distribution in ("pillow", "panel"):
        try:
            metadata.version(distribution)
        except metadata.PackageNotFoundError:
            pass
        else:
            raise AssertionError(f"visualization installation included {{distribution}}")
elif extra == "inspect":
    import_module("persistra.viz")
    import_module("persistra._inspection")
    import_module("panel")
    for distribution in ("plotly", "pillow", "panel"):
        metadata.version(distribution)
else:
    raise AssertionError(f"unsupported smoke extra: {{extra}}")
"""


def sdist_files(archive_path: Path) -> tuple[str, ...]:
    """Return safe relative file names from one standard single-root sdist."""
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
    roots = {member.name.split("/", 1)[0] for member in members}
    if len(roots) != 1:
        raise ValueError(f"sdist must have one root directory, found {sorted(roots)!r}")
    root = roots.pop()
    files: list[str] = []
    for member in members:
        if member.issym() or member.islnk():
            raise ValueError(f"sdist must not contain links: {member.name}")
        if not member.isfile():
            continue
        prefix = f"{root}/"
        if not member.name.startswith(prefix):
            raise ValueError(f"sdist member leaves its root: {member.name}")
        files.append(member.name.removeprefix(prefix))
    return tuple(sorted(files))


def validate_sdist_policy(files: tuple[str, ...]) -> None:
    """Require the documented source, verification, test, and documentation scope."""
    unexpected = sorted(
        path
        for path in files
        if path not in SDIST_ROOT_FILES
        and not any(path.startswith(prefix) for prefix in SDIST_DIRECTORY_PREFIXES)
    )
    if unexpected:
        raise ValueError(f"sdist contains files outside policy: {unexpected!r}")
    missing_roots = sorted(SDIST_ROOT_FILES - set(files))
    if missing_roots:
        raise ValueError(f"sdist is missing required root files: {missing_roots!r}")
    for prefix in SDIST_DIRECTORY_PREFIXES:
        if not any(path.startswith(prefix) for path in files):
            raise ValueError(f"sdist is missing required content under {prefix}")


def wheel_files(wheel: Path) -> tuple[str, ...]:
    """Return normalized member names from one wheel."""
    with zipfile.ZipFile(wheel) as archive:
        return tuple(sorted(archive.namelist()))


def wheel_metadata(wheel: Path) -> Message:
    """Read the one Core Metadata document from a wheel."""
    with zipfile.ZipFile(wheel) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(candidates) != 1:
            raise ValueError(f"wheel must contain one METADATA file, found {len(candidates)}")
        content = archive.read(candidates[0])
    return BytesParser(policy=default).parsebytes(content)


def sdist_metadata(sdist: Path) -> Message:
    """Read the one Core Metadata document from a source distribution."""
    with tarfile.open(sdist, mode="r:gz") as archive:
        candidates = [
            member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
        ]
        if len(candidates) != 1:
            raise ValueError(f"sdist must contain one PKG-INFO file, found {len(candidates)}")
        extracted = archive.extractfile(candidates[0])
        if extracted is None:
            raise ValueError("could not read sdist PKG-INFO")
        content = extracted.read()
    return BytesParser(policy=default).parsebytes(content)


def validate_distribution_metadata(
    metadata: Message,
    archive_files: tuple[str, ...],
    *,
    wheel: bool,
) -> None:
    """Validate modern license, project URL, and rendered README metadata."""
    label = "wheel" if wheel else "sdist"
    metadata_version = metadata.get("Metadata-Version", "")
    try:
        parsed_metadata_version = tuple(int(part) for part in metadata_version.split("."))
    except ValueError as error:
        raise ValueError(f"{label} has an invalid Core Metadata version") from error
    if parsed_metadata_version < (2, 4):
        raise ValueError(f"{label} must use Core Metadata 2.4 or later")
    if metadata.get("License-Expression") != "MIT" or metadata.get("License") is not None:
        raise ValueError(f"{label} must declare only License-Expression: MIT")
    if metadata.get_all("License-File", []) != ["LICENSE"]:
        raise ValueError(f"{label} must declare LICENSE as its license file")
    classifiers = metadata.get_all("Classifier", [])
    if any(classifier.startswith("License ::") for classifier in classifiers):
        raise ValueError(f"{label} must not contain deprecated license classifiers")

    project_urls: dict[str, str] = {}
    for value in metadata.get_all("Project-URL", []):
        name, separator, url = value.partition(", ")
        if not separator or name in project_urls:
            raise ValueError(f"{label} contains an invalid Project-URL: {value}")
        project_urls[name] = url
    if project_urls != EXPECTED_PROJECT_URLS:
        raise ValueError(f"{label} project URLs differ: {project_urls!r}")

    if metadata.get("Description-Content-Type") != "text/markdown":
        raise ValueError(f"{label} README content type must be text/markdown")
    description = metadata.get_payload()
    if not isinstance(description, str):
        raise ValueError(f"{label} README metadata must be text")
    if "](docs/" in description or "github.com/fallblu/persistra/blob/main/docs" in description:
        raise ValueError(f"{label} README contains repository-relative documentation links")
    if "https://fallblu.github.io/persistra/" not in description:
        raise ValueError(f"{label} README does not link to the canonical documentation site")

    if wheel:
        if not any(path.endswith(".dist-info/licenses/LICENSE") for path in archive_files):
            raise ValueError("wheel does not contain its declared license file")
    elif "LICENSE" not in archive_files:
        raise ValueError("sdist does not contain its declared license file")


def create_environment(directory: Path) -> Path:
    """Create one isolated environment and return its Python executable."""
    environment = directory / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(environment)],
        check=True,
    )
    return environment / "bin" / "python"


def install_and_smoke(
    wheel: Path,
    *,
    expected_version: str,
    extra: str | None,
    directory: Path,
) -> None:
    """Install one wheel boundary and run its isolated import contract."""
    python = create_environment(directory)
    requirement = str(wheel) if extra is None else f"persistra[{extra}] @ {wheel.as_uri()}"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), requirement],
        check=True,
    )
    subprocess.run(
        [str(python), "-I", "-c", installed_smoke_program(expected_version, extra)],
        check=True,
        cwd=directory,
    )


def build_wheel_from_sdist(sdist: Path, directory: Path) -> Path:
    """Extract one sdist safely and build a wheel from only its contents."""
    source_parent = directory / "source"
    source_parent.mkdir(parents=True)
    with tarfile.open(sdist, mode="r:gz") as archive:
        archive.extractall(source_parent, filter="data")
    roots = list(source_parent.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError("extracted sdist must contain exactly one source directory")
    output = directory / "wheel"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(output), str(roots[0])],
        check=True,
    )
    wheels = list(output.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected one wheel built from sdist, found {len(wheels)}")
    return wheels[0].resolve()


def main() -> None:
    """Verify artifacts and each supported clean-install boundary."""
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
    sdists = sorted(Path("dist").glob(f"persistra-{version}.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            f"expected one current wheel and sdist, found {len(wheels)} wheel(s) "
            f"and {len(sdists)} sdist(s)"
        )
    wheel = wheels[0].resolve()
    sdist = sdists[0].resolve()
    try:
        source_files = sdist_files(sdist)
        built_files = wheel_files(wheel)
        validate_sdist_policy(source_files)
        wheel_core_metadata = wheel_metadata(wheel)
        sdist_core_metadata = sdist_metadata(sdist)
        validate_distribution_metadata(wheel_core_metadata, built_files, wheel=True)
        validate_distribution_metadata(sdist_core_metadata, source_files, wheel=False)
        if wheel_core_metadata.get_payload() != sdist_core_metadata.get_payload():
            raise ValueError("wheel and sdist rendered README metadata differ")
    except ValueError as error:
        raise SystemExit(str(error)) from error

    with tempfile.TemporaryDirectory(prefix="persistra-package-check-") as temporary:
        root = Path(temporary)
        for extra in (None, "viz", "inspect"):
            label = "base" if extra is None else extra
            directory = root / label
            directory.mkdir()
            install_and_smoke(
                wheel,
                expected_version=version,
                extra=extra,
                directory=directory,
            )

        rebuilt = build_wheel_from_sdist(sdist, root / "sdist-build")
        if wheel_files(rebuilt) != wheel_files(wheel):
            raise SystemExit("wheel built from sdist has different archive contents")
        rebuilt_environment = root / "sdist-install"
        rebuilt_environment.mkdir()
        install_and_smoke(
            rebuilt,
            expected_version=version,
            extra=None,
            directory=rebuilt_environment,
        )


if __name__ == "__main__":
    main()
