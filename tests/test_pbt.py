"""
Property-based tests using Hypothesis.

Round-trip strategy: generate a JSON Schema → produce data via from_schema →
validate the produced data against the schema using jsonschema.validate.

We build schemas using Hypothesis strategies so we get diverse inputs without
needing an external oracle.
"""

import os
import random

from faker import Faker
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from jsonschema import validate

from faker_jsonschema.provider import (
    JSONSchemaProvider,
    LengthType,
    UnsatisfiableConstraintsError,
)

# ── Faker instance for PBT ───────────────────────────────────────────

_seed = int(os.getenv("SEED", random.randint(0, 9999999)))
_faker = Faker()
Faker.seed(_seed)
_faker.add_provider(JSONSchemaProvider)


# ── Schema strategies ────────────────────────────────────────────────


def _string_schemas():
    """Strategy yielding string-type JSON Schemas."""
    return st.fixed_dictionaries(
        {"type": st.just("string")},
        optional={
            "minLength": st.integers(min_value=0, max_value=50),
            "maxLength": st.integers(min_value=0, max_value=200),
        },
    ).filter(lambda s: s.get("maxLength", 999) >= s.get("minLength", 0))


def _integer_schemas():
    """Strategy yielding integer-type JSON Schemas."""
    return st.fixed_dictionaries(
        {"type": st.just("integer")},
        optional={
            "minimum": st.integers(min_value=-1000, max_value=1000),
            "maximum": st.integers(min_value=-1000, max_value=1000),
        },
    ).filter(lambda s: s.get("maximum", 9999) >= s.get("minimum", -9999))


def _number_schemas():
    """Strategy yielding number-type JSON Schemas."""
    return st.fixed_dictionaries(
        {"type": st.just("number")},
        optional={
            "minimum": st.floats(min_value=-1000, max_value=1000, allow_nan=False),
            "maximum": st.floats(min_value=-1000, max_value=1000, allow_nan=False),
        },
    ).filter(lambda s: s.get("maximum", 9999) >= s.get("minimum", -9999))


def _boolean_schemas():
    """Strategy yielding boolean-type JSON Schemas."""
    return st.just({"type": "boolean"})


def _null_schemas():
    """Strategy yielding null-type JSON Schemas."""
    return st.just({"type": "null"})


def _flat_schemas():
    """Strategy yielding any flat-type JSON Schema."""
    return st.one_of(
        _string_schemas(),
        _integer_schemas(),
        _number_schemas(),
        _boolean_schemas(),
        _null_schemas(),
    )


def _array_schemas():
    """Strategy yielding array-type JSON Schemas with flat items."""
    return st.fixed_dictionaries(
        {
            "type": st.just("array"),
            "items": _flat_schemas(),
        },
        optional={
            "minItems": st.integers(min_value=0, max_value=5),
            "maxItems": st.integers(min_value=0, max_value=10),
        },
    ).filter(lambda s: s.get("maxItems", 999) >= s.get("minItems", 0))


def _simple_property_schemas():
    """Strategy yielding a dict of 1-3 flat properties for object schemas."""
    return st.dictionaries(
        keys=st.from_regex(r"[a-z]{2,8}", fullmatch=True),
        values=_flat_schemas(),
        min_size=1,
        max_size=3,
    )


def _object_schemas():
    """Strategy yielding object-type JSON Schemas with flat property values."""
    return _simple_property_schemas().flatmap(
        lambda props: st.fixed_dictionaries(
            {
                "type": st.just("object"),
                "properties": st.just(props),
                "required": st.just(list(props.keys())),
                "additionalProperties": st.just(False),
            }
        )
    )


def _any_schema():
    """Strategy yielding any valid single-type JSON Schema."""
    return st.one_of(
        _flat_schemas(),
        _array_schemas(),
        _object_schemas(),
    )


# ── Property-based tests ────────────────────────────────────────────


@given(schema=_string_schemas())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_string_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


@given(schema=_integer_schemas())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_integer_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


@given(schema=_number_schemas())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_number_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


@given(schema=_boolean_schemas())
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_boolean_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


