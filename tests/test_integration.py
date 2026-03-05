"""Integration smoke tests: use faker_jsonschema the way end-users would."""

import pytest
from faker import Faker
from jsonschema import validate

from faker_jsonschema.provider import JSONSchemaProvider


@pytest.fixture()
def fake():
    """Stand-alone Faker instance with the provider added — mirrors user setup."""
    f = Faker()
    f.add_provider(JSONSchemaProvider)
    return f


# ------------------------------------------------------------------
# Basic type round-trips via from_schema
# ------------------------------------------------------------------


def test_string(fake):
    schema = {"type": "string", "minLength": 1, "maxLength": 50}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_integer(fake):
    schema = {"type": "integer", "minimum": 0, "maximum": 100}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_number(fake):
    schema = {"type": "number", "minimum": -1.0, "maximum": 1.0}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_boolean(fake):
    schema = {"type": "boolean"}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_null(fake):
    schema = {"type": "null"}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_array(fake):
    schema = {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 1,
        "maxItems": 5,
    }
    result = fake.from_schema(schema)
    validate(result, schema)


def test_object(fake):
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
        },
        "required": ["name", "age"],
    }
    result = fake.from_schema(schema)
    validate(result, schema)


# ------------------------------------------------------------------
# Slightly more realistic schemas
# ------------------------------------------------------------------


def test_nested_object(fake):
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "zip": {"type": "string", "pattern": "^[0-9]{5}$"},
                },
                "required": ["street", "zip"],
            },
        },
        "required": ["id", "address"],
    }
    result = fake.from_schema(schema)
    validate(result, schema)


def test_array_of_objects(fake):
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "done": {"type": "boolean"},
            },
            "required": ["title", "done"],
        },
        "minItems": 2,
        "maxItems": 4,
    }
    result = fake.from_schema(schema)
    validate(result, schema)


def test_enum(fake):
    schema = {"enum": ["red", "green", "blue"]}
    result = fake.from_schema(schema)
    validate(result, schema)


def test_nullable(fake):
    schema = {"type": "string", "nullable": True}
    # Just ensure it doesn't explode; value is either str or None.
    result = fake.from_schema(schema)
    assert result is None or isinstance(result, str)


def test_anyof(fake):
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    result = fake.from_schema(schema)
    assert isinstance(result, (str, int))


def test_string_formats(fake):
    """Spot-check a few common string formats."""
    for fmt in ("date", "date-time", "email", "uri", "uuid"):
        schema = {"type": "string", "format": fmt}
        result = fake.from_schema(schema)
        validate(result, schema)


def test_ref(fake):
    schema = {
        "type": "object",
        "properties": {
            "billing": {"$ref": "#/$defs/address"},
            "shipping": {"$ref": "#/$defs/address"},
        },
        "$defs": {
            "address": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                },
                "required": ["city"],
            },
        },
    }
    result = fake.from_schema(schema)
    validate(result, schema)


# ------------------------------------------------------------------
# Repeated generation doesn't crash (statelessness check)
# ------------------------------------------------------------------


def test_repeated_calls(fake):
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }
    for _ in range(20):
        result = fake.from_schema(schema)
        validate(result, schema)


# ------------------------------------------------------------------
# Seeding produces deterministic output
# ------------------------------------------------------------------


def test_seeded_determinism():
    schema = {"type": "object", "properties": {"v": {"type": "integer"}}}

    Faker.seed(42)
    a = Faker()
    a.add_provider(JSONSchemaProvider)
    result_a = a.from_schema(schema)

    Faker.seed(42)
    b = Faker()
    b.add_provider(JSONSchemaProvider)
    result_b = b.from_schema(schema)

    assert result_a == result_b
