"""Tests for oneOf, anyOf, allOf compound schema dispatch."""

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError

# ── oneOf ────────────────────────────────────────────────────────────


def test_oneof_string_or_integer(faker, repeats_for_slow):
    """OneOf with string | integer → result matches exactly one."""
    schema = {
        "oneOf": [
            {"type": "string"},
            {"type": "integer"},
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, (str, int))
        validate(result, schema)


def test_oneof_multiple_object_schemas(faker, repeats_for_slow):
    """OneOf with distinct object schemas."""
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {"kind": {"type": "string"}, "x": {"type": "integer"}},
                "required": ["kind", "x"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"kind": {"type": "string"}, "y": {"type": "number"}},
                "required": ["kind", "y"],
                "additionalProperties": False,
            },
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "kind" in result


def test_oneof_direct_call(faker, repeats_for_slow):
    """Direct call to jsonschema_oneof."""
    schemas = [
        {"type": "string"},
        {"type": "integer"},
        {"type": "boolean"},
    ]
    types_seen = set()
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_oneof(schemas)
        if isinstance(result, bool):
            types_seen.add("bool")
        elif isinstance(result, int):
            types_seen.add("int")
        elif isinstance(result, str):
            types_seen.add("str")
    # should see at least 2 types over 10 iterations
    assert len(types_seen) >= 2, f"Only saw types: {types_seen}"


# ── anyOf ────────────────────────────────────────────────────────────


def test_anyof_string_or_integer(faker, repeats_for_slow):
    """AnyOf with string | integer → result matches at least one."""
    schema = {
        "anyOf": [
            {"type": "string"},
            {"type": "integer"},
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, (str, int))
        validate(result, schema)


def test_anyof_same_type_merges_constraints(faker, repeats_for_slow):
    """AnyOf with multiple schemas of same type → constraints are merged."""
    schema = {
        "anyOf": [
            {"type": "integer", "minimum": 0, "maximum": 100},
            {"type": "integer", "minimum": 50, "maximum": 200},
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        validate(result, schema)


def test_anyof_three_schemas(faker, repeats_for_slow):
    """AnyOf with three sub-schemas."""
    schema = {
        "anyOf": [
            {"type": "string"},
            {"type": "integer"},
            {"type": "boolean"},
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, (str, int, bool))
        validate(result, schema)


def test_anyof_direct_call(faker, repeats_for_slow):
    """Direct call to jsonschema_anyof with same-type schemas."""
    schemas = [
        {"type": "integer", "minimum": 10, "maximum": 50},
        {"type": "integer", "minimum": 20, "maximum": 40},
    ]
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_anyof(schemas)
        assert isinstance(result, int)
        # must satisfy at least one sub-schema
        valid = any(
            s.get("minimum", float("-inf")) <= result <= s.get("maximum", float("inf"))
            for s in schemas
        )
        assert valid, f"{result} doesn't satisfy any sub-schema"


# ── allOf ────────────────────────────────────────────────────────────


def test_allof_multi_type_raises(faker):
    """AllOf with incompatible types raises UnsatisfiableConstraintsError."""
    schema = {
        "allOf": [
            {"type": "string"},
            {"type": "integer"},
        ]
    }
    with pytest.raises(UnsatisfiableConstraintsError, match="Cannot satisfy allOf"):
        faker.from_schema(schema)


def test_allof_merged_integer_constraints(faker, repeats_for_fast):
    """AllOf merging integer constraints (min/max tightened)."""
    schema = {
        "allOf": [
            {"type": "integer", "minimum": 0, "maximum": 100},
            {"type": "integer", "minimum": 50, "maximum": 80},
        ]
    }
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        assert 50 <= result <= 80
        validate(result, schema)


def test_allof_merged_string_constraints(faker, repeats_for_fast):
    """AllOf merging string constraints."""
    schema = {
        "allOf": [
            {"type": "string", "minLength": 5, "maxLength": 20},
            {"type": "string", "minLength": 10, "maxLength": 15},
        ]
    }
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert 10 <= len(result) <= 15
        validate(result, schema)


def test_allof_direct_call(faker, repeats_for_slow):
    """Direct call to jsonschema_allof."""
    schemas = [
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
        {"type": "object", "properties": {"b": {"type": "integer"}}, "required": ["b"]},
    ]
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_allof(schemas)
        assert isinstance(result, dict)
        assert "a" in result
        assert "b" in result
