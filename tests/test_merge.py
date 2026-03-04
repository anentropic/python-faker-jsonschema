"""Unit tests for schema merging logic: resolvers, _merge_schemas, compound_schema."""

import pytest

from faker_jsonschema.provider import (
    UnsatisfiableConstraintsError,
    _merge_constraint,
    _merge_schemas,
    _resolve_additional_properties,
    _resolve_dependent_required,
    _resolve_dependent_schemas,
    _resolve_equal_or_error,
    _resolve_multiple_of,
    _resolve_properties,
    compound_schema,
)


# ── _merge_constraint ────────────────────────────────────────────────


def test_merge_constraint_both_none():
    assert _merge_constraint(None, None, max) is None


def test_merge_constraint_left_only():
    assert _merge_constraint(5, None, max) == 5


def test_merge_constraint_right_only():
    assert _merge_constraint(None, 10, max) == 10


def test_merge_constraint_both_present():
    assert _merge_constraint(5, 10, max) == 10
    assert _merge_constraint(5, 10, min) == 5


# ── _resolve_equal_or_error ──────────────────────────────────────────


def test_resolve_equal_same():
    assert _resolve_equal_or_error("date", "date") == "date"
    assert _resolve_equal_or_error(42, 42) == 42


def test_resolve_equal_different():
    with pytest.raises(UnsatisfiableConstraintsError):
        _resolve_equal_or_error("date", "email")


# ── _resolve_multiple_of ─────────────────────────────────────────────


def test_resolve_multiple_of_left_divides():
    """6 is a multiple of 3 → pick 6."""
    assert _resolve_multiple_of(6, 3) == 6


def test_resolve_multiple_of_right_divides():
    """3 divides into 6 → pick 6."""
    assert _resolve_multiple_of(3, 6) == 6


def test_resolve_multiple_of_neither():
    """5 and 3 — neither divides the other."""
    with pytest.raises(UnsatisfiableConstraintsError):
        _resolve_multiple_of(5, 3)


def test_resolve_multiple_of_same():
    assert _resolve_multiple_of(4, 4) == 4


def test_resolve_multiple_of_one_is_1():
    """1 divides everything."""
    assert _resolve_multiple_of(1, 7) == 7
    assert _resolve_multiple_of(7, 1) == 7


# ── _resolve_properties ─────────────────────────────────────────────


def test_resolve_properties_disjoint():
    left = {"a": {"type": "string"}}
    right = {"b": {"type": "integer"}}
    result = _resolve_properties(left, right)
    assert "a" in result
    assert "b" in result
    assert result["a"] == {"type": "string"}
    assert result["b"] == {"type": "integer"}


def test_resolve_properties_overlapping():
    """Overlapping keys recurse into _merge_schemas."""
    left = {"a": {"type": "integer", "minimum": 0, "maximum": 100}}
    right = {"a": {"type": "integer", "minimum": 50, "maximum": 80}}
    result = _resolve_properties(left, right)
    assert result["a"]["minimum"] == 50  # max of mins
    assert result["a"]["maximum"] == 80  # min of maxes


# ── _resolve_additional_properties ───────────────────────────────────


def test_resolve_additional_properties_false_wins():
    assert _resolve_additional_properties(False, True) is False
    assert _resolve_additional_properties(True, False) is False
    assert _resolve_additional_properties(False, False) is False


def test_resolve_additional_properties_both_true():
    assert _resolve_additional_properties(True, True) is True


def test_resolve_additional_properties_dict_and_true():
    schema = {"type": "string"}
    assert _resolve_additional_properties(schema, True) == schema
    assert _resolve_additional_properties(True, schema) == schema


def test_resolve_additional_properties_dict_and_dict():
    """Two dict schemas get merged."""
    left = {"type": "integer", "minimum": 0, "maximum": 100}
    right = {"type": "integer", "minimum": 50, "maximum": 80}
    result = _resolve_additional_properties(left, right)
    assert isinstance(result, dict)
    assert result["minimum"] == 50
    assert result["maximum"] == 80


