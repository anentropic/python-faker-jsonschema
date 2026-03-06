"""Integration contract smoke tests for end-user Faker usage."""

import pytest
from faker import Faker
from jsonschema import validate

from faker_jsonschema.provider import JSONSchemaProvider


@pytest.fixture()
def fake():
    """Stand-alone Faker instance with the provider added, like end users."""
    f = Faker()
    f.add_provider(JSONSchemaProvider)
    return f


def test_provider_registration_exposes_expected_entry_points(fake):
    assert callable(getattr(fake, "from_jsonschema", None))


def test_from_jsonschema_round_trip_smoke(fake):
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    result = fake.from_jsonschema(schema)
    validate(result, schema)


def test_nested_schema_smoke(fake):
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
    result = fake.from_jsonschema(schema)
    validate(result, schema)


def test_seeded_determinism():
    schema = {"type": "object", "properties": {"v": {"type": "integer"}}}

    Faker.seed(42)
    a = Faker()
    a.add_provider(JSONSchemaProvider)
    result_a = a.from_jsonschema(schema)

    Faker.seed(42)
    b = Faker()
    b.add_provider(JSONSchemaProvider)
    result_b = b.from_jsonschema(schema)

    assert result_a == result_b
