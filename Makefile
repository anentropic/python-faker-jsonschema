.PHONY: pypi, tag, shell, typecheck, pytest, test

pypi:
	poetry publish --build
	make tag

tag:
	git tag $$(python -c "from faker_jsonschema import __version__; print(__version__)")
	git push --tags

typecheck:
	pytype faker_jsonschema

pytest:
	#  --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb
	py.test -v -s tests/

test:
	$(MAKE) typecheck
	$(MAKE) pytest
