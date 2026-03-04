import itertools
import re

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


# ── Existing tests ───────────────────────────────────────────────────


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


# ── Negative / edge-case tests ───────────────────────────────────────


def test_jsonschema_object_negative_min_properties(faker):
    with pytest.raises(ValueError, match="minProperties must be >= 0"):
        faker.jsonschema_object(min_properties=-1)


def test_jsonschema_object_max_lt_min(faker):
    with pytest.raises(ValueError, match="maxProperties must be >= minProperties"):
        faker.jsonschema_object(min_properties=5, max_properties=3)


def test_jsonschema_object_max_lt_required(faker, properties):
    with pytest.raises(UnsatisfiableConstraintsError, match="maxProperties"):
        faker.jsonschema_object(
            properties=properties,
            required=list(properties.keys()),
            max_properties=1,
        )


def test_jsonschema_object_min_eq_max(faker, repeats_for_slow):
    """minProperties == maxProperties → exact count."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            min_properties=5,
            max_properties=5,
        )
        assert len(result) == 5


def test_jsonschema_object_empty_schema(faker, repeats_for_slow):
    """Empty object schema {} → returns a dict."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object()
        assert isinstance(result, dict)


def test_jsonschema_object_no_properties_no_additional(faker):
    """additionalProperties=False, no properties, minProperties=0 → {}."""
    result = faker.jsonschema_object(
        additional_properties=False,
        min_properties=0,
    )
    assert result == {}


def test_jsonschema_object_required_not_in_properties(faker, repeats_for_slow):
    """Required keys not listed in properties should still be generated."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={"a": {"type": "string"}},
            required=["a", "b", "c"],
        )
        assert "a" in result
        assert "b" in result
        assert "c" in result
        assert isinstance(result["a"], str)


def test_jsonschema_object_large_min_additional_only(faker):
    """Large minProperties with additionalProperties=True, no declared properties."""
    result = faker.jsonschema_object(
        min_properties=20,
        max_properties=20,
    )
    assert len(result) == 20


def test_jsonschema_object_min_satisfiable_with_non_required(faker, repeats_for_slow):
    """
    B1 regression: minProperties > len(required) but <= len(properties)
    should NOT raise (previously did).
    """
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={
                "a": {"type": "string"},
                "b": {"type": "integer"},
                "c": {"type": "number"},
                "d": {"type": "boolean"},
                "e": {"type": "string"},
            },
            required=["a"],
            additional_properties=False,
            min_properties=3,
            max_properties=5,
        )
        assert len(result) >= 3
        assert len(result) <= 5
        assert "a" in result


# ── additionalProperties as schema ───────────────────────────────────


def test_jsonschema_object_additional_properties_schema(faker, repeats_for_slow):
    """additionalProperties as a schema → extra values conform to it."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": {"type": "integer"},
        "minProperties": 3,
    }
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={"name": {"type": "string"}},
            required=["name"],
            additional_properties={"type": "integer"},
            min_properties=3,
        )
        assert isinstance(result, dict)
        assert "name" in result
        assert isinstance(result["name"], str)
        for key, val in result.items():
            if key != "name":
                assert isinstance(val, int), f"Key {key!r} should be int, got {type(val)}"
        validate(result, schema)


def test_jsonschema_object_additional_properties_false_strict(faker, repeats_for_slow):
    """additionalProperties=False → only declared properties appear."""
    props = {"x": {"type": "string"}, "y": {"type": "integer"}}
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties=props,
            required=["x", "y"],
            additional_properties=False,
        )
        assert set(result.keys()) <= {"x", "y"}


# ── patternProperties ────────────────────────────────────────────────


def test_jsonschema_object_pattern_properties(faker, repeats_for_slow):
    """patternProperties → at least one key matching each pattern."""
    schema = {
        "type": "object",
        "patternProperties": {
            "^S_": {"type": "string"},
            "^I_": {"type": "integer"},
        },
        "additionalProperties": False,
        "minProperties": 2,
        "maxProperties": 4,
    }
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            pattern_properties={
                "^S_": {"type": "string"},
                "^I_": {"type": "integer"},
            },
            additional_properties=False,
            min_properties=2,
            max_properties=4,
        )
        assert isinstance(result, dict)
        assert len(result) >= 2
        # at least one key matching each pattern should exist
        s_keys = [k for k in result if re.search("^S_", k)]
        i_keys = [k for k in result if re.search("^I_", k)]
        assert len(s_keys) >= 1
        assert len(i_keys) >= 1
        for k in s_keys:
            assert isinstance(result[k], str)
        for k in i_keys:
            assert isinstance(result[k], int)


def test_jsonschema_object_pattern_properties_with_properties(faker, repeats_for_slow):
    """patternProperties combined with properties."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={"name": {"type": "string"}},
            pattern_properties={"^x_": {"type": "number"}},
            required=["name"],
            additional_properties=False,
            min_properties=2,
        )
        assert "name" in result
        assert isinstance(result["name"], str)
        assert len(result) >= 2


# ── dependentRequired ────────────────────────────────────────────────


def test_jsonschema_object_dependent_required(faker, repeats_for_slow):
    """dependentRequired: presence of trigger guarantees dependent keys."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={
                "credit_card": {"type": "string"},
                "billing_address": {"type": "string"},
                "phone": {"type": "string"},
            },
            required=["credit_card"],
            dependent_required={
                "credit_card": ["billing_address"],
            },
            additional_properties=False,
        )
        assert "credit_card" in result
        assert "billing_address" in result

    schema = {
        "type": "object",
        "properties": {
            "credit_card": {"type": "string"},
            "billing_address": {"type": "string"},
            "phone": {"type": "string"},
        },
        "required": ["credit_card"],
        "dependentRequired": {
            "credit_card": ["billing_address"],
        },
        "additionalProperties": False,
    }
    validate(result, schema)


