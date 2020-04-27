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
def test_jsonschema_array_from_schema(
    faker, repeats_for_slow, schema
):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(items=schema)
        assert isinstance(result, list)
        for item in result:
            validate(item, schema)
