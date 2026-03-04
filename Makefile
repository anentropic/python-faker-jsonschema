.PHONY: pypi, tag, shell, typecheck, lint, format, pytest, test

pypi:
	uv build
	uv publish
	make tag

tag:
	git tag $$(python -c "from faker_jsonschema import __version__; print(__version__)")
	git push --tags

shell:
	uv run env PYTHONPATH=faker_jsonschema:tests:$$PYTHONPATH ipython

typecheck:
	uv run pytype faker_jsonschema

lint:
	uv run ruff check faker_jsonschema tests

format:
	uv run ruff format faker_jsonschema tests

pytest:
	uv run pytest -v -s --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb tests/

test:
	$(MAKE) lint
	$(MAKE) pytest
