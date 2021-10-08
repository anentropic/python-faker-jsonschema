import itertools

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError


@pytest.fixture()
def properties():
    return {
        "any": {},
        "str": {"type": "string"},
        "num": {"type": "number"},
        # example from "petstore-expanded.yml"...
        "petstore": {
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
    }


def test_jsonschema_object_properties(
    faker, repeats_for_slow, properties
):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties=properties,
            required=list(properties.keys()),
            additional_properties=False
        )
        assert isinstance(result, dict)
        for key, val in result.items():
            validate(val, properties[key])


@pytest.mark.parametrize(
    "min_properties,max_properties,additional_properties",
    itertools.product(
        (0, 3, 5, 11),
        (None, 15, 20, 25),
        (True, False)
    )
)
def test_jsonschema_object_length(
    faker, repeats_for_slow, min_properties, max_properties, additional_properties
):
    for _ in range(repeats_for_slow):
        if not additional_properties and min_properties > 0:
            with pytest.raises(UnsatisfiableConstraintsError):
                faker.jsonschema_object(
                    min_properties=min_properties,
                    max_properties=max_properties,
                    additional_properties=additional_properties,
                )
            continue

        result = faker.jsonschema_object(
            min_properties=min_properties,
            max_properties=max_properties,
            additional_properties=additional_properties,
        )
        assert isinstance(result, dict)
        assert len(result) >= min_properties
        if max_properties is not None and not additional_properties:
            assert len(result) <= max_properties

        schema = {
            key: val
            for key, val in (
                ("type", "object"),
                ("minProperties", min_properties),
                ("maxProperties", max_properties),
                ("additionalProperties", additional_properties),
            )
            if val is not None
        }
        validate(result, schema)


@pytest.mark.parametrize(
    "required",
    (
        list(comb)
        for i in range(1, 5)
        for comb in itertools.combinations(
            ["any", "str", "num", "petstore"], i
        )
    )
)
def test_jsonschema_object_required(
    faker, properties, required
):
    result = faker.jsonschema_object(
        properties=properties,
        required=required,
        additional_properties=False,
    )
    assert isinstance(result, dict)
    assert all(key in result for key in required)
    schema = {
        key: val
        for key, val in (
            ("type", "object"),
            ("properties", properties),
            ("required", required),
            ("additionalProperties", False),
        )
        if val is not None
    }
    validate(result, schema)


@pytest.mark.parametrize(
    "property_names",
    (
        {"pattern": "^[a-zA-Z0-9\\.\\-_]+$"},
        {"pattern": "[\\w\\.-]+@[\\w\\.-]+"},
        {"pattern": "^(\\([0-9]{3}\\))?[0-9]{3}-[0-9]{4}$"},
        {"pattern": "^\\w{3}\\d{2,4}$"},
        {"minLength": 3, "maxLength": 5},
        {"minLength": 13, "maxLength": 15},
    )
)
def test_jsonschema_object_property_names(
    faker, property_names
):
    result = faker.jsonschema_object(
        properties=None,
        property_names=property_names,
        additional_properties=True,
        min_properties=10,
        max_properties=10,
    )
    assert isinstance(result, dict)
    schema = {
        key: val
        for key, val in (
            ("type", "object"),
            ("properties", None),
            ("propertyNames", property_names),
            ("minProperties", 10),
            ("maxProperties", 10),
            ("additionalProperties", True),
        )
        if val is not None
    }
    validate(result, schema)
