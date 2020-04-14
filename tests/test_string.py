import itertools
import re
from typing import List, Optional, Tuple

import pytest

from faker_jsonschema.provider import UnsatisfiableConstraintsError


@pytest.mark.flaky(max_runs=5, min_passes=5)
@pytest.mark.parametrize(
    "min_length,max_length",
    itertools.product(
        (3, 5, 11),
        (None, 15, 20, 25),
    )
)
def test_jsonschema_string_length(
    faker, min_length, max_length
):
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
        with pytest.raises(UnsatisfiableConstraintsError):
            result = faker.jsonschema_string(
                pattern=pattern,
                min_length=min_length,
                max_length=max_length,
            )
            print(result)
        return

    result = faker.jsonschema_string(
        pattern=pattern,
        min_length=min_length,
        max_length=max_length,
    )
    assert isinstance(result, str)
    assert re.search(pattern, result)
    assert len(result) >= min_length
    if max_length is not None:
        assert len(result) <= max_length


@pytest.mark.parametrize(
    "format_, return_type",
    (
        # defined in OpenAPI spec:
        ("date", str),
        ("date-time", str),
        ("password", str),
        ("byte", bytes),
        ("binary", bytes),
        # mentioned in OpenAPI spec as examples:
        ("email", str),
        ("uuid", str),
        ("uri", str),
        ("hostname", str),
        ("ipv4", str),
        ("ipv6", str),
    )
)
def test_jsonschema_format(faker, format_, return_type):
    result = faker.jsonschema_string(
        format_=format_,
    )
    assert isinstance(result, return_type)
