"""Tests for jsonschema_not() — 'not' schemas."""

import pytest
from jsonschema import ValidationError, validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError


def test_jsonschema_not_constrained_string(faker, repeats_for_slow):
    """Not a constrained string -> value should not match the constraints."""
    not_schema = {"type": "string", "minLength": 10, "maxLength": 20}
    schema = {"not": not_schema}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        validate(result, schema)


def test_jsonschema_not_type_integer(faker, repeats_for_slow):
    """Not a constrained integer -> value should not match the constraints."""
    not_schema = {"type": "integer", "minimum": 0, "maximum": 10}
    schema = {"not": not_schema}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        validate(result, schema)


def test_jsonschema_not_type_boolean(faker, repeats_for_slow):
    """from_schema({"not": {"type": "boolean"}}) should produce non-booleans."""
    schema = {"not": {"type": "boolean"}}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        validate(result, schema)


def test_jsonschema_not_type_number(faker, repeats_for_slow):
    """Not a number schema -> result should fail validation against it."""
    not_schema = {"type": "number", "minimum": 0, "maximum": 100}
    schema = {"not": not_schema}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        validate(result, schema)


def test_jsonschema_not_direct_call(faker, repeats_for_slow):
    """Direct call to jsonschema_not with a constrained integer schema."""
    not_schema = {"type": "integer", "minimum": 0, "maximum": 10}
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_not(not_schema)
        # verify it does NOT validate against the not_schema
        with pytest.raises(ValidationError):
            validate(result, not_schema)


def test_jsonschema_not_different_type_always_passes(faker):
    """With type biasing, not always succeeds by picking a different type."""
    not_schema = {"type": "boolean"}
    for _ in range(50):
        result = faker.jsonschema_not(not_schema)
        with pytest.raises(ValidationError):
            validate(result, not_schema)


# -- unsatisfiable not schemas -----------------------------------------------


def test_not_empty_schema_raises(faker):
    """not: {} forbids all values; should raise immediately."""
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.from_jsonschema({"not": {}})


def test_not_true_schema_raises(faker):
    """not: true is equivalent to not: {} and is equally unsatisfiable."""
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.jsonschema_not(True)


# -- not termination edge cases ----------------------------------------------


class TestNotTermination:
    """Verify jsonschema_not terminates reliably with various schema shapes."""

    def test_not_very_broad_object(self, faker):
        """Not with a very broad object schema should always succeed."""
        not_schema = {"type": "object"}
        for _ in range(20):
            result = faker.jsonschema_not(not_schema)
            with pytest.raises(ValidationError):
                validate(result, not_schema)

    def test_not_unconstrained_string(self, faker):
        """Not a fully unconstrained string -> picks a different type."""
        not_schema = {"type": "string"}
        for _ in range(20):
            faker.jsonschema_not(not_schema)

    def test_not_null(self, faker):
        """Not null -> should never return None."""
        not_schema = {"type": "null"}
        schema = {"not": not_schema}
        for _ in range(50):
            result = faker.from_jsonschema(schema)
            assert result is not None
            validate(result, schema)
