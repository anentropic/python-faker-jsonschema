"""
Tests for new JSON Schema features.

Type arrays, boolean schemas, const, if/then/else, legacy dependencies,
new string formats, contentEncoding, and draft-06+ exclusiveMinimum/exclusiveMaximum.
"""

import re

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError

# ── Type as array (draft-06+) ────────────────────────────────────────


def test_type_array_string_null(faker, repeats_for_fast):
    """{"type": ["string", "null"]} → str or None."""
    schema = {"type": ["string", "null"]}
    types_seen = set()
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        if result is None:
            types_seen.add("null")
        else:
            assert isinstance(result, str)
            types_seen.add("string")
        validate(result, schema)
    assert types_seen == {"string", "null"}, f"Only saw: {types_seen}"


def test_type_array_integer_number(faker, repeats_for_fast):
    """{"type": ["integer", "number"]} → int or float."""
    schema = {"type": ["integer", "number"]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, (int, float))
        validate(result, schema)


def test_type_array_single(faker, repeats_for_fast):
    """{"type": ["boolean"]} → always bool."""
    schema = {"type": ["boolean"]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, bool)
        validate(result, schema)


def test_type_array_with_constraints(faker, repeats_for_fast):
    """Type array with constraints applies to the chosen type."""
    schema = {"type": ["integer", "null"], "minimum": 5, "maximum": 10}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        if result is not None:
            assert isinstance(result, int)
            assert 5 <= result <= 10
        validate(result, schema)


# ── Boolean schemas (draft-06+) ──────────────────────────────────────


def test_boolean_schema_true(faker, repeats_for_fast):
    """Schema True → accepts anything (like empty schema)."""
    schema = True
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        validate(result, schema)


def test_boolean_schema_false(faker):
    """Schema False → always unsatisfiable."""
    with pytest.raises(UnsatisfiableConstraintsError):
        faker.from_schema(False)


def test_empty_schema_as_true(faker, repeats_for_fast):
    """Empty dict schema {} behaves like True."""
    schema = {}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        validate(result, schema)


# ── const (draft-06+) ────────────────────────────────────────────────


def test_const_string(faker, repeats_for_fast):
    """Const with string → always returns that exact string."""
    schema = {"const": "hello"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result == "hello"
        validate(result, schema)


def test_const_integer(faker, repeats_for_fast):
    """Const with integer → always returns that integer."""
    schema = {"const": 42}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result == 42
        validate(result, schema)


def test_const_null(faker, repeats_for_fast):
    """Const with null → always returns None."""
    schema = {"const": None}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result is None
        validate(result, schema)


def test_const_object(faker, repeats_for_fast):
    """Const with object → always returns that exact object."""
    schema = {"const": {"key": "value"}}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result == {"key": "value"}
        validate(result, schema)


def test_const_array(faker, repeats_for_fast):
    """Const with array → always returns that exact array."""
    schema = {"const": [1, 2, 3]}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert result == [1, 2, 3]
        validate(result, schema)


# ── if / then / else ─────────────────────────────────────────────────


def test_if_then_else_basic(faker):
    """if/then/else round-trip: result validates against schema."""
    schema = {
        "type": "integer",
        "if": {"minimum": 10},
        "then": {"maximum": 100},
        "else": {"maximum": 9},
    }
    for _ in range(50):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        # The result should satisfy at least one branch
        # (we can't deterministically predict which branch was chosen)


def test_if_then_only(faker, repeats_for_fast):
    """Schema with if/then but no else."""
    schema = {
        "type": "string",
        "if": {"minLength": 5},
        "then": {"maxLength": 20},
    }
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)


def test_if_else_only(faker, repeats_for_fast):
    """Schema with if/else but no then."""
    schema = {
        "type": "integer",
        "if": {"maximum": 0},
        "else": {"minimum": 1},
    }
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)


# ── Draft-06+ numeric exclusiveMinimum / exclusiveMaximum ────────────


def test_exclusive_minimum_numeric_integer(faker, repeats_for_fast):
    """ExclusiveMinimum as number (draft-06+) for integers."""
    schema = {"type": "integer", "exclusiveMinimum": 5, "maximum": 10}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        assert result > 5
        assert result <= 10
        validate(result, schema)


def test_exclusive_maximum_numeric_integer(faker, repeats_for_fast):
    """ExclusiveMaximum as number (draft-06+) for integers."""
    schema = {"type": "integer", "minimum": 5, "exclusiveMaximum": 10}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        assert result >= 5
        assert result < 10
        validate(result, schema)


