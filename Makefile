.PHONY: pypi, tag, shell, typecheck, pytest, test

pypi:
	poetry publish --build
	make tag

tag:
	git tag $$(python -c "from faker_jsonschema import __version__; print(__version__)")
	git push --tags

shell:
	PYTHONPATH=faker_jsonschema:tests:$$PYTHONPATH ipython

typecheck:
	pytype faker_jsonschema

pytest:
	py.test -v -s tests/

test:
	$(MAKE) typecheck
	$(MAKE) pytest
