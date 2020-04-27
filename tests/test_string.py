import itertools
import re
from typing import List, Optional, Tuple

import pytest

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
    )
)
def test_jsonschema_string_length(
    faker, repeats_for_slow, min_length, max_length
):
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
    )
)
def test_jsonschema_pattern(
    faker,
    pattern_spec: Tuple[str, Optional[List[int]]],
    min_length: int,
    max_length: Optional[int],
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
        with pytest.raises(NoExampleFoundError):
            faker.jsonschema_string(
                pattern=pattern,
                min_length=min_length,
                max_length=max_length,
            )
        return

    try:
        result = faker.jsonschema_string(
            pattern=pattern,
            min_length=min_length,
            max_length=max_length,
        )
    except NoExampleFoundError as e:
        # finding suitable examples (with underlying `hypothesis.example`)
        # is not deterministic, an example should exist but may not be found
        print(repr(e))
    else:
        assert isinstance(result, str)
        assert re.search(pattern, result)
        assert len(result) >= min_length
        if max_length is not None:
            assert len(result) <= max_length


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
        )
    )
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
    )
)
def test_jsonschema_format_min_max_length_fixed(
    faker, min_length, max_length
):
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
    )
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
    )
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
    )
)
def test_jsonschema_format_min_max_length_variable_range(
    faker, min_length, max_length
):
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
    )
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
