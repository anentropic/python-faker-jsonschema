import itertools

import pytest
from jsonschema import validate


@pytest.mark.parametrize(
    "schema",
    (
        {},
        {"type": "string"},
        {"type": "number"},
        # example from "petstore-expanded.yml"...
        {
            "allOf": [
                {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "integer", "format": "int64"},
                    },
                },
                {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "tag": {"type": "string"},
                    },
                },
            ]
        },
    ),
)
def test_jsonschema_array_items(faker, repeats_for_slow, schema):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(items=schema)
        assert isinstance(result, list)
        for item in result:
            validate(item, schema)


@pytest.mark.parametrize(
    "min_items,max_items,unique_items",
    itertools.product((0, 3, 5, 11), (None, 15, 20, 25), (True, False)),
)
def test_jsonschema_array_length(
    faker, repeats_for_slow, min_items, max_items, unique_items
):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            items={"type": "number"},
            min_items=min_items,
            max_items=max_items,
            unique_items=unique_items,
        )
        assert isinstance(result, list)
        assert len(result) >= min_items
        if max_items is not None:
            assert len(result) <= max_items
        if unique_items:
            # NOTE: set len relies on type: number (not object/array)
            assert len(set(result)) == len(result)


# ── from_schema round-trip tests ─────────────────────────────────────────


def test_from_schema_array_basic(faker, repeats_for_slow):
    """from_schema round trip with array type."""
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 100},
        "minItems": 1,
        "maxItems": 5,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        validate(result, schema)


def test_from_schema_array_unique_items(faker, repeats_for_slow):
    """from_schema round trip with uniqueItems."""
    schema = {
        "type": "array",
        "items": {"type": "string"},
        "uniqueItems": True,
        "minItems": 2,
        "maxItems": 5,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        validate(result, schema)


def test_from_schema_array_no_items(faker, repeats_for_slow):
    """from_schema round trip without explicit items schema."""
    schema = {
        "type": "array",
        "minItems": 0,
        "maxItems": 3,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert len(result) <= 3


def test_jsonschema_array_full_schema_validation(faker, repeats_for_slow):
    """Validate full array against the complete array schema."""
    schema = {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 10,
    }
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            items={"type": "number"},
            min_items=2,
            max_items=10,
        )
        validate(result, schema)


# ── Negative / edge-case tests ───────────────────────────────────────


def test_jsonschema_array_negative_min_items(faker):
    with pytest.raises(ValueError, match="minItems must be >= 0"):
        faker.jsonschema_array(min_items=-1)


def test_jsonschema_array_max_lt_min(faker):
    with pytest.raises(ValueError, match="maxItems must be >= minItems"):
        faker.jsonschema_array(min_items=5, max_items=3)


def test_jsonschema_array_empty(faker, repeats_for_slow):
    """minItems=0, maxItems=0 → always empty list."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            items={"type": "string"},
            min_items=0,
            max_items=0,
        )
        assert result == []


# ── uniqueItems edge cases ───────────────────────────────────────────


class TestArrayUniqueItemsEdgeCases:
    """Array uniqueItems edge cases that could hang or produce wrong results."""

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


# ── prefixItems / additionalItems ────────────────────────────────────


def test_prefix_items_basic(faker, repeats_for_slow):
    """PrefixItems with different types for each position."""
    schema = {
        "type": "array",
        "prefixItems": [
            {"type": "string"},
            {"type": "integer"},
            {"type": "boolean"},
        ],
        "items": False,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert len(result) == 3
        assert isinstance(result[0], str)
        assert isinstance(result[1], int) and not isinstance(result[1], bool)
        assert isinstance(result[2], bool)
        validate(result, schema)


def test_prefix_items_with_additional(faker, repeats_for_slow):
    """PrefixItems with items schema for additional items."""
    schema = {
        "type": "array",
        "prefixItems": [
            {"type": "string"},
            {"type": "integer"},
        ],
        "items": {"type": "boolean"},
        "minItems": 4,
        "maxItems": 6,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert 4 <= len(result) <= 6
        assert isinstance(result[0], str)
        assert isinstance(result[1], int) and not isinstance(result[1], bool)
        for item in result[2:]:
            assert isinstance(item, bool)
        validate(result, schema)


def test_prefix_items_direct(faker, repeats_for_slow):
    """Direct call with prefix_items."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "number"},
                {"type": "string"},
            ],
            min_items=2,
            max_items=2,
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], (int, float))
        assert isinstance(result[1], str)


def test_empty_prefix_items_with_items_false(faker, repeats_for_slow):
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


def test_additional_items_false(faker, repeats_for_slow):
    """additionalItems: false with prefixItems → exactly N items."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "string"},
                {"type": "integer"},
            ],
            additional_items=False,
            min_items=2,
            max_items=2,
        )
        assert isinstance(result, list)
        assert len(result) == 2


def test_additional_items_schema(faker, repeats_for_slow):
    """AdditionalItems as schema → extra items match that schema."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "string"},
            ],
            additional_items={"type": "boolean"},
            min_items=3,
            max_items=5,
        )
        assert isinstance(result, list)
        assert len(result) >= 3
        assert isinstance(result[0], str)
        for item in result[1:]:
            assert isinstance(item, bool)


def test_array_zero_max_items(faker, repeats_for_slow):
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


# ── contains / minContains / maxContains ─────────────────────────────


def test_contains_basic(faker, repeats_for_slow):
    """Contains → at least one item matches."""
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 100},
        "contains": {"type": "integer", "minimum": 50, "maximum": 100},
        "minItems": 3,
        "maxItems": 10,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert any(isinstance(x, int) and x >= 50 for x in result)
        validate(result, schema)


def test_min_contains(faker, repeats_for_slow):
    """MinContains → at least N items match contains."""
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 100},
        "contains": {"type": "integer", "minimum": 50, "maximum": 100},
        "minContains": 3,
        "minItems": 5,
        "maxItems": 15,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        matching = sum(1 for x in result if isinstance(x, int) and x >= 50)
        assert matching >= 3
        validate(result, schema)


def test_contains_direct(faker, repeats_for_slow):
    """Direct call with contains."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            items={"type": "string"},
            contains={"type": "string", "minLength": 10},
            min_items=3,
            max_items=10,
        )
        assert isinstance(result, list)
        # At least one string with length >= 10
        assert any(isinstance(x, str) and len(x) >= 10 for x in result)


def test_contains_with_tight_constraints(faker, repeats_for_slow):
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


def test_contains_tight_maxitems_equals_mincontains(faker, repeats_for_slow):
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


def test_contains_with_maxcontains(faker, repeats_for_slow):
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


def test_contains_disjoint_from_items(faker, repeats_for_slow):
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


def test_contains_without_items(faker, repeats_for_slow):
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
        assert matching >= 3, f"Expected >= 3 matching ints, got {matching}: {result}"
