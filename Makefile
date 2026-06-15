.PHONY: lint type test docs-check docs-serve docs-build docs-execute build pre-commit-install pre-commit-run

lint:
	uv run ruff check .

type:
	uv run pyright

test:
	uv run pytest

docs-check:
	uv run python scripts/check_docstrings.py
	uv run python scripts/check_doc_snippets.py

docs-serve:
	uv run mkdocs serve

docs-build:
	uv run mkdocs build --strict

# Re-execute every notebook in place; fails on the first cell error.
docs-execute:
	find docs -name '*.ipynb' -not -path '*/.ipynb_checkpoints/*' -print0 | \
		xargs -0 -r uv run jupyter nbconvert --to notebook --execute --inplace \
			--ExecutePreprocessor.timeout=600

build:
	uv build

pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files
