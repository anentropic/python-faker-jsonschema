"""Tests for jsonschema_not() — 'not' schemas."""

import pytest
from jsonschema import ValidationError, validate

from faker_jsonschema.provider import NoExampleFoundError


def test_jsonschema_not_constrained_string(faker, repeats_for_slow):
    """Not a constrained string → value should not match the constraints."""
    # Use a constrained schema so there's a chance of generating non-matching values
    not_schema = {"type": "string", "minLength": 10, "maxLength": 20}
    schema = {"not": not_schema}
    successes = 0
    for _ in range(repeats_for_slow):
        try:
            result = faker.from_schema(schema)
        except NoExampleFoundError:
            # acceptable — the random type chosen was string and couldn't
            # find a non-matching string in `max_search` attempts
            continue
        successes += 1
        validate(result, schema)
    assert successes > 0, "Should succeed at least once"


def test_jsonschema_not_type_integer(faker, repeats_for_slow):
    """Not a constrained integer → value should not match the constraints."""
    not_schema = {"type": "integer", "minimum": 0, "maximum": 10}
    schema = {"not": not_schema}
    successes = 0
    for _ in range(repeats_for_slow):
        try:
            result = faker.from_schema(schema)
        except NoExampleFoundError:
            continue
        successes += 1
        validate(result, schema)
    assert successes > 0, "Should succeed at least once"


def test_jsonschema_not_type_boolean(faker, repeats_for_slow):
    """from_schema({"not": {"type": "boolean"}}) should produce non-booleans."""
    schema = {"not": {"type": "boolean"}}
    successes = 0
    for _ in range(repeats_for_slow):
        try:
            result = faker.from_schema(schema)
        except NoExampleFoundError:
            continue
        successes += 1
        validate(result, schema)
    assert successes > 0, "Should succeed at least once"


def test_jsonschema_not_type_number(faker, repeats_for_slow):
    """Not a number schema → result should fail validation against it."""
    not_schema = {"type": "number", "minimum": 0, "maximum": 100}
    schema = {"not": not_schema}
    successes = 0
    for _ in range(repeats_for_slow):
        try:
            result = faker.from_schema(schema)
        except NoExampleFoundError:
            continue
        successes += 1
        validate(result, schema)
    assert successes > 0, "Should succeed at least once"


def test_jsonschema_not_direct_call(faker, repeats_for_slow):
    """Direct call to jsonschema_not with a constrained integer schema."""
    not_schema = {"type": "integer", "minimum": 0, "maximum": 10}
    successes = 0
    for _ in range(repeats_for_slow):
        try:
            result = faker.jsonschema_not(not_schema)
        except NoExampleFoundError:
            continue
        successes += 1
        # verify it does NOT validate against the not_schema
        with pytest.raises(ValidationError):
            validate(result, not_schema)
    assert successes > 0, "Should succeed at least once"


def test_jsonschema_not_different_type_always_passes(faker, repeats_for_slow):
    """When not picks a different type, it always succeeds without search."""
    # Use a type that's 1 of 6 basic types, so most random picks will differ
    not_schema = {"type": "boolean"}
    successes = 0
    for _ in range(50):  # more iterations for statistical confidence
        try:
            result = faker.jsonschema_not(not_schema)
        except NoExampleFoundError:
            continue
        successes += 1
        with pytest.raises(ValidationError):
            validate(result, not_schema)
    # boolean is 1/6 of types, so we should succeed most of the time
    assert successes > 10, f"Only {successes}/50 successes, expected more"
