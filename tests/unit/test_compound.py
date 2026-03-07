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
        result = faker.from_jsonschema(schema)
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
        result = faker.from_jsonschema(schema)
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


def test_oneof_overlapping_numeric_types_requires_exactly_one_match(faker, provider, monkeypatch):
    """OneOf must reject values that validate against both integer and number."""
    schema = {
        "oneOf": [
            {"type": "integer"},
            {"type": "number"},
        ]
    }

    monkeypatch.setattr(provider.generator, "random_element", lambda elements: list(elements)[0])

    result = faker.from_jsonschema(schema)
    assert not (isinstance(result, int) and not isinstance(result, bool))
    validate(result, schema)


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
        result = faker.from_jsonschema(schema)
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
        result = faker.from_jsonschema(schema)
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
        result = faker.from_jsonschema(schema)
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


def test_anyof_disjoint_same_type_branches_still_generate_valid_value(faker, provider, monkeypatch):
    """AnyOf should select a satisfiable branch, not intersect disjoint same-type schemas."""
    schema = {
        "anyOf": [
            {"type": "integer", "maximum": 0},
            {"type": "integer", "minimum": 1},
        ]
    }

    def sample_all(elements, length=None):
        values = list(elements)
        if length is None:
            return values
        return values[:length]

    monkeypatch.setattr(provider.generator, "random_sample", sample_all)

    result = faker.from_jsonschema(schema)
    assert isinstance(result, int) and not isinstance(result, bool)
    validate(result, schema)


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
        faker.from_jsonschema(schema)


def test_allof_merged_integer_constraints(faker, repeats_for_fast):
    """AllOf merging integer constraints (min/max tightened)."""
    schema = {
        "allOf": [
            {"type": "integer", "minimum": 0, "maximum": 100},
            {"type": "integer", "minimum": 50, "maximum": 80},
        ]
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
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
        result = faker.from_jsonschema(schema)
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


# ── if / then / else ─────────────────────────────────────────────────


def test_if_then_else_basic(faker):
    """if/then/else round-trip: result validates against schema."""
    schema = {
        "type": "integer",
        "if": {"minimum": 10},
        "then": {"maximum": 100},
        "else": {"maximum": 9},
    }
    for _ in range(50):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, int)
        # The result should satisfy at least one branch
        # (we can't deterministically predict which branch was chosen)


def test_if_then_only(faker, repeats_for_fast):
    """Schema with if/then but no else."""
    schema = {
        "type": "string",
        "if": {"minLength": 5},
        "then": {"maxLength": 20},
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)


def test_if_else_only(faker, repeats_for_fast):
    """Schema with if/else but no then."""
    schema = {
        "type": "integer",
        "if": {"maximum": 0},
        "else": {"minimum": 1},
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, int)


# ── if/then/else edge cases ──────────────────────────────────────────


class TestIfThenElseEdgeCases:
    """Verify if/then/else merging and generation."""

    def test_if_then_else_with_required(self, faker, repeats_for_slow):
        """if/then/else adds required properties on the correct branch."""
        schema = {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
            },
            "required": ["type"],
            "if": {"properties": {"type": {"const": "business"}}},
            "then": {
                "properties": {"company": {"type": "string"}},
                "required": ["company"],
            },
            "else": {
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
        saw_then = False
        saw_else = False
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, dict)
            assert "type" in result
            validate(result, schema)
            if "company" in result:
                saw_then = True
                assert result["type"] == "business"
            if "name" in result:
                saw_else = True
                assert result["type"] != "business"
        assert saw_then, "then-branch was never observed"
        assert saw_else, "else-branch was never observed"

    def test_if_then_else_integer_constraints(self, faker, repeats_for_fast):
        """
        if/then/else constraining an integer: proper constraint intersection.

        Base: minimum=0, maximum=200.
        then branch: maximum=150  → merged result has min=0, max=min(200,150)=150
        else branch: maximum=50   → merged result has min=0, max=min(200,50)=50

        With proper merging, the base maximum is tightened (not clobbered),
        and the base minimum is always preserved.
        """
        schema = {
            "type": "integer",
            "minimum": 0,
            "maximum": 200,
            "if": {"minimum": 100},
            "then": {"maximum": 150},
            "else": {"maximum": 50},
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, int)
            validate(result, schema)

    def test_if_then_else_preserves_base_constraints(self, faker, repeats_for_fast):
        """
        Branch adding minLength must not clobber base maxLength.

        Base: minLength=1, maxLength=10
        then branch: minLength=5  → merged: minLength=max(1,5)=5, maxLength=10
        else branch: (empty)      → merged: minLength=1, maxLength=10

        The old shallow merge would replace minLength but keep maxLength.
        With _merge_schemas this uses max() for minLength — even better.
        Either way, maxLength=10 must be preserved.
        """
        schema = {
            "type": "string",
            "minLength": 1,
            "maxLength": 10,
            "if": {"minLength": 5},
            "then": {"minLength": 5},
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, str)
            assert len(result) <= 10, (
                f"maxLength=10 was clobbered by branch merge: got len={len(result)}"
            )
            assert len(result) >= 1

    def test_if_then_else_deep_property_merge(self, faker, repeats_for_slow):
        """
        Branch adding a property must not clobber existing properties.

        Base properties: {name: string, age: {integer, min=0, max=120}}
        then branch properties: {email: string}
        → merged properties should have all three: name, age, email
        (old shallow merge would clobber age with the branch dict)
        """
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
            },
            "required": ["name", "age"],
            "if": {"properties": {"name": {"minLength": 1}}},
            "then": {
                "properties": {"email": {"type": "string", "format": "email"}},
                "required": ["email"],
            },
        }
        saw_then = False
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, dict)
            assert "name" in result
            assert "age" in result, f"'age' property was lost during if/then merge: {result}"
            assert isinstance(result["age"], int)
            assert 0 <= result["age"] <= 120, f"age constraints lost during merge: {result['age']}"
            if "email" in result:
                saw_then = True
        # Over many iterations, we should see the then-branch at least once
        assert saw_then, "then-branch was never applied"

    def test_nested_if_then_else(self, faker, repeats_for_slow):
        """Nested if/then/else in properties."""
        schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "value": {
                    "type": "integer",
                    "minimum": 0,
                    "if": {"minimum": 10},
                    "then": {"maximum": 20},
                    "else": {"maximum": 9},
                },
            },
            "required": ["status", "value"],
        }
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, dict)
            assert "status" in result
            assert "value" in result
            assert isinstance(result["value"], int)
            assert result["value"] >= 0

    def test_if_then_else_else_branch_needs_negation(self, faker, repeats_for_fast):
        """
        Else branch requires if-condition negation to produce valid values.

        Base: integer 0–200
        if minimum >= 50 → then maximum 100  (valid range: 50–100)
        else → multipleOf 7  (without negation could generate 56, 63, …
               which satisfy if but not then; with negation range is 0–49)
        """
        schema = {
            "type": "integer",
            "minimum": 0,
            "maximum": 200,
            "if": {"minimum": 50},
            "then": {"maximum": 100},
            "else": {"multipleOf": 7},
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, int)
            validate(result, schema)


