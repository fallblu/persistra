.PHONY: lint type test docs-check docs-build build pre-commit-install pre-commit-run

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest

docs-check:
	uv run python scripts/check_docs.py

docs-build:
	uv run --group docs mkdocs build --strict

build:
	uv build

pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files
