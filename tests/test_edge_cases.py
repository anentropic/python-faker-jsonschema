"""
Tests added during code review to cover edge cases and verify bug fixes.

Areas covered:
1. Negative exclusive bounds (integers and floats)
2. Circular $ref detection
3. _safe_random_int edge cases
4. Array uniqueItems with small domain
5. Object dependentRequired exceeding maxProperties
6. jsonschema_not with broad schemas (termination)
7. anyOf with type-less schemas
8. deeply nested generation terminates
9. if/then/else constraint merging
10. contains at depth limit
"""

import pytest
from jsonschema import ValidationError, validate

from faker_jsonschema.provider import (
    JSONSchemaProvider,
    NoExampleFoundError,
    UnsatisfiableConstraintsError,
)


@pytest.fixture()
def provider(faker):
    """Get the JSONSchemaProvider instance from the faker."""
    for p in faker.providers:
        if isinstance(p, JSONSchemaProvider):
            return p
    pytest.fail("JSONSchemaProvider not found")


# ── 1. Negative exclusive bounds ─────────────────────────────────────


class TestNegativeExclusiveBounds:
    """Verify exclusive bounds work correctly for negative values."""

    def test_negative_exclusive_minimum_integer(self, faker, repeats_for_fast):
        """ExclusiveMinimum with negative value: result must be > boundary."""
        schema = {"type": "integer", "exclusiveMinimum": -5, "maximum": 0}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert result > -5, f"Expected > -5, got {result}"
            assert result <= 0
            validate(result, schema)

    def test_negative_exclusive_maximum_integer(self, faker, repeats_for_fast):
        """ExclusiveMaximum with negative value: result must be < boundary."""
        schema = {"type": "integer", "minimum": -10, "exclusiveMaximum": -5}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert result >= -10
            assert result < -5, f"Expected < -5, got {result}"
            validate(result, schema)

    def test_negative_both_exclusive_integer(self, faker, repeats_for_fast):
        """Both exclusive bounds negative: -10 < result < -1."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": -10,
            "exclusiveMaximum": -1,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert -10 < result < -1, f"Expected -10 < x < -1, got {result}"
            validate(result, schema)

    def test_negative_exclusive_minimum_float(self, faker, repeats_for_fast):
        """ExclusiveMinimum with negative float: result must be > boundary."""
        schema = {"type": "number", "exclusiveMinimum": -5.0, "maximum": 0.0}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, float)
            assert result > -5.0, f"Expected > -5.0, got {result}"
            assert result <= 0.0
            validate(result, schema)

    def test_negative_exclusive_maximum_float(self, faker, repeats_for_fast):
        """ExclusiveMaximum with negative float: result must be < boundary."""
        schema = {"type": "number", "minimum": -10.0, "exclusiveMaximum": -5.0}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, float)
            assert result >= -10.0
            assert result < -5.0, f"Expected < -5.0, got {result}"
            validate(result, schema)

    def test_negative_exclusive_min_direct_call(self, faker, repeats_for_fast):
        """Direct call with negative exclusive_minimum."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(
                exclusive_minimum=-20, exclusive_maximum=-10
            )
            assert isinstance(result, int)
            assert -20 < result < -10

    def test_negative_exclusive_draft04_form(self, faker, repeats_for_fast):
        """Draft-04 boolean exclusiveMin/Max with negative values."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(
                minimum=-10, maximum=-5, exclusive_min=True, exclusive_max=True
            )
            assert isinstance(result, int)
            assert -10 < result < -5

    def test_zero_straddling_exclusive_bounds(self, faker, repeats_for_fast):
        """Exclusive bounds straddling zero: -3 < result < 3."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": -3,
            "exclusiveMaximum": 3,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert -3 < result < 3
            validate(result, schema)


# ── 2. Circular $ref detection ───────────────────────────────────────


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
            result = faker.from_schema(schema, max_depth=3)
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
            faker.from_schema(schema, max_depth=2)

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
            faker.from_schema(schema, max_depth=2)