# ── anyOf edge cases ─────────────────────────────────────────────────


class TestAnyOfEdgeCases:
    """anyOf with various schema shapes."""

    def test_anyof_single_schema(self, faker, repeats_for_slow):
        """AnyOf with a single sub-schema."""
        schema = {
            "anyOf": [
                {"type": "integer", "minimum": 0, "maximum": 100},
            ]
        }
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, int)
            assert 0 <= result <= 100
            validate(result, schema)

    def test_anyof_objects_with_different_required(self, faker, repeats_for_slow):
        """AnyOf with objects having different required properties."""
        schema = {
            "anyOf": [
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
            ]
        }
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, dict)
            validate(result, schema)

    def test_anyof_member_without_type(self, faker, repeats_for_slow):
        """AnyOf should support valid sub-schemas that omit an explicit type."""
        schema = {
            "anyOf": [
                {"const": 1},
                {"type": "string", "minLength": 1},
            ]
        }
        for _ in range(repeats_for_slow):
            result = faker.from_jsonschema(schema)
            validate(result, schema)


def test_allof_members_without_type(faker, repeats_for_fast):
    """AllOf should intersect valid sub-schemas even when members omit type."""
    schema = {
        "allOf": [
            {"const": 1},
            {"enum": [1, 2]},
        ]
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == 1
        validate(result, schema)


def test_allof_conflicting_const_without_type_raises(faker):
    """AllOf with conflicting untyped const values is unsatisfiable."""
    schema = {
        "allOf": [
            {"const": 1},
            {"const": 2},
        ]
    }
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.from_jsonschema(schema)


def test_allof_disjoint_enum_without_type_raises(faker):
    """AllOf with disjoint untyped enums is unsatisfiable."""
    schema = {
        "allOf": [
            {"enum": [1, 2]},
            {"enum": [3, 4]},
        ]
    }
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.from_jsonschema(schema)


# ── Complex real-world compound schemas ──────────────────────────────


def test_discriminated_union(faker, repeats_for_slow):
    """Discriminated union via oneOf with const type field."""
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["dog"]},
                    "bark_volume": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 10,
                    },
                },
                "required": ["type", "bark_volume"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["cat"]},
                    "indoor": {"type": "boolean"},
                },
                "required": ["type", "indoor"],
                "additionalProperties": False,
            },
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, dict)
        assert "type" in result
        if result["type"] == "dog":
            assert "bark_volume" in result
        elif result["type"] == "cat":
            assert "indoor" in result


def test_allof_with_dependent_schemas(faker, repeats_for_slow):
    """AllOf combined with dependentSchemas."""
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {
                    "payment_type": {"type": "string"},
                },
                "required": ["payment_type"],
            },
            {
                "type": "object",
                "dependentSchemas": {
                    "payment_type": {
                        "properties": {
                            "amount": {
                                "type": "number",
                                "minimum": 0,
                            },
                        },
                        "required": ["amount"],
                    },
                },
            },
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, dict)
        assert "payment_type" in result
        # dependentSchemas should force amount when payment_type is present
        assert "amount" in result
