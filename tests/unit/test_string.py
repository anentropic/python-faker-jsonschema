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
        (0, 1, 3, 5, 11, 13),
        (None, 3, 7, 12, 15),
    ),
)
def test_jsonschema_format_min_max_length_variable_singular(faker, min_length, max_length):
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
def test_stringformat_validate_constraints(length_type, lengths, min_length, max_length, expected):
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
        (0, 0, False),  # hostname min valid length is 1
        (0, None, True),
        (0, 20, True),
        (20, 30, True),
        (0, 5, True),
        (70, 100, True),
    ),
)
def test_jsonschema_format_min_max_length_hostname(faker, min_length, max_length, expect_result):
    format_ = "hostname"
    format_type = JSONSchemaProvider.STRING_FORMATS[format_]
    assert format_type.length_type == LengthType.VARIABLE_RANGE

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
    with pytest.raises(UnsatisfiableConstraintsError, match="incompatible with format: byte"):
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


def test_from_schema_string_format_byte_round_trip(faker, repeats_for_fast):
    """format: byte must still produce a JSON string instance."""
    schema = {"type": "string", "format": "byte"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


def test_from_schema_string_format_binary_round_trip(faker, repeats_for_fast):
    """format: binary must still produce a JSON string instance."""
    schema = {"type": "string", "format": "binary"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


# ── contentEncoding ──────────────────────────────────────────────────


def test_content_encoding_base64(faker, repeats_for_fast):
    """contentEncoding: base64 → returns a base64-encoded string."""
    schema = {"type": "string", "contentEncoding": "base64"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        # should be valid base64 (length multiple of 4)
        assert len(result) % 4 == 0


def test_content_encoding_base64_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='base64'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="base64")
        assert isinstance(result, str)
        assert len(result) % 4 == 0


def test_content_encoding_base32(faker, repeats_for_fast):
    """contentEncoding: base32 → returns a base32-encoded string."""
    import base64

    schema = {"type": "string", "contentEncoding": "base32"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) % 8 == 0
        base64.b32decode(result)  # must not raise


def test_content_encoding_base32_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='base32'."""
    import base64

    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="base32")
        assert isinstance(result, str)
        assert len(result) % 8 == 0
        base64.b32decode(result)


def test_content_encoding_base16(faker, repeats_for_fast):
    """contentEncoding: base16 → returns a base16 (hex) encoded string."""
    import base64

    schema = {"type": "string", "contentEncoding": "base16"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert len(result) % 2 == 0
        base64.b16decode(result)  # must not raise


def test_content_encoding_base16_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='base16'."""
    import base64

    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="base16")
        assert isinstance(result, str)
        assert len(result) % 2 == 0
        base64.b16decode(result)


def test_content_encoding_7bit(faker, repeats_for_fast):
    """contentEncoding: 7bit → returns a string in printable ASCII range."""
    schema = {"type": "string", "contentEncoding": "7bit"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert all(0x20 <= ord(char) <= 0x7E for char in result)


def test_content_encoding_7bit_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='7bit'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="7bit")
        assert isinstance(result, str)
        assert all(0x20 <= ord(char) <= 0x7E for char in result)


def test_content_encoding_8bit(faker, repeats_for_fast):
    """contentEncoding: 8bit → returns a string with no NUL characters."""
    schema = {"type": "string", "contentEncoding": "8bit"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        assert all(ord(char) != 0x00 for char in result)  # no NUL


def test_content_encoding_8bit_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='8bit'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="8bit")
        assert isinstance(result, str)
        assert all(ord(char) != 0x00 for char in result)


def test_content_encoding_binary(faker, repeats_for_fast):
    """contentEncoding: binary → returns a string representation of binary data."""
    schema = {"type": "string", "contentEncoding": "binary"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)


def test_content_encoding_binary_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='binary'."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="binary")
        assert isinstance(result, str)


def test_content_encoding_quoted_printable(faker, repeats_for_fast):
    """contentEncoding: quoted-printable → returns a valid QP string."""
    import quopri

    schema = {"type": "string", "contentEncoding": "quoted-printable"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        quopri.decodestring(result)  # must not raise


def test_content_encoding_quoted_printable_direct(faker, repeats_for_fast):
    """Direct call with content_encoding='quoted-printable'."""
    import quopri

    for _ in range(repeats_for_fast):
        result = faker.jsonschema_string(content_encoding="quoted-printable")
        assert isinstance(result, str)
        quopri.decodestring(result)


def test_content_encoding_unknown_falls_through(faker):
    """Unknown contentEncoding value falls through to plain string generation."""
    schema = {"type": "string", "contentEncoding": "x-custom"}
    result = faker.from_jsonschema(schema)
    assert isinstance(result, str)


def test_content_encoding_case_insensitive(faker):
    """ContentEncoding matching is case-insensitive."""
    for encoding in ("BASE64", "Base64", "BASE32", "Base16", "BINARY"):
        result = faker.from_jsonschema({"type": "string", "contentEncoding": encoding})
        assert isinstance(result, str)


def test_from_schema_content_encoding_base64_round_trip(faker, repeats_for_fast):
    """ContentEncoding metadata must not change the JSON string instance type."""
    schema = {"type": "string", "contentEncoding": "base64"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


def test_from_schema_content_encoding_binary_round_trip(faker, repeats_for_fast):
    """contentEncoding: binary must still produce a JSON string instance."""
    schema = {"type": "string", "contentEncoding": "binary"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, str)
        validate(result, schema)


# -- Length-aware format tests -----------------------------------------------


class TestLengthAwareFormats:
    """Verify format methods respect minLength/maxLength constraints."""

    def test_email_with_length_range(self, faker, repeats_for_fast):
        """format: email with minLength/maxLength should always succeed."""
        schema = {"type": "string", "format": "email", "minLength": 15, "maxLength": 60}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 15 <= len(result) <= 60
            assert "@" in result

    def test_idn_email_exact_high_length(self, faker, repeats_for_fast):
        """format: idn-email with exact high minLength=maxLength must produce valid result."""
        schema = {"type": "string", "format": "idn-email", "minLength": 97, "maxLength": 97}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            validate(result, schema)
            assert len(result) == 97

    def test_email_exceeds_rfc_max(self, faker):
        """format: email with minLength beyond RFC 5321 max raises."""
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.from_jsonschema({"type": "string", "format": "email", "minLength": 300})

    def test_hostname_with_min_length(self, faker, repeats_for_fast):
        """format: hostname with minLength should produce longer hostnames."""
        schema = {"type": "string", "format": "hostname", "minLength": 30}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert len(result) >= 30
            assert "." in result

    def test_uri_with_long_min_length(self, faker, repeats_for_fast):
        """format: uri with large minLength should pad the path."""
        schema = {"type": "string", "format": "uri", "minLength": 50, "maxLength": 100}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 50 <= len(result) <= 100
            assert result.startswith("http")

    def test_json_pointer_with_length(self, faker, repeats_for_fast):
        """format: json-pointer with length constraints."""
        schema = {
            "type": "string",
            "format": "json-pointer",
            "minLength": 10,
            "maxLength": 30,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 10 <= len(result) <= 30
            assert result.startswith("/")

    def test_duration_with_length(self, faker, repeats_for_fast):
        """format: duration with length constraints."""
        schema = {
            "type": "string",
            "format": "duration",
            "minLength": 3,
            "maxLength": 10,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 3 <= len(result) <= 10
            assert result.startswith("P")

    def test_duration_with_high_min_length(self, faker, repeats_for_fast):
        """format: duration with minLength near realistic max (18-25 chars)."""
        schema = {
            "type": "string",
            "format": "duration",
            "minLength": 18,
            "maxLength": 25,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 18 <= len(result) <= 25
            assert result.startswith("P")

    def test_duration_with_very_high_min_length(self, faker, repeats_for_fast):
        """format: duration with minLength beyond realistic values (25-32 chars)."""
        schema = {
            "type": "string",
            "format": "duration",
            "minLength": 25,
            "maxLength": 32,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 25 <= len(result) <= 32
            assert result.startswith("P")

    def test_duration_min_length_too_large(self, faker):
        """format: duration with minLength beyond max possible raises."""
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.from_jsonschema({"type": "string", "format": "duration", "minLength": 33})

    def test_uri_reference_with_length(self, faker, repeats_for_fast):
        """format: uri-reference with length constraints."""
        schema = {
            "type": "string",
            "format": "uri-reference",
            "minLength": 5,
            "maxLength": 50,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 5 <= len(result) <= 50


# -- Pattern + length tests -------------------------------------------------


class TestPatternWithLength:
    """Verify pattern+length padding for unanchored patterns."""

    def test_unanchored_pattern_with_min_length(self, faker, repeats_for_fast):
        """Unanchored pattern with minLength should pad to meet length."""
        schema = {
            "type": "string",
            "pattern": "[a-z]+",
            "minLength": 50,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert len(result) >= 50
            assert re.search("[a-z]+", result)

    def test_unanchored_pattern_with_length_range(self, faker, repeats_for_fast):
        """Unanchored pattern with min and max length."""
        schema = {
            "type": "string",
            "pattern": r"\d+",
            "minLength": 20,
            "maxLength": 40,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 20 <= len(result) <= 40
            assert re.search(r"\d+", result)

    def test_anchored_pattern_with_compatible_length(self, faker, repeats_for_fast):
        """Anchored pattern with compatible length should still work."""
        schema = {
            "type": "string",
            "pattern": r"^[a-z]{5,10}$",
            "minLength": 5,
            "maxLength": 10,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert 5 <= len(result) <= 10
            assert re.search(r"^[a-z]{5,10}$", result)