@given(schema=_array_schemas())
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_array_round_trip(schema):
    result = _faker.from_jsonschema(schema, default_collection_max=10)
    validate(result, schema)


@given(schema=_object_schemas())
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_object_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


@given(schema=_any_schema())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_any_schema_round_trip(schema):
    """Generate any schema type → from_schema → validate."""
    try:
        result = _faker.from_jsonschema(schema, default_collection_max=10)
    except UnsatisfiableConstraintsError:
        # Some generated schemas may be unsatisfiable — that's fine
        return
    validate(result, schema)


# ── Compound schema PBT ──────────────────────────────────────────────


@given(
    schema1=_integer_schemas(),
    schema2=_integer_schemas(),
)
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_allof_integer(schema1, schema2):
    """AllOf with two integer schemas → result valid against both."""
    merged_min = max(schema1.get("minimum", -9999), schema2.get("minimum", -9999))
    merged_max = min(schema1.get("maximum", 9999), schema2.get("maximum", 9999))
    if merged_max < merged_min:
        return  # unsatisfiable by construction

    allof_schema = {"allOf": [schema1, schema2]}
    try:
        result = _faker.from_jsonschema(allof_schema)
    except UnsatisfiableConstraintsError:
        return
    validate(result, schema1)
    validate(result, schema2)


# ── New feature PBT tests ────────────────────────────────────────────


@given(schema=_null_schemas())
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_null_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    assert result is None
    validate(result, schema)


def _type_array_schemas():
    """Strategy yielding schemas with type as array."""
    type_list = st.lists(
        st.sampled_from(["string", "integer", "number", "boolean", "null"]),
        min_size=1,
        max_size=3,
        unique=True,
    )
    return type_list.map(lambda types: {"type": types})


@given(schema=_type_array_schemas())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_type_array_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


def _const_schemas():
    """Strategy yielding const schemas."""
    return st.one_of(
        st.integers(min_value=-1000, max_value=1000).map(lambda v: {"const": v}),
        st.text(min_size=0, max_size=20).map(lambda v: {"const": v}),
        st.just({"const": None}),
        st.just({"const": True}),
        st.just({"const": False}),
    )


@given(schema=_const_schemas())
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_const_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    assert result == schema["const"]
    validate(result, schema)


def _exclusive_integer_schemas():
    """Strategy yielding integer schemas with draft-06+ exclusiveMinimum/Maximum."""
    return st.fixed_dictionaries(
        {"type": st.just("integer")},
        optional={
            "exclusiveMinimum": st.integers(min_value=-100, max_value=100),
            "exclusiveMaximum": st.integers(min_value=-100, max_value=100),
        },
    ).filter(lambda s: s.get("exclusiveMaximum", 9999) > s.get("exclusiveMinimum", -9999) + 1)


@given(schema=_exclusive_integer_schemas())
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_exclusive_integer_round_trip(schema):
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


def _prefix_items_schemas():
    """Strategy yielding array schemas with prefixItems."""
    prefix = st.lists(_flat_schemas(), min_size=1, max_size=3)
    return prefix.map(
        lambda items: {
            "type": "array",
            "prefixItems": items,
            "items": False,
        }
    )


@given(schema=_prefix_items_schemas())
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_prefix_items_round_trip(schema):
    try:
        result = _faker.from_jsonschema(schema, default_collection_max=10)
    except UnsatisfiableConstraintsError:
        return
    validate(result, schema)


def _ref_schemas():
    """Strategy yielding schemas with $ref/$defs."""
    return _flat_schemas().map(
        lambda inner: {
            "$defs": {"target": inner},
            "type": "object",
            "properties": {"val": {"$ref": "#/$defs/target"}},
            "required": ["val"],
            "additionalProperties": False,
        }
    )


@given(schema=_ref_schemas())
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_ref_round_trip(schema):
    try:
        result = _faker.from_jsonschema(schema)
    except UnsatisfiableConstraintsError:
        return
    validate(result, schema)


# -- Format + length PBT ---------------------------------------------------