def test_resolve_additional_properties_false_and_dict():
    assert _resolve_additional_properties(False, {"type": "string"}) is False
    assert _resolve_additional_properties({"type": "string"}, False) is False


# ── _resolve_dependent_required ──────────────────────────────────────


def test_resolve_dependent_required_disjoint():
    left = {"a": ["b"]}
    right = {"c": ["d"]}
    result = _resolve_dependent_required(left, right)
    assert result == {"a": ["b"], "c": ["d"]}


def test_resolve_dependent_required_overlapping():
    left = {"a": ["b", "c"]}
    right = {"a": ["c", "d"]}
    result = _resolve_dependent_required(left, right)
    assert set(result["a"]) == {"b", "c", "d"}


# ── _resolve_dependent_schemas ───────────────────────────────────────


def test_resolve_dependent_schemas_disjoint():
    left = {"a": {"type": "object", "properties": {"x": {"type": "string"}}}}
    right = {"b": {"type": "object", "properties": {"y": {"type": "integer"}}}}
    result = _resolve_dependent_schemas(left, right)
    assert "a" in result
    assert "b" in result


def test_resolve_dependent_schemas_overlapping():
    left = {
        "a": {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        }
    }
    right = {
        "a": {
            "type": "object",
            "properties": {"y": {"type": "integer"}},
            "required": ["y"],
        }
    }
    result = _resolve_dependent_schemas(left, right)
    # merged schema should have both properties
    assert "x" in result["a"]["properties"]
    assert "y" in result["a"]["properties"]
    assert set(result["a"]["required"]) == {"x", "y"}


# ── _merge_schemas ───────────────────────────────────────────────────


def test_merge_schemas_integer():
    left = {"type": "integer", "minimum": 0, "maximum": 100}
    right = {"type": "integer", "minimum": 50, "maximum": 80}
    result = _merge_schemas(left, right)
    assert result["type"] == "integer"
    assert result["minimum"] == 50
    assert result["maximum"] == 80


def test_merge_schemas_string():
    left = {"type": "string", "minLength": 5, "maxLength": 20}
    right = {"type": "string", "minLength": 10, "maxLength": 15}
    result = _merge_schemas(left, right)
    assert result["minLength"] == 10
    assert result["maxLength"] == 15


def test_merge_schemas_incompatible_raises():
    left = {"type": "string", "pattern": "^abc$"}
    right = {"type": "string", "pattern": "^xyz$"}
    with pytest.raises(UnsatisfiableConstraintsError, match="Cannot merge"):
        _merge_schemas(left, right)


def test_merge_schemas_object_properties():
    left = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    right = {
        "type": "object",
        "properties": {"b": {"type": "integer"}},
        "required": ["b"],
    }
    result = _merge_schemas(left, right)
    assert "a" in result["properties"]
    assert "b" in result["properties"]
    assert set(result["required"]) == {"a", "b"}


# ── compound_schema ──────────────────────────────────────────────────


def test_compound_schema_two_integers():
    schemas = [
        {"type": "integer", "minimum": 0, "maximum": 100},
        {"type": "integer", "minimum": 50, "maximum": 80},
    ]
    result = compound_schema(schemas)
    assert result["minimum"] == 50
    assert result["maximum"] == 80


def test_compound_schema_three_strings():
    schemas = [
        {"type": "string", "minLength": 1, "maxLength": 100},
        {"type": "string", "minLength": 10},
        {"type": "string", "maxLength": 50},
    ]
    result = compound_schema(schemas)
    assert result["minLength"] == 10
    assert result["maxLength"] == 50


def test_compound_schema_objects():
    schemas = [
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a"],
        },
        {
            "type": "object",
            "properties": {"b": {"type": "integer"}},
            "required": ["b"],
        },
        {
            "type": "object",
            "properties": {"c": {"type": "boolean"}},
            "required": ["c"],
        },
    ]
    result = compound_schema(schemas)
    assert set(result["properties"].keys()) == {"a", "b", "c"}
    assert set(result["required"]) == {"a", "b", "c"}