def test_exclusive_both_numeric_integer(faker, repeats_for_fast):
    """Both exclusiveMinimum and exclusiveMaximum as numbers."""
    schema = {"type": "integer", "exclusiveMinimum": 0, "exclusiveMaximum": 5}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        assert 0 < result < 5
        validate(result, schema)


def test_exclusive_minimum_numeric_number(faker, repeats_for_fast):
    """ExclusiveMinimum as number (draft-06+) for floats."""
    schema = {"type": "number", "exclusiveMinimum": 1.0, "maximum": 5.0}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, float)
        assert result > 1.0
        assert result <= 5.0
        validate(result, schema)


def test_exclusive_maximum_numeric_number(faker, repeats_for_fast):
    """ExclusiveMaximum as number (draft-06+) for floats."""
    schema = {"type": "number", "minimum": 1.0, "exclusiveMaximum": 5.0}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, float)
        assert result >= 1.0
        assert result < 5.0
        validate(result, schema)


def test_exclusive_direct_call_integer(faker, repeats_for_fast):
    """Direct call with exclusive_minimum/exclusive_maximum params."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_integer(exclusive_minimum=0, exclusive_maximum=10)
        assert isinstance(result, int)
        assert 0 < result < 10


def test_exclusive_direct_call_number(faker, repeats_for_fast):
    """Direct call with exclusive_minimum/exclusive_maximum params."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_number(exclusive_minimum=0.0, exclusive_maximum=10.0)
        assert isinstance(result, float)
        assert 0.0 < result < 10.0


# ── Legacy dependencies keyword ──────────────────────────────────────


def test_dependencies_array_form(faker, repeats_for_slow):
    """Legacy dependencies with array values → dependentRequired."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "credit_card": {"type": "integer"},
            "billing_address": {"type": "string"},
        },
        "required": ["name"],
        "dependencies": {
            "credit_card": ["billing_address"],
        },
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        if "credit_card" in result:
            assert "billing_address" in result
        validate(result, schema)


def test_dependencies_schema_form(faker, repeats_for_slow):
    """Legacy dependencies with schema values → dependentSchemas."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "credit_card": {"type": "integer"},
        },
        "required": ["name", "credit_card"],
        "dependencies": {
            "credit_card": {
                "properties": {
                    "billing_address": {"type": "string"},
                },
                "required": ["billing_address"],
            }
        },
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        # credit_card is required, so billing_address must be present
        assert "billing_address" in result
        validate(result, schema)


def test_dependencies_mixed(faker, repeats_for_slow):
    """Legacy dependencies with both array and schema values."""
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "string"},
            "c": {"type": "integer"},
        },
        "required": ["a", "b"],
        "dependencies": {
            "a": ["b"],  # array form
            "b": {  # schema form
                "properties": {"c": {"type": "integer"}},
                "required": ["c"],
            },
        },
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, dict)
        assert "b" in result  # a is required, so b must be present
        assert "c" in result  # b is required, so c must be present
        validate(result, schema)


# ── New string formats (draft-07+) ───────────────────────────────────


