import itertools
from decimal import Decimal

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError


@pytest.mark.parametrize(
    "min_value,max_value",
    itertools.product(
        (None, 0, -10.99999, -10.00001, 10.00001, 10.99999, -10, 10, 9999),
        (None, 0, -10.99999, -10.00001, 10.00001, 10.99999, -10, 10, 9999),
    ),
)
def test_better_pyfloat(faker, min_value, max_value):
    if None not in (min_value, max_value) and min_value > max_value:
        with pytest.raises(ValueError):
            faker.better_pyfloat(min_value, max_value)
        return

    result = faker.better_pyfloat(min_value, max_value)
    assert isinstance(result, float)

    if min_value is not None:
        assert result >= min_value
    if max_value is not None:
        assert result <= max_value


def test_jsonschema_number_invalid_multiple(faker):
    with pytest.raises(ValueError):
        faker.jsonschema_number(
            minimum=1,
            maximum=5,
            multiple_of=0,
        )


@pytest.mark.parametrize(
    "exclusive_min,exclusive_max", itertools.product(*[[True, False]] * 2)
)
def test_jsonschema_number_invalid_exclusive_range(faker, exclusive_min, exclusive_max):
    if True in (exclusive_min, exclusive_max):
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_number(
                minimum=5,
                maximum=5,
                exclusive_min=exclusive_min,
                exclusive_max=exclusive_max,
            )
    else:
        result = faker.jsonschema_number(
            minimum=5,
            maximum=5,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
        )
        assert isinstance(result, float)
        assert result == 5


@pytest.mark.parametrize(
    "minimum,maximum,exclusive_min,exclusive_max",
    itertools.product(
        (10,),
        (10.00000000001,),
        (True, False),
        (True, False),
    ),
)
def test_jsonschema_number_exclusive_range(
    faker, repeats_for_fast, minimum, maximum, exclusive_min, exclusive_max
):
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_number(
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
        )
        assert isinstance(result, float)
        if exclusive_min:
            assert result > minimum
        else:
            assert result >= minimum
        if exclusive_max:
            assert result < maximum
        else:
            assert result <= maximum


@pytest.mark.parametrize(
    "minimum,maximum,multiple_of",
    itertools.product(
        (None, 0, -10.99999, -10.00001, 10, 10.00001, 10.99999, -13, 13, 9999),
        (None, 0, -10.99999, -10.00001, 10, 10.00001, 10.99999, -13, 13, 9999),
        (None, -10, -3, -2.5, -1.33, 1.33, 2.5, 3, 10),
    ),
)
def test_jsonschema_number(faker, minimum, maximum, multiple_of):
    if None not in (minimum, maximum) and minimum > maximum:
        with pytest.raises(ValueError):
            faker.jsonschema_number(
                minimum=minimum,
                maximum=maximum,
                multiple_of=multiple_of,
            )
        return

    try:
        result = faker.jsonschema_number(
            minimum=minimum,
            maximum=maximum,
            multiple_of=multiple_of,
        )
    except UnsatisfiableConstraintsError:
        # we should only get UnsatisfiableConstraintsError if `multiple_of` was
        # specified in conjunction with manually-specified `minimum` and
        # `maximum` values where the range does not contain any multiple of
        # `multiple_of`
        assert multiple_of is not None
        assert minimum is not None
        assert maximum is not None
        assert int(minimum / multiple_of) == int(maximum / multiple_of)
        assert Decimal(str(minimum)) % Decimal(str(multiple_of)) != 0
        assert Decimal(str(maximum)) % Decimal(str(multiple_of)) != 0
        return

    assert isinstance(result, float)
    if minimum is not None:
        assert result >= minimum
    if maximum is not None:
        assert result <= maximum
    if multiple_of is not None:
        assert Decimal(str(result)) % Decimal(str(multiple_of)) == 0, (
            result,
            multiple_of,
            result % multiple_of,
        )


# ── from_schema round-trip tests ─────────────────────────────────────────


@pytest.mark.parametrize(
    "minimum,maximum",
    [
        (None, None),
        (0.0, 100.0),
        (-50.5, 50.5),
        (10.0, 10.0),
    ],
)
def test_from_schema_number_round_trip(faker, repeats_for_fast, minimum, maximum):
    """from_schema round trip for number with min/max constraints."""
    schema = {"type": "number"}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, (float, int))
        validate(result, schema)


def test_from_schema_number_multiple_of(faker, repeats_for_fast):
    """from_schema round trip with multipleOf."""
    schema = {"type": "number", "minimum": 0, "maximum": 100, "multipleOf": 2.5}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, (float, int))
        validate(result, schema)


# ── Draft-06+ exclusiveMinimum / exclusiveMaximum ────────────────────


def test_exclusive_minimum_numeric_number(faker, repeats_for_fast):
    """ExclusiveMinimum as number (draft-06+) for floats."""
    schema = {"type": "number", "exclusiveMinimum": 1.0, "maximum": 5.0}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, float)
        assert result > 1.0
        assert result <= 5.0
        validate(result, schema)


def test_exclusive_maximum_numeric_number(faker, repeats_for_fast):
    """ExclusiveMaximum as number (draft-06+) for floats."""
    schema = {"type": "number", "minimum": 1.0, "exclusiveMaximum": 5.0}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert isinstance(result, float)
        assert result >= 1.0
        assert result < 5.0
        validate(result, schema)


def test_exclusive_direct_call_number(faker, repeats_for_fast):
    """Direct call with exclusive_minimum/exclusive_maximum params."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_number(exclusive_minimum=0.0, exclusive_maximum=10.0)
        assert isinstance(result, float)
        assert 0.0 < result < 10.0


# ── Negative exclusive bounds ────────────────────────────────────────


class TestNegativeExclusiveBoundsNumber:
    """Verify exclusive bounds work correctly for negative float values."""

    def test_negative_exclusive_minimum_float(self, faker, repeats_for_fast):
        """ExclusiveMinimum with negative float: result must be > boundary."""
        schema = {"type": "number", "exclusiveMinimum": -5.0, "maximum": 0.0}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, float)
            assert result > -5.0, f"Expected > -5.0, got {result}"
            assert result <= 0.0
            validate(result, schema)

    def test_negative_exclusive_maximum_float(self, faker, repeats_for_fast):
        """ExclusiveMaximum with negative float: result must be < boundary."""
        schema = {"type": "number", "minimum": -10.0, "exclusiveMaximum": -5.0}
        for _ in range(repeats_for_fast):
            result = faker.from_jsonschema(schema)
            assert isinstance(result, float)
            assert result >= -10.0
            assert result < -5.0, f"Expected < -5.0, got {result}"
            validate(result, schema)


# ── multipleOf edge cases ────────────────────────────────────────────


def test_multiple_of_float_negative_range(faker, repeats_for_fast):
    """MultipleOf float in negative range."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_number(minimum=-10.0, maximum=-1.0, multiple_of=2.5)
        assert isinstance(result, float)
        assert -10.0 <= result <= -1.0