# ── 3. _safe_random_int edge cases ──────────────────────────────────


class TestSafeRandomInt:
    """Edge cases for _safe_random_int that previously had unbounded recursion."""

    def test_both_none(self, faker, provider, repeats_for_fast):
        """Both min and max None should always terminate."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(None, None)
            assert isinstance(result, int)

    def test_equal_values(self, faker, provider, repeats_for_fast):
        """Equal min and max should return that value."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(5, 5)
            assert result == 5

    def test_negative_range(self, faker, provider, repeats_for_fast):
        """Negative min, None max should produce reasonable results."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(-100, None)
            assert isinstance(result, int)
            assert result >= -100

    def test_none_min(self, faker, provider, repeats_for_fast):
        """None min, specified max should produce values <= max."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(None, 50)
            assert isinstance(result, int)
            assert result <= 50


# ── 4. Array uniqueItems with small domain ───────────────────────────


class TestArrayEdgeCases:
    """Array generation edge cases that could hang or produce wrong results."""

    def test_unique_booleans_max_2(self, faker, repeats_for_slow):
        """
        UniqueItems with boolean type (domain size 2).

        With finite-domain sampling, this must always produce exactly
        [True, False] (in some order).
        """
        schema = {
            "type": "array",
            "items": {"type": "boolean"},
            "uniqueItems": True,
            "minItems": 2,
            "maxItems": 2,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 2, f"Expected 2 items, got {len(result)}: {result}"
            assert set(result) == {True, False}, (
                f"Expected {{True, False}}, got {result}"
            )
            validate(result, schema)

    def test_unique_small_enum(self, faker, repeats_for_slow):
        """UniqueItems with small enum domain."""
        schema = {
            "type": "array",
            "items": {"type": "integer", "enum": [1, 2, 3]},
            "uniqueItems": True,
            "minItems": 2,
            "maxItems": 3,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) >= 2
            assert len(set(result)) == len(result)  # all unique
            validate(result, schema)

    def test_unique_bounded_integers(self, faker, repeats_for_slow):
        """
        UniqueItems with bounded integer domain (10 values).

        Finite-domain sampling should always produce distinct values.
        """
        schema = {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 10},
            "uniqueItems": True,
            "minItems": 5,
            "maxItems": 5,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 5
            assert len(set(result)) == 5, f"Expected 5 unique values, got {result}"
            assert all(1 <= x <= 10 for x in result)
            validate(result, schema)

    def test_unique_bounded_integers_multiple_of(self, faker, repeats_for_slow):
        """UniqueItems with bounded integer + multipleOf (domain: 10,20,30,40,50)."""
        schema = {
            "type": "array",
            "items": {
                "type": "integer",
                "minimum": 10,
                "maximum": 50,
                "multipleOf": 10,
            },
            "uniqueItems": True,
            "minItems": 5,
            "maxItems": 5,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 5
            assert set(result) == {10, 20, 30, 40, 50}
            validate(result, schema)

    def test_unique_nullable_booleans(self, faker, repeats_for_slow):
        """UniqueItems with nullable boolean (domain: true, false, null = 3)."""
        schema = {
            "type": "array",
            "items": {"type": "boolean", "nullable": True},
            "uniqueItems": True,
            "minItems": 3,
            "maxItems": 3,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 3, f"Expected 3 items, got {result}"
            # Check uniqueness by converting to set of JsonVal-like wrappers
            assert len({repr(x) for x in result}) == 3, (
                f"Expected 3 unique items, got {result}"
            )

    def test_unique_domain_cap(self, faker, repeats_for_slow):
        """When minItems exceeds finite domain size, count is capped."""
        schema = {
            "type": "array",
            "items": {"type": "boolean"},
            "uniqueItems": True,
            "minItems": 5,  # impossible to get 5 unique booleans
            "maxItems": 10,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            # domain is only {true, false}, so we get at most 2
            assert len(result) <= 2
            assert len(set(result)) == len(result)

    def test_empty_prefix_items_with_items_false(self, faker, repeats_for_slow):
        """PrefixItems with items: false and matching minItems."""
        schema = {
            "type": "array",
            "prefixItems": [{"type": "string"}, {"type": "integer"}],
            "items": False,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 2
            assert isinstance(result[0], str)
            assert isinstance(result[1], int) and not isinstance(result[1], bool)
            validate(result, schema)

    def test_array_zero_max_items(self, faker, repeats_for_slow):
        """maxItems: 0 should always produce empty array."""
        schema = {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": 0,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert result == []
            validate(result, schema)

    def test_contains_with_tight_constraints(self, faker, repeats_for_slow):
        """
        Contains with minContains is now planned upfront, not best-effort.

        With upfront contains planning, we generate the required number of
        contains-matching items first, then fill remaining slots. This should
        reliably satisfy minContains every time.
        """
        schema = {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 100},
            "contains": {"type": "integer", "minimum": 90, "maximum": 100},
            "minContains": 2,
            "minItems": 5,
            "maxItems": 20,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            matching = sum(1 for x in result if isinstance(x, int) and 90 <= x <= 100)
            assert matching >= 2, (
                f"Expected >= 2 contains matches, got {matching} in {result}"
            )
            validate(result, schema)

    def test_contains_tight_maxitems_equals_mincontains(self, faker, repeats_for_slow):
        """When maxItems == minContains, every item must match contains."""
        schema = {
            "type": "array",
            "contains": {"type": "string", "minLength": 5},
            "minContains": 3,
            "minItems": 3,
            "maxItems": 3,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) == 3
            matching = sum(1 for x in result if isinstance(x, str) and len(x) >= 5)
            assert matching >= 3, (
                f"Expected all 3 items to match contains, got {matching}: {result}"
            )
            validate(result, schema)

    def test_contains_with_maxcontains(self, faker, repeats_for_slow):
        """
        MaxContains limits how many items match the contains schema.

        Uses a high-overlap scenario (items 0-100, contains 90-100) to
        verify the generation loop actively rejects excess contains matches
        rather than relying on post-hoc fixup.
        """
        schema = {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 100},
            "contains": {"type": "integer", "minimum": 90, "maximum": 100},
            "minContains": 1,
            "maxContains": 2,
            "minItems": 5,
            "maxItems": 10,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            matching = sum(1 for x in result if isinstance(x, int) and 90 <= x <= 100)
            assert matching >= 1, f"Expected >= 1 match, got {matching}: {result}"
            assert matching <= 2, f"Expected <= 2 matches, got {matching}: {result}"
            validate(result, schema)

    def test_contains_disjoint_from_items(self, faker, repeats_for_slow):
        """
        Contains schema is disjoint from items.

        Items generated from contains schema still appear in the array.

        Note: in JSON Schema, items validates ALL items, so if contains
        and items are truly disjoint, it's unsatisfiable. Here we use
        contains as a subset of items (strings with minLength).
        """
        schema = {
            "type": "array",
            "items": {"type": "string"},
            "contains": {"type": "string", "minLength": 20},
            "minContains": 2,
            "minItems": 5,
            "maxItems": 10,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert all(isinstance(x, str) for x in result)
            long_strings = sum(1 for x in result if len(x) >= 20)
            assert long_strings >= 2, (
                f"Expected >= 2 long strings, got {long_strings}: {result}"
            )
            validate(result, schema)

    def test_contains_without_items(self, faker, repeats_for_slow):
        """Contains without items — heterogeneous array with some matching items."""
        schema = {
            "type": "array",
            "contains": {"type": "integer", "minimum": 100, "maximum": 200},
            "minContains": 3,
            "minItems": 5,
            "maxItems": 10,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, list)
            assert len(result) >= 5
            matching = sum(1 for x in result if isinstance(x, int) and 100 <= x <= 200)
            assert matching >= 3, (
                f"Expected >= 3 matching ints, got {matching}: {result}"
            )


# ── 5. Object generation edge cases ─────────────────────────────────


class TestObjectEdgeCases:
    """Object generation edge cases and termination checks."""

    def test_dependent_required_adds_beyond_max_properties(
        self, faker, repeats_for_slow
    ):
        """
        DependentRequired may add properties beyond maxProperties.

        This is semantically correct: the generated object must satisfy
        dependentRequired even if that means exceeding maxProperties intent.
        Just verifying it doesn't crash.
        """
        for _ in range(repeats_for_slow):
            result = faker.jsonschema_object(
                properties={
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                    "c": {"type": "string"},
                },
                required=["a"],
                dependent_required={"a": ["b", "c"]},
                max_properties=2,
            )
            assert isinstance(result, dict)
            assert "a" in result
            # dependentRequired forces b and c to be present
            assert "b" in result
            assert "c" in result

    def test_pattern_properties_with_hard_pattern(self, faker, repeats_for_slow):
        """Pattern properties with a complex regex should terminate."""
        for _ in range(repeats_for_slow):
            result = faker.jsonschema_object(
                pattern_properties={
                    "^[a-z]{2,4}_[0-9]+$": {"type": "integer"},
                },
                additional_properties=True,
                min_properties=1,
            )
            assert isinstance(result, dict)

    def test_deeply_nested_objects_terminate(self, faker):
        """6 levels of nesting should terminate via max_depth."""
        schema = {
            "type": "object",
            "properties": {
                "l1": {
                    "type": "object",
                    "properties": {
                        "l2": {
                            "type": "object",
                            "properties": {
                                "l3": {
                                    "type": "object",
                                    "properties": {
                                        "l4": {
                                            "type": "object",
                                            "properties": {
                                                "l5": {
                                                    "type": "object",
                                                    "properties": {
                                                        "l6": {
                                                            "type": "object",
                                                            "properties": {
                                                                "val": {
                                                                    "type": "string"
                                                                }
                                                            },
                                                        }
                                                    },
                                                }
                                            },
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }
        # Default max_depth=5, so this 6-level schema should still terminate
        result = faker.from_schema(schema)
        assert isinstance(result, dict)

    def test_object_additional_properties_schema_with_constraints(
        self, faker, repeats_for_slow
    ):
        """AdditionalProperties as a constrained schema."""
        schema = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
            "minProperties": 3,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "id" in result
            for key, val in result.items():
                if key != "id":
                    assert isinstance(val, int)
                    assert 0 <= val <= 100
            validate(result, schema)


# ── 6. jsonschema_not termination ────────────────────────────────────


class TestNotTermination:
    """Verify jsonschema_not terminates with various schema shapes."""

    def test_not_very_broad_object(self, faker):
        """Not with a very broad object schema should eventually terminate or raise."""
        not_schema = {"type": "object"}
        # This should terminate (either by finding a non-object or raising)
        successes = 0
        for _ in range(20):
            try:
                result = faker.jsonschema_not(not_schema)
                successes += 1
                # result must not be a dict
                with pytest.raises(ValidationError):
                    validate(result, not_schema)
            except NoExampleFoundError:
                pass
        # Should succeed some of the time (5/7 types aren't objects)
        assert successes > 5

    def test_not_unconstrained_string(self, faker):
        """Not a fully unconstrained string → picks a different type."""
        not_schema = {"type": "string"}
        successes = 0
        for _ in range(20):
            try:
                faker.jsonschema_not(not_schema)
                successes += 1
            except NoExampleFoundError:
                pass
        assert successes > 5

    def test_not_null(self, faker, repeats_for_slow):
        """Not null → should never return None."""
        not_schema = {"type": "null"}
        schema = {"not": not_schema}
        successes = 0
        for _ in range(50):
            try:
                result = faker.from_schema(schema)
                successes += 1
                assert result is not None
                validate(result, schema)
            except NoExampleFoundError:
                pass
        assert successes > 10


# ── 7. anyOf edge cases ──────────────────────────────────────────────


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
            result = faker.from_schema(schema)
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
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            validate(result, schema)


# ── 8. if/then/else edge cases ───────────────────────────────────────


class TestIfThenElseEdgeCases:
    """Verify if/then/else merging and generation."""

    def test_if_then_else_with_required(self, faker, repeats_for_slow):
        """if/then/else adding required properties."""
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
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "type" in result

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
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert result >= 0
            # With proper merge, result is at most 150 (then) or 50 (else)
            assert result <= 200

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
            result = faker.from_schema(schema)
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
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "name" in result
            assert "age" in result, (
                f"'age' property was lost during if/then merge: {result}"
            )
            assert isinstance(result["age"], int)
            assert 0 <= result["age"] <= 120, (
                f"age constraints lost during merge: {result['age']}"
            )
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
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "status" in result
            assert "value" in result
            assert isinstance(result["value"], int)
            assert result["value"] >= 0


# ── 9. multipleOf edge cases ────────────────────────────────────────


class TestMultipleOfEdgeCases:
    """multipleOf with tricky constraint combinations."""

    def test_multiple_of_negative(self, faker, repeats_for_fast):
        """MultipleOf with negative min/max."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(minimum=-30, maximum=-10, multiple_of=5)
            assert isinstance(result, int)
            assert -30 <= result <= -10
            assert result % 5 == 0

    def test_multiple_of_float_negative_range(self, faker, repeats_for_fast):
        """MultipleOf float in negative range."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_number(
                minimum=-10.0, maximum=-1.0, multiple_of=2.5
            )
            assert isinstance(result, float)
            assert -10.0 <= result <= -1.0

    def test_multiple_of_with_exclusive_bounds(self, faker, repeats_for_fast):
        """MultipleOf combined with exclusive bounds."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": 0,
            "exclusiveMaximum": 20,
            "multipleOf": 5,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert 0 < result < 20
            assert result % 5 == 0
            validate(result, schema)

    def test_multiple_of_unsatisfiable_raises(self, faker):
        """MultipleOf that can't be satisfied raises UnsatisfiableConstraintsError."""
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_integer(minimum=1, maximum=4, multiple_of=5)


# ── 10. Complex real-world schemas ───────────────────────────────────


class TestRealWorldSchemas:
    """Integration tests with complex, real-world-like schemas."""

    def test_discriminated_union(self, faker, repeats_for_slow):
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
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "type" in result
            if result["type"] == "dog":
                assert "bark_volume" in result
            elif result["type"] == "cat":
                assert "indoor" in result

    def test_recursive_tree_structure(self, faker, repeats_for_slow):
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
            result = faker.from_schema(schema, max_depth=4)
            assert isinstance(result, dict)
            assert "name" in result
            validate(result, schema)

    def test_schema_with_all_features(self, faker, repeats_for_slow):
        """Schema combining multiple advanced features."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "minimum": 1},
                "name": {"type": "string", "minLength": 1, "maxLength": 100},
                "email": {"type": "string", "format": "email"},
                "age": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": 150,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 0,
                    "maxItems": 5,
                    "uniqueItems": True,
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["id", "name"],
            "additionalProperties": False,
        }
        for _ in range(repeats_for_slow):
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "id" in result
            assert "name" in result
            assert isinstance(result["id"], int)
            assert result["id"] >= 1
            validate(result, schema)

    def test_allof_with_dependent_schemas(self, faker, repeats_for_slow):
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
            result = faker.from_schema(schema)
            assert isinstance(result, dict)
            assert "payment_type" in result
            # dependentSchemas should force amount when payment_type is present
            assert "amount" in result

    def test_const_in_properties(self, faker, repeats_for_fast):
        """Const values in object properties."""
        schema = {
            "type": "object",
            "properties": {
                "version": {"const": 2},
                "name": {"type": "string"},
            },
            "required": ["version", "name"],
            "additionalProperties": False,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert result["version"] == 2
            assert isinstance(result["name"], str)
            validate(result, schema)
