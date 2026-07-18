.PHONY: lint type test contracts schema-check benchmark-smoke docs-check docs-build build pre-commit-install pre-commit-run

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest

contracts:
	uv run pytest --no-cov tests/contracts

schema-check:
	uv run python scripts/check_schema.py

benchmark-smoke:
	uv run pytest --no-cov tests/performance/test_benchmark_smoke.py

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
