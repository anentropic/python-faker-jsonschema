import itertools
import re

import pytest
from jsonschema import validate

from faker_jsonschema.provider import (
    JSONSchemaProvider,
    LengthType,
    NoExampleFoundError,
    StringFormat,
    UnsatisfiableConstraintsError,
)


@pytest.mark.parametrize(
    "min_length,max_length",
    itertools.product(
        (3, 5, 11),
        (None, 15, 20, 25),
    ),
)
def test_jsonschema_string_length(faker, repeats_for_slow, min_length, max_length):
    for _ in range(repeats_for_slow):
        result = faker.jsonschema_string(
            min_length=min_length,
            max_length=max_length,
        )
        assert isinstance(result, str)
        assert len(result) >= min_length
        if max_length is not None:
            assert len(result) <= max_length


@pytest.mark.parametrize(
    "pattern_spec,min_length,max_length",
    itertools.product(
        (
            (r"^[a-zA-Z0-9\.\-_]+$", None),
            (r"[\w\.-]+@[\w\.-]+", None),
            (r"^(\([0-9]{3}\))?[0-9]{3}-[0-9]{4}$", [8, 13]),
            (r"^\w{3}\d{2,4}$", [5, 6, 7]),
        ),
        (5, 11, 13),
        (None, 7, 12, 15),
    ),
)
def test_jsonschema_pattern(
    faker,
    pattern_spec: tuple[str, list[int] | None],
    min_length: int,
    max_length: int | None,
):
    pattern, possible_lengths = pattern_spec

    if max_length is not None and min_length > max_length:
        with pytest.raises(ValueError):
            faker.jsonschema_string(
                pattern=pattern,
                min_length=min_length,
                max_length=max_length,
            )
        return

    def valid_constraints():
        return any(
            len_ >= min_length and (max_length is None or len_ <= max_length)
            for len_ in possible_lengths
        )

    if possible_lengths is not None and not valid_constraints():
        # length constraints could never be satisfied by the pattern
        with pytest.raises((NoExampleFoundError, UnsatisfiableConstraintsError)):
            faker.jsonschema_string(
                pattern=pattern,
                min_length=min_length,
                max_length=max_length,
            )
        return

    # finding suitable examples (with underlying `hypothesis.example`)
    # is not deterministic — track failure rate instead of silently ignoring
    failures = 0
    attempts = 5
    for _ in range(attempts):
        try:
            result = faker.jsonschema_string(
                pattern=pattern,
                min_length=min_length,
                max_length=max_length,
            )
        except (NoExampleFoundError, UnsatisfiableConstraintsError):
            failures += 1
        else:
            assert isinstance(result, str)
            assert re.search(pattern, result)
            assert len(result) >= min_length
            if max_length is not None:
                assert len(result) <= max_length
    assert failures < attempts, (
        f"Pattern {pattern!r} with minLength={min_length}, "
        f"maxLength={max_length} failed all {attempts} attempts"
    )


@pytest.mark.parametrize(
    "format_",
    itertools.chain(
        JSONSchemaProvider.STRING_FORMATS.keys(),
        # other values which match faker providers which return str:
        (
            "currency_code",
            "color",
        ),
        # other values which match faker providers which can be cast to str:
        (
            "date_of_birth",
            "unix_time",
        ),
    ),
)
def test_jsonschema_format(faker, format_):
    format_type = JSONSchemaProvider.STRING_FORMATS.get(format_)
    result = faker.jsonschema_string(
        format_=format_,
    )
    assert isinstance(result, format_type.return_type if format_type else str)


