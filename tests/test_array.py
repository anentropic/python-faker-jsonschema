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
    )
)
def test_jsonschema_array_items(
    faker, repeats_for_slow, schema
):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(items=schema)
        assert isinstance(result, list)
        for item in result:
            validate(item, schema)


@pytest.mark.parametrize(
    "min_items,max_items,unique_items",
    itertools.product(
        (0, 3, 5, 11),
        (None, 15, 20, 25),
        (True, False)
    )
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
