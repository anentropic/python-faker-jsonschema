"""Tests for $ref / $defs resolution."""

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError

# ── Basic $ref/$defs ─────────────────────────────────────────────────


def test_ref_defs_basic(faker, repeats_for_fast):
    """$ref pointing to $defs resolves correctly."""
    schema = {
        "$defs": {
            "name": {"type": "string", "minLength": 1, "maxLength": 50},
        },
        "type": "object",
        "properties": {
            "first_name": {"$ref": "#/$defs/name"},
            "last_name": {"$ref": "#/$defs/name"},
        },
        "required": ["first_name", "last_name"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, dict)
        assert isinstance(result["first_name"], str)
        assert isinstance(result["last_name"], str)
        validate(result, schema)


def test_ref_definitions_legacy(faker, repeats_for_fast):
    """$ref pointing to legacy 'definitions' key."""
    schema = {
        "definitions": {
            "posint": {"type": "integer", "minimum": 0, "maximum": 1000},
        },
        "type": "object",
        "properties": {
            "count": {"$ref": "#/definitions/posint"},
        },
        "required": ["count"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, dict)
        assert isinstance(result["count"], int)
        assert result["count"] >= 0
        validate(result, schema)


def test_ref_nested(faker, repeats_for_slow):
    """$ref that resolves to a schema containing another $ref."""
    schema = {
        "$defs": {
            "inner": {"type": "integer", "minimum": 1, "maximum": 10},
            "outer": {
                "type": "object",
                "properties": {"value": {"$ref": "#/$defs/inner"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
        "type": "array",
        "items": {"$ref": "#/$defs/outer"},
        "minItems": 1,
        "maxItems": 3,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert isinstance(item, dict)
            assert 1 <= item["value"] <= 10
        validate(result, schema)


def test_ref_with_sibling_keywords(faker, repeats_for_fast):
    """$ref with sibling keywords (draft 2019-09+) — extra keys merged."""
    schema = {
        "$defs": {
            "base": {"type": "integer", "minimum": 0},
        },
        "type": "object",
        "properties": {
            "score": {"$ref": "#/$defs/base", "maximum": 100},
        },
        "required": ["score"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result["score"], int)
        assert result["score"] >= 0
        assert result["score"] <= 100
        validate(result, schema)


def test_ref_with_sibling_object_keywords(faker, repeats_for_fast):
    """$ref siblings should merge nested object constraints instead of overwriting them."""
    schema = {
        "$defs": {
            "base": {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
                "additionalProperties": False,
            }
        },
        "$ref": "#/$defs/base",
        "properties": {"b": {"type": "integer"}},
        "required": ["b"],
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        validate(result, schema)


# ── Error cases ──────────────────────────────────────────────────────


def test_ref_unresolvable(faker):
    """$ref pointing to non-existent definition raises error."""
    schema = {
        "$defs": {},
        "type": "object",
        "properties": {
            "x": {"$ref": "#/$defs/nonexistent"},
        },
        "required": ["x"],
    }
    with pytest.raises(UnsatisfiableConstraintsError, match="Cannot resolve"):
        faker.from_jsonschema(schema)


# ── Circular $ref detection ──────────────────────────────────────────


class TestCircularRef:
    """Verify that circular $ref schemas don't cause infinite recursion."""

    def test_circular_ref_optional_child(self, faker, repeats_for_slow):
        """Circular $ref with optional child should terminate via max_depth."""
        schema = {
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "child": {"$ref": "#/$defs/node"},
                    },
                }
            },
            "$ref": "#/$defs/node",
        }
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema, max_depth=3)
            assert isinstance(result, dict)

    def test_circular_ref_required_child_raises(self, faker):
        """Circular $ref with required child should raise, not RecursionError."""
        schema = {
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "child": {"$ref": "#/$defs/node"},
                    },
                    "required": ["value", "child"],
                    "additionalProperties": False,
                }
            },
            "$ref": "#/$defs/node",
        }
        # Should raise UnsatisfiableConstraintsError (not RecursionError)
        with pytest.raises(UnsatisfiableConstraintsError, match="Circular"):
            faker.from_jsonschema(schema, max_depth=2)

    def test_indirect_circular_ref(self, faker):
        """A -> B -> A circular $ref should be detected."""
        schema = {
            "$defs": {
                "a": {
                    "type": "object",
                    "properties": {"b": {"$ref": "#/$defs/b"}},
                    "required": ["b"],
                },
                "b": {
                    "type": "object",
                    "properties": {"a": {"$ref": "#/$defs/a"}},
                    "required": ["a"],
                },
            },
            "$ref": "#/$defs/a",
        }
        with pytest.raises(UnsatisfiableConstraintsError, match="Circular"):
            faker.from_jsonschema(schema, max_depth=2)


def test_recursive_tree_structure(faker, repeats_for_slow):
    """Tree structure with optional children array (recursive $ref)."""
    schema = {
        "$defs": {
            "node": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/node"},
                        "maxItems": 3,
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            }
        },
        "$ref": "#/$defs/node",
    }
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema, max_depth=4)
        assert isinstance(result, dict)
        assert "name" in result
        validate(result, schema)