def test_jsonschema_object_dependent_required_trigger_absent(faker, repeats_for_slow):
    """dependentRequired: trigger key absent → dependent not forced."""
    for _ in range(repeats_for_slow):
        # don't require the trigger key
        result = faker.jsonschema_object(
            properties={
                "credit_card": {"type": "string"},
                "billing_address": {"type": "string"},
            },
            dependent_required={
                "credit_card": ["billing_address"],
            },
            additional_properties=False,
        )
        # if credit_card happens to be present, billing_address must also be
        if "credit_card" in result:
            assert "billing_address" in result


# ── dependentSchemas ─────────────────────────────────────────────────


def test_jsonschema_object_dependent_schemas(faker, repeats_for_slow):
    """dependentSchemas: trigger present → dependent schema properties generated."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={
                "name": {"type": "string"},
            },
            required=["name"],
            dependent_schemas={
                "name": {
                    "type": "object",
                    "required": ["age"],
                    "properties": {
                        "age": {"type": "integer", "minimum": 0, "maximum": 150},
                    },
                },
            },
            additional_properties=False,
        )
        assert "name" in result
        assert "age" in result
        assert isinstance(result["age"], int)
        assert 0 <= result["age"] <= 150


# ── unevaluatedProperties ───────────────────────────────────────────


def test_jsonschema_object_unevaluated_properties_false(faker, repeats_for_slow):
    """unevaluatedProperties: false → no extra properties beyond declared."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            required=["name", "age"],
            unevaluated_properties=False,
        )
        assert set(result.keys()) <= {"name", "age"}


def test_jsonschema_object_unevaluated_properties_schema(faker, repeats_for_slow):
    """unevaluatedProperties as schema → extra values conform to it."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_object(
            properties={
                "name": {"type": "string"},
            },
            required=["name"],
            unevaluated_properties={"type": "boolean"},
            min_properties=3,
        )
        assert "name" in result
        assert isinstance(result["name"], str)
        for key, val in result.items():
            if key != "name":
                assert isinstance(val, bool), (
                    f"unevaluated key {key!r} should be bool, got {type(val)}"
                )


# ── if / then / else ─────────────────────────────────────────────────


def test_jsonschema_object_if_then_else_via_from_schema(faker, repeats_for_slow):
    """if/then/else at schema level via from_schema."""
    schema = {
        "type": "object",
        "properties": {
            "street_address": {"type": "string"},
            "country": {"type": "string"},
        },
        "required": ["street_address", "country"],
        "if": {
            "properties": {"country": {"const": "United States of America"}}
        },
        "then": {
            "properties": {"postal_code": {"type": "string"}}
        },
        "else": {
            "properties": {"postal_code": {"type": "string"}}
        },
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "street_address" in result
        assert "country" in result


# ── from_schema integration tests ────────────────────────────────────


def test_from_schema_basic_object(faker, repeats_for_slow):
    """from_schema round-trip with a basic object schema."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
        },
        "required": ["name", "age"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "name" in result
        assert "age" in result
        validate(result, schema)


def test_from_schema_additional_properties_as_schema(faker, repeats_for_slow):
    """from_schema with additionalProperties as a schema."""
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
        },
        "required": ["id"],
        "additionalProperties": {"type": "string"},
        "minProperties": 3,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "id" in result
        validate(result, schema)


def test_from_schema_nested_object(faker, repeats_for_slow):
    """from_schema with nested object-in-object."""
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name", "email"],
                "additionalProperties": False,
            },
            "score": {"type": "number"},
        },
        "required": ["user", "score"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "user" in result
        assert isinstance(result["user"], dict)
        assert "name" in result["user"]
        assert "email" in result["user"]
        validate(result, schema)


def test_from_schema_allof_objects(faker, repeats_for_slow):
    """from_schema with allOf containing multiple object schemas."""
    schema = {
        "allOf": [
            {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
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
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
        assert isinstance(result["id"], int)
        assert isinstance(result["name"], str)


def test_from_schema_pattern_properties(faker, repeats_for_slow):
    """from_schema with patternProperties."""
    schema = {
        "type": "object",
        "patternProperties": {
            "^S_": {"type": "string"},
        },
        "additionalProperties": False,
        "minProperties": 1,
        "maxProperties": 3,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        for key in result:
            assert re.search("^S_", key), f"Key {key!r} should match pattern ^S_"
            assert isinstance(result[key], str)


# ── anyOf / allOf regression tests ───────────────────────────────────


def test_anyof_multiple_types_including_objects(faker, repeats_for_slow):
    """anyOf with mixed types (object + string) shouldn't crash (B4 regression)."""
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]},
            {"type": "string"},
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, (dict, str))
        if isinstance(result, dict):
            assert "x" in result


def test_allof_two_object_schemas(faker, repeats_for_slow):
    """allOf with 2 object schemas → merged properties (B5 regression)."""
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
            },
            {
                "type": "object",
                "properties": {"b": {"type": "integer"}},
                "required": ["b"],
            },
        ]
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "a" in result
        assert "b" in result
        assert isinstance(result["a"], str)
        assert isinstance(result["b"], int)
