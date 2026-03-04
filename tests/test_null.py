"""Tests for null type support."""

from jsonschema import validate


# ── Direct call ──────────────────────────────────────────────────────


def test_jsonschema_null(faker):
    """jsonschema_null() always returns None."""
    for _ in range(10):
        result = faker.jsonschema_null()
        assert result is None


# ── from_schema round-trip ───────────────────────────────────────────


def test_from_schema_null(faker, repeats_for_fast):
    """from_schema with type null → always None."""
    schema = {"type": "null"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result is None
        validate(result, schema)


def test_from_schema_null_with_enum(faker, repeats_for_fast):
    """null type with enum containing only None."""
    schema = {"type": "null", "enum": [None]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result is None
        validate(result, schema)