@pytest.mark.parametrize(
    "min_length,max_length",
    itertools.product(
        (5, 11, 13),
        (None, 7, 12, 15),
    ),
)
def test_jsonschema_format_min_max_length_fixed(faker, min_length, max_length):
    format_ = "date"
    format_type = JSONSchemaProvider.STRING_FORMATS[format_]
    assert format_type.length_type == LengthType.FIXED
    assert format_type.lengths == [10]

    if max_length is not None and min_length > max_length:
        with pytest.raises(ValueError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    if min_length > 10 or (max_length is not None and max_length < 10):
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    result = faker.jsonschema_string(
        format_=format_,
        min_length=min_length,
        max_length=max_length,
    )
    assert isinstance(result, format_type.return_type if format_type else str)
    assert min_length <= len(result)
    if max_length is not None:
        assert len(result) <= max_length


@pytest.mark.parametrize(
    "min_length,max_length",
    itertools.product(
        (5, 11, 13),
        (None, 7, 12, 15),
    ),
)
def test_jsonschema_format_min_max_length_variable_singular(
    faker, min_length, max_length
):
    format_ = "password"
    format_type = JSONSchemaProvider.STRING_FORMATS[format_]
    assert format_type.length_type == LengthType.VARIABLE_SINGULAR
    assert format_type.lengths is None

    if max_length is not None and min_length > max_length:
        with pytest.raises(ValueError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    result = faker.jsonschema_string(
        format_=format_,
        min_length=min_length,
        max_length=max_length,
    )
    assert isinstance(result, format_type.return_type)
    assert min_length <= len(result)
    if max_length is not None:
        assert len(result) <= max_length


@pytest.mark.parametrize(
    "length_type,lengths,min_length,max_length,expected",
    (
        (LengthType.FIXED, [10], 0, None, True),
        (LengthType.FIXED, [10], 9, None, True),
        (LengthType.FIXED, [10], 10, None, True),
        (LengthType.FIXED, [10], 11, None, False),
        (LengthType.FIXED, [10], 0, 9, False),
        (LengthType.FIXED, [10], 0, 10, True),
        (LengthType.FIXED, [10], 0, 11, True),
        (LengthType.FIXED, [10, 13], 0, None, True),
        (LengthType.FIXED, [10, 13], 9, None, True),
        (LengthType.FIXED, [10, 13], 10, None, True),
        (LengthType.FIXED, [10, 13], 13, None, False),
        (LengthType.FIXED, [10, 13], 14, None, False),
        (LengthType.FIXED, [10, 13], 0, 9, False),
        (LengthType.FIXED, [10, 13], 0, 10, False),
        (LengthType.FIXED, [10, 13], 0, 14, True),
        (LengthType.FIXED, [10, 13], 9, 11, False),
        (LengthType.FIXED, [10, 13], 11, 12, False),
        (LengthType.FIXED, [10, 13], 13, 13, False),
        (LengthType.FIXED, range(10, 14), 0, None, True),
        (LengthType.FIXED, range(10, 14), 9, None, True),
        (LengthType.FIXED, range(10, 14), 10, None, True),
        (LengthType.FIXED, range(10, 14), 13, None, False),
        (LengthType.FIXED, range(10, 14), 14, None, False),
        (LengthType.FIXED, range(10, 14), 0, 9, False),
        (LengthType.FIXED, range(10, 14), 0, 10, False),
        (LengthType.FIXED, range(10, 14), 0, 14, True),
        (LengthType.FIXED, range(10, 14), 9, 11, False),
        (LengthType.FIXED, range(10, 14), 11, 12, False),
        (LengthType.FIXED, range(10, 14), 13, 13, False),
        (LengthType.FIXED, range(8, 18, 4), 0, None, True),
        (LengthType.FIXED, range(8, 18, 4), 8, None, True),
        (LengthType.FIXED, range(8, 18, 4), 9, None, False),
        (LengthType.FIXED, range(8, 18, 4), 18, None, False),
        (LengthType.FIXED, range(8, 18, 4), 0, 9, False),
        (LengthType.FIXED, range(8, 18, 4), 0, 15, False),
        (LengthType.FIXED, range(8, 18, 4), 0, 16, True),
        (LengthType.FIXED, range(8, 18, 4), 8, 15, False),
        (LengthType.FIXED, range(8, 18, 4), 8, 16, True),
        (LengthType.FIXED, range(8, 18, 4), 9, 16, False),
        (LengthType.FIXED, range(9, 18, 4), 0, None, True),
        (LengthType.FIXED, range(9, 18, 4), 9, None, True),
        (LengthType.FIXED, range(9, 18, 4), 10, None, False),
        (LengthType.FIXED, range(9, 18, 4), 18, None, False),
        (LengthType.FIXED, range(9, 18, 4), 0, 10, False),
        (LengthType.FIXED, range(9, 18, 4), 0, 16, False),
        (LengthType.FIXED, range(9, 18, 4), 0, 17, True),
        (LengthType.FIXED, range(9, 18, 4), 9, 16, False),
        (LengthType.FIXED, range(9, 18, 4), 9, 17, True),
        (LengthType.FIXED, range(9, 18, 4), 10, 17, False),
        (LengthType.VARIABLE_SINGULAR, None, 0, 0, True),
        (LengthType.VARIABLE_RANGE, None, 0, 0, True),
        (LengthType.UNCONSTRAINED, None, 0, 0, False),
        (LengthType.VARIABLE_SINGULAR, None, 0, 1, True),
        (LengthType.VARIABLE_RANGE, None, 0, 1, True),
        (LengthType.UNCONSTRAINED, None, 0, 1, True),
    ),
)
def test_stringformat_validate_constraints(
    length_type, lengths, min_length, max_length, expected
):
    format_type = StringFormat(length_type=length_type, lengths=lengths)
    result = format_type.validate_constraints(min_length, max_length)
    assert result == expected


@pytest.mark.parametrize(
    "min_length,max_length",
    itertools.product(
        (5, 11, 13),
        (None, 7, 12, 15),
    ),
)
def test_jsonschema_format_min_max_length_variable_range(faker, min_length, max_length):
    format_ = "byte"
    format_type = JSONSchemaProvider.STRING_FORMATS[format_]
    assert format_type.length_type == LengthType.VARIABLE_RANGE

    if max_length is not None and min_length > max_length:
        with pytest.raises(ValueError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    if not format_type.validate_constraints(min_length, max_length):
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    result = faker.jsonschema_string(
        format_=format_,
        min_length=min_length,
        max_length=max_length,
    )
    assert isinstance(result, format_type.return_type)
    assert min_length <= len(result)
    if max_length is not None:
        assert len(result) <= max_length


@pytest.mark.parametrize(
    "min_length,max_length,expect_result",
    (
        (0, 0, False),
        (0, None, True),
        (0, 20, True),
        (20, 30, True),
        (0, 5, False),  # too short
        (70, 100, False),  # too long
    ),
)
def test_jsonschema_format_min_max_length_unconstrained(
    faker, min_length, max_length, expect_result
):
    format_ = "hostname"
    format_type = JSONSchemaProvider.STRING_FORMATS[format_]
    assert format_type.length_type == LengthType.UNCONSTRAINED

    if not expect_result:
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    if not format_type.validate_constraints(min_length, max_length):
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_string(
                format_=format_,
                min_length=min_length,
                max_length=max_length,
            )
        return

    result = faker.jsonschema_string(
        format_=format_,
        min_length=min_length,
        max_length=max_length,
    )
    assert isinstance(result, format_type.return_type)
    assert min_length <= len(result)
    if max_length is not None:
        assert len(result) <= max_length


# ── from_schema round-trip tests ─────────────────────────────────────


@pytest.mark.parametrize(
    "min_length,max_length",
    [
        (0, None),
        (5, 20),
        (10, 10),
        (0, 5),
    ],
)
def test_from_schema_string_round_trip(faker, repeats_for_slow, min_length, max_length):
    """from_schema round trip for string with length constraints."""
    schema = {"type": "string", "minLength": min_length}
    if max_length is not None:
        schema["maxLength"] = max_length
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


def test_from_schema_string_format_date(faker, repeats_for_slow):
    """from_schema round trip with format: date."""
    schema = {"type": "string", "format": "date"}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


def test_from_schema_string_format_email(faker, repeats_for_slow):
    """from_schema round trip with format: email."""
    schema = {"type": "string", "format": "email"}
    for _ in range(repeats_for_slow):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)


# ── _format_byte edge case ───────────────────────────────────────────


def test_format_byte_no_valid_length(faker):
    """_format_byte with no valid base64 length in range raises."""
    with pytest.raises(
        UnsatisfiableConstraintsError, match="incompatible with format: byte"
    ):
        faker.jsonschema_string(format_="byte", min_length=5, max_length=7)


# ── Format-specific tests ────────────────────────────────────────────


def test_format_time(faker, repeats_for_fast):
    """format: time → RFC 3339 full-time."""
    schema = {"type": "string", "format": "time"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
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
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert result.startswith("P")


def test_format_uri_reference(faker, repeats_for_fast):
    """format: uri-reference → URI or relative reference."""
    schema = {"type": "string", "format": "uri-reference"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_uri_template(faker, repeats_for_fast):
    """format: uri-template → URI with template vars."""
    schema = {"type": "string", "format": "uri-template"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert "{" in result and "}" in result


def test_format_iri(faker, repeats_for_fast):
    """format: iri → valid IRI (ASCII URI is valid subset)."""
    schema = {"type": "string", "format": "iri"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_iri_reference(faker, repeats_for_fast):
    """format: iri-reference → IRI or relative IRI reference."""
    schema = {"type": "string", "format": "iri-reference"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_idn_email(faker, repeats_for_fast):
    """format: idn-email → international email."""
    schema = {"type": "string", "format": "idn-email"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert "@" in result


def test_format_idn_hostname(faker, repeats_for_fast):
    """format: idn-hostname → international hostname."""
    schema = {"type": "string", "format": "idn-hostname"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) > 0


def test_format_json_pointer(faker, repeats_for_fast):
    """format: json-pointer → RFC 6901."""
    schema = {"type": "string", "format": "json-pointer"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert result.startswith("/")


def test_format_relative_json_pointer(faker, repeats_for_fast):
    """format: relative-json-pointer → starts with digit."""
    schema = {"type": "string", "format": "relative-json-pointer"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert result[0].isdigit()


def test_format_regex(faker, repeats_for_fast):
    """format: regex → a valid regular expression."""
    schema = {"type": "string", "format": "regex"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        # Verify it's actually a valid regex
        re.compile(result)


# ── contentEncoding ──────────────────────────────────────────────────


def test_content_encoding_base64(faker, repeats_for_fast):
    """contentEncoding: base64 → returns base64-encoded bytes."""
    schema = {"type": "string", "contentEncoding": "base64"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, bytes)
        # should be valid base64 (length multiple of 4)
        assert len(result) % 4 == 0


def test_content_encoding_base64_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='base64'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="base64")
        assert isinstance(result, bytes)
        assert len(result) % 4 == 0
