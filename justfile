default:
    @just --list

pypi:
    uv build
    uv publish
    just tag

tag:
    git tag "$(python -c "from faker_jsonschema import __version__; print(__version__)")"
    git push --tags

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
