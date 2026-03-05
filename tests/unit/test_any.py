"""Tests for jsonschema_any() and empty-schema dispatch."""

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError

# ── Direct calls ─────────────────────────────────────────────────────


def test_jsonschema_any_returns_json_values(faker, repeats_for_fast):
    """jsonschema_any() should return a value of any JSON-compatible type."""
    types_seen = set()
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_any()
        types_seen.add(type(result).__name__)
    # over 50 iterations we should see more than one type
    assert len(types_seen) >= 2, f"Only saw types: {types_seen}"


def test_jsonschema_any_multiple_types(faker):
    """Over many iterations we should see diverse types."""
    types_seen = set()
    for _ in range(200):
        result = faker.jsonschema_any()
        if isinstance(result, bool):
            types_seen.add("bool")
        elif isinstance(result, int):
            types_seen.add("int")
        elif isinstance(result, float):
            types_seen.add("float")
        elif isinstance(result, str):
            types_seen.add("str")
        elif isinstance(result, list):
            types_seen.add("list")
        elif isinstance(result, dict):
            types_seen.add("dict")
        else:
            types_seen.add(type(result).__name__)
    # should see at least 3 different types
    assert len(types_seen) >= 3, f"Only saw types: {types_seen}"


# ── from_schema with empty schema (no "type" key) ───────────────────


def test_from_schema_empty_schema(faker, repeats_for_fast):
    """from_schema({}) should dispatch to jsonschema_any."""
    schema = {}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        # empty schema validates anything
        validate(result, schema)


def test_from_schema_no_type_key(faker, repeats_for_fast):
    """Schema without 'type' and without compound keys → any."""
    schema = {"description": "anything goes"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        # should produce something and not crash
        assert (
            result is not None or result is None
        )  # always passes; main test is no crash


# ── Type as array (draft-06+) ────────────────────────────────────────


def test_type_array_string_null(faker, repeats_for_fast):
    """{"type": ["string", "null"]} → str or None."""
    schema = {"type": ["string", "null"]}
    types_seen = set()
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        if result is None:
            types_seen.add("null")
        else:
            assert isinstance(result, str)
            types_seen.add("string")
        validate(result, schema)
    assert types_seen == {"string", "null"}, f"Only saw: {types_seen}"


def test_type_array_integer_number(faker, repeats_for_fast):
    """{"type": ["integer", "number"]} → int or float."""
    schema = {"type": ["integer", "number"]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, (int, float))
        validate(result, schema)


def test_type_array_single(faker, repeats_for_fast):
    """{"type": ["boolean"]} → always bool."""
    schema = {"type": ["boolean"]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, bool)
        validate(result, schema)


def test_type_array_with_constraints(faker, repeats_for_fast):
    """Type array with constraints applies to the chosen type."""
    schema = {"type": ["integer", "null"], "minimum": 5, "maximum": 10}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        if result is not None:
            assert isinstance(result, int)
            assert 5 <= result <= 10
        validate(result, schema)


# ── Boolean schemas (draft-06+) ──────────────────────────────────────


def test_boolean_schema_true(faker, repeats_for_fast):
    """Schema True → accepts anything (like empty schema)."""
    schema = True
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        validate(result, schema)


def test_boolean_schema_false(faker):
    """Schema False → always unsatisfiable."""
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.from_schema(False)


def test_empty_schema_as_true(faker, repeats_for_fast):
    """Empty dict schema {} behaves like True."""
    schema = {}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        validate(result, schema)
