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
