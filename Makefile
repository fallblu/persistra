.PHONY: lint type test contracts mutation benchmark benchmark-check release-evidence docs-check docs-build build package-check verify pre-commit-install pre-commit-run

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest

contracts:
	uv run pytest --no-cov tests/contracts

mutation:
	uv run --group mutation python scripts/check_mutation.py

benchmark:
	uv run python scripts/benchmark_performance.py

benchmark-check:
	uv run python scripts/benchmark_performance.py --enforce --output benchmark-results.json

release-evidence: build
	uv run --group release-evidence python scripts/build_release_evidence.py

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