# Build a list of (format_name, min_valid, max_valid) for VARIABLE_RANGE formats
_FORMAT_RANGES = []
for _name, _fmt in JSONSchemaProvider.STRING_FORMATS.items():
    if (
        _fmt.length_type is LengthType.VARIABLE_RANGE
        and isinstance(_fmt.lengths, range)
        and _fmt.return_type is str  # exclude bytes-returning formats
    ):
        _FORMAT_RANGES.append((_name, _fmt.lengths.start, _fmt.lengths.stop - 1))


def _string_format_schemas():
    """
    Strategy yielding string schemas with format + compatible length.

    Uses a 'safe' lower bound so we don't ask for lengths that are technically
    in range but practically unreachable (e.g. 3-char email).
    """
    # safe_min avoids unreachably small values for variable-length formats
    safe_min = 10

    return st.sampled_from(_FORMAT_RANGES).flatmap(
        lambda fmt: st.fixed_dictionaries(
            {
                "type": st.just("string"),
                "format": st.just(fmt[0]),
            },
            optional={
                "minLength": st.integers(
                    min_value=max(fmt[1], safe_min),
                    max_value=min(fmt[2], 200),
                ),
                "maxLength": st.integers(
                    min_value=max(fmt[1], safe_min),
                    max_value=min(fmt[2], 200),
                ),
            },
        ).filter(lambda s: s.get("maxLength", 99999) >= s.get("minLength", 0))
    )


@given(schema=_string_format_schemas())
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_string_format_length_round_trip(schema):
    """Format + length constraints: result validates and respects length."""
    try:
        result = _faker.from_jsonschema(schema)
    except UnsatisfiableConstraintsError:
        return
    validate(result, schema)
    if "minLength" in schema:
        assert len(result) >= schema["minLength"]
    if "maxLength" in schema:
        assert len(result) <= schema["maxLength"]


# -- NOT schema PBT --------------------------------------------------------


def _not_schemas():
    """Strategy yielding NOT schemas with typed inner schemas."""
    inner = st.one_of(
        st.fixed_dictionaries(
            {"type": st.just("string")},
            optional={"minLength": st.integers(0, 20), "maxLength": st.integers(0, 50)},
        ).filter(lambda s: s.get("maxLength", 999) >= s.get("minLength", 0)),
        st.fixed_dictionaries(
            {"type": st.just("integer")},
            optional={
                "minimum": st.integers(-100, 100),
                "maximum": st.integers(-100, 100),
            },
        ).filter(lambda s: s.get("maximum", 999) >= s.get("minimum", -999)),
        st.just({"type": "boolean"}),
        st.just({"type": "null"}),
        st.fixed_dictionaries(
            {"type": st.just("number")},
            optional={
                "minimum": st.integers(-100, 100),
                "maximum": st.integers(-100, 100),
            },
        ).filter(lambda s: s.get("maximum", 999) >= s.get("minimum", -999)),
    )
    return inner.map(lambda s: {"not": s})


@given(schema=_not_schemas())
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_not_round_trip(schema):
    """NOT schemas should always succeed (no NoExampleFoundError)."""
    result = _faker.from_jsonschema(schema)
    validate(result, schema)


# -- Pattern + length PBT --------------------------------------------------


def _pattern_length_schemas():
    """Strategy yielding string schemas with unanchored patterns + length."""
    patterns = st.sampled_from([r"\d+", r"[a-z]+", r"\w+", r"[A-Za-z0-9]+"])
    return st.fixed_dictionaries(
        {
            "type": st.just("string"),
            "pattern": patterns,
            "minLength": st.integers(min_value=1, max_value=80),
        },
        optional={
            "maxLength": st.integers(min_value=1, max_value=200),
        },
    ).filter(lambda s: s.get("maxLength", 999) >= s["minLength"])


@given(schema=_pattern_length_schemas())
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_pbt_pattern_length_round_trip(schema):
    """Unanchored pattern + length: result validates and respects length."""
    import re

    try:
        result = _faker.from_jsonschema(schema)
    except UnsatisfiableConstraintsError:
        return
    validate(result, schema)
    assert len(result) >= schema["minLength"]
    if "maxLength" in schema:
        assert len(result) <= schema["maxLength"]
    assert re.search(schema["pattern"], result)