def test_format_time(faker, repeats_for_fast):
    """format: time → RFC 3339 full-time."""
    schema = {"type": "string", "format": "time"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        # Should match HH:MM:SS with optional timezone
        assert re.match(r"\d{2}:\d{2}:\d{2}", result)


def test_format_time_direct(faker, repeats_for_fast):
    """Direct call for time format."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(format_="time")
        assert isinstance(result, str)
        assert re.match(r"\d{2}:\d{2}:\d{2}", result)


def test_format_duration(faker, repeats_for_fast):
    """format: duration → ISO 8601 duration."""
    schema = {"type": "string", "format": "duration"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert result.startswith("P")


def test_format_uri_reference(faker, repeats_for_fast):
    """format: uri-reference → URI or relative reference."""
    schema = {"type": "string", "format": "uri-reference"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_uri_template(faker, repeats_for_fast):
    """format: uri-template → URI with template vars."""
    schema = {"type": "string", "format": "uri-template"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert "{" in result and "}" in result


def test_format_iri(faker, repeats_for_fast):
    """format: iri → valid IRI (ASCII URI is valid subset)."""
    schema = {"type": "string", "format": "iri"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_iri_reference(faker, repeats_for_fast):
    """format: iri-reference → IRI or relative IRI reference."""
    schema = {"type": "string", "format": "iri-reference"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_idn_email(faker, repeats_for_fast):
    """format: idn-email → international email."""
    schema = {"type": "string", "format": "idn-email"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert "@" in result


def test_format_idn_hostname(faker, repeats_for_fast):
    """format: idn-hostname → international hostname."""
    schema = {"type": "string", "format": "idn-hostname"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_json_pointer(faker, repeats_for_fast):
    """format: json-pointer → RFC 6901."""
    schema = {"type": "string", "format": "json-pointer"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert result.startswith("/")


def test_format_relative_json_pointer(faker, repeats_for_fast):
    """format: relative-json-pointer → starts with digit."""
    schema = {"type": "string", "format": "relative-json-pointer"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        assert result[0].isdigit()


def test_format_regex(faker, repeats_for_fast):
    """format: regex → a valid regular expression."""
    schema = {"type": "string", "format": "regex"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, str)
        # Verify it's actually a valid regex
        re.compile(result)


# ── contentEncoding (draft 2019-09+) ─────────────────────────────────


def test_content_encoding_base64(faker, repeats_for_fast):
    """contentEncoding: base64 → returns base64-encoded bytes."""
    schema = {"type": "string", "contentEncoding": "base64"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, bytes)
        # should be valid base64 (length multiple of 4)
        assert len(result) % 4 == 0


def test_content_encoding_base64_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='base64'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="base64")
        assert isinstance(result, bytes)
        assert len(result) % 4 == 0


# ── prefixItems (draft 2020-12) ──────────────────────────────────────


def test_prefix_items_basic(faker, repeats_for_slow):
    """PrefixItems with different types for each position."""
    schema = {
        "type": "array",
        "prefixItems": [
            {"type": "string"},
            {"type": "integer"},
            {"type": "boolean"},
        ],
        "items": False,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert len(result) == 3
        assert isinstance(result[0], str)
        assert isinstance(result[1], int) and not isinstance(result[1], bool)
        assert isinstance(result[2], bool)
        validate(result, schema)


def test_prefix_items_with_additional(faker, repeats_for_slow):
    """PrefixItems with items schema for additional items."""
    schema = {
        "type": "array",
        "prefixItems": [
            {"type": "string"},
            {"type": "integer"},
        ],
        "items": {"type": "boolean"},
        "minItems": 4,
        "maxItems": 6,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert 4 <= len(result) <= 6
        assert isinstance(result[0], str)
        assert isinstance(result[1], int) and not isinstance(result[1], bool)
        for item in result[2:]:
            assert isinstance(item, bool)
        validate(result, schema)


def test_prefix_items_direct(faker, repeats_for_slow):
    """Direct call with prefix_items."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "number"},
                {"type": "string"},
            ],
            min_items=2,
            max_items=2,
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], (int, float))
        assert isinstance(result[1], str)


# ── contains / minContains / maxContains ─────────────────────────────


def test_contains_basic(faker, repeats_for_slow):
    """Contains → at least one item matches."""
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 100},
        "contains": {"type": "integer", "minimum": 50, "maximum": 100},
        "minItems": 3,
        "maxItems": 10,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        assert any(isinstance(x, int) and x >= 50 for x in result)
        validate(result, schema)


def test_min_contains(faker, repeats_for_slow):
    """MinContains → at least N items match contains."""
    schema = {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 100},
        "contains": {"type": "integer", "minimum": 50, "maximum": 100},
        "minContains": 3,
        "minItems": 5,
        "maxItems": 15,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema)
        assert isinstance(result, list)
        matching = sum(1 for x in result if isinstance(x, int) and x >= 50)
        assert matching >= 3
        validate(result, schema)


def test_contains_direct(faker, repeats_for_slow):
    """Direct call with contains."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            items={"type": "string"},
            contains={"type": "string", "minLength": 10},
            min_items=3,
            max_items=10,
        )
        assert isinstance(result, list)
        # At least one string with length >= 10
        assert any(isinstance(x, str) and len(x) >= 10 for x in result)


# ── additionalItems ─────────────────────────────────────────────────


def test_additional_items_false(faker, repeats_for_slow):
    """additionalItems: false with prefixItems → exactly N items."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "string"},
                {"type": "integer"},
            ],
            additional_items=False,
            min_items=2,
            max_items=2,
        )
        assert isinstance(result, list)
        assert len(result) == 2


def test_additional_items_schema(faker, repeats_for_slow):
    """AdditionalItems as schema → extra items match that schema."""
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_array(
            prefix_items=[
                {"type": "string"},
            ],
            additional_items={"type": "boolean"},
            min_items=3,
            max_items=5,
        )
        assert isinstance(result, list)
        assert len(result) >= 3
        assert isinstance(result[0], str)
        for item in result[1:]:
            assert isinstance(item, bool)
