.PHONY: docs-serve docs-build docs-execute sample-data

docs-serve:
	mkdocs serve

docs-build:
	mkdocs build --strict

# Re-execute every notebook in place; fails on the first cell error.
docs-execute:
	jupyter nbconvert --to notebook --execute --inplace \
		--ExecutePreprocessor.timeout=600 \
		$$(find docs -name '*.ipynb' -not -path '*/.ipynb_checkpoints/*')

sample-data:
	python scripts/build_sample_data.py
