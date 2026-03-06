# AGENTS.md

## Project

A Faker provider (`JSONSchemaProvider`) that generates fake data conforming to a given [JSON Schema](https://json-schema.org/specification). The main implementation is in `faker_jsonschema/provider.py`.

## Stack

- Python ≥3.11, managed with **uv**
- Faker, Hypothesis (strategies for regex-based string generation), jsonschema (validation)
- Tests: pytest. Lint: ruff. Types: basedpyright. Task runner: just. Pre-commit: **prek** (`prek run --all-files`).

## Commands

```
just test          # lint + pytest
just pytest        # uv run pytest -v -s --pdb
just lint          # uv run ruff check faker_jsonschema tests
just format        # uv run ruff format faker_jsonschema tests
just typecheck     # uv run basedpyright
```

Always run `just lint` and `uv run pytest` before committing.

## Architecture

- `faker_jsonschema/provider.py` — Single-file provider. `from_jsonschema(schema)` is the public entry point; it dispatches to `jsonschema_<type>()` methods via `_from_schema()`. A metaclass auto-generates `kwargs_from_schema` mappers (camelCase schema keys → snake_case args). Compound types (`allOf`/`anyOf`/`oneOf`) merge schemas via `TYPE_ATTR_MERGE_RESOLVERS` then recurse.
- `js_regex/` — Vendored JS-regex-to-Python-regex adapter.
- `faker_jsonschema/utils.py` — Small utilities (currently just `IntInf`).

### Key conventions in provider.py

- Recursive schema generation must use `self._from_schema()` (not `from_schema()`) to preserve `context._depth`.
- Use `self.context` (the property), never `self._context` directly — the property lazily initializes a `Context()` when `None`.
- `from_jsonschema()` sets `self._context = None` in its `finally` block. Direct method calls (e.g. `jsonschema_string()`) must tolerate this.
- `nullable_or_enum` decorator intercepts `nullable` and `enum` before type-specific logic.

## Tests

- One test file per type: `tests/test_string.py`, `test_integer.py`, `test_number.py`, `test_array.py`, `test_object.py`.
- `tests/test_pbt.py` — Property-based tests (Hypothesis).
- Session-scoped `faker` fixture (seeded, seed printed and controllable via `SEED` env var).
- `repeats_for_slow` (10) and `repeats_for_fast` (50) fixtures for non-deterministic tests.
- Tests validate results with `jsonschema.validate(result, schema)`.
- Test both direct method calls (`faker.jsonschema_object(...)`) and `faker.from_jsonschema({...})` round-trips.
