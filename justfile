default:
    @just --list

docs-build:
    uv run --group docs mkdocs build --strict

docs-serve port="8000":
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:{{port}} --livereload

shell:
    uv run ipython

typecheck:
    uv run basedpyright

lint:
    uv run ruff check faker_jsonschema tests

format:
    uv run ruff format faker_jsonschema tests

# Run tests with pytest and drop into pdb on failure (interactive)
pytest:
    uv run pytest -v -s --pdb

test:
    just lint
    uv run pytest -v -s
