.PHONY: lint type test contracts docs-check docs-build build package-check verify pre-commit-install pre-commit-run

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest

contracts:
	uv run pytest --no-cov tests/contracts

docs-check:
	uv run python scripts/check_docs.py

docs-build:
	NO_MKDOCS_2_WARNING=true uv run --group docs mkdocs build --strict

build:
	uv build

package-check: build
	uv run python scripts/check_package.py

verify: lint type test docs-check docs-build package-check
	uv lock --check

pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files
