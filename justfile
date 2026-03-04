default:
    @just --list

build:
    uv run mkdocs build --strict

serve port="8000":
    uv run mkdocs serve --dev-addr 127.0.0.1:{{port}} --livereload

shell:
    PYTHONPATH=faker_jsonschema:tests:$PYTHONPATH uv run ipython

typecheck:
    uv run basedpyright

lint:
    uv run ruff check faker_jsonschema tests

format:
    uv run ruff format faker_jsonschema tests

pytest:
    uv run pytest -v -s --pdb

test:
    just lint
    just pytest
