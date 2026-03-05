import itertools

import pytest
from jsonschema import validate

from faker_jsonschema.provider import UnsatisfiableConstraintsError


def test_jsonschema_integer_invalid_multiple(faker):
    with pytest.raises(ValueError):
        faker.jsonschema_integer(
            minimum=1,
            maximum=5,
            multiple_of=0,
        )


@pytest.mark.parametrize(
    "exclusive_min,exclusive_max", itertools.product(*[[True, False]] * 2)
)
def test_jsonschema_integer_invalid_exclusive_range(
    faker, exclusive_min, exclusive_max
):
    if True in (exclusive_min, exclusive_max):
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_integer(
                minimum=5,
                maximum=5,
                exclusive_min=exclusive_min,
                exclusive_max=exclusive_max,
            )
    else:
        result = faker.jsonschema_integer(
            minimum=5,
            maximum=5,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
        )
        assert isinstance(result, int)
        assert result == 5


@pytest.mark.parametrize(
    "minimum,maximum,exclusive_min,exclusive_max",
    itertools.product(
        (10,),
        (12,),
        (True, False),
        (True, False),
    ),
)
def test_jsonschema_integer_exclusive_range(
    faker, repeats_for_fast, minimum, maximum, exclusive_min, exclusive_max
):
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_integer(
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
        )
        assert isinstance(result, int)
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
        (None, 0, -3, 3, 10, -13, 13, 9999),
        (None, 0, -3, 3, 10, -13, 13, 9999),
        (None, -10, -3, 3, 10),
    ),
)
def test_jsonschema_integer(faker, minimum, maximum, multiple_of):
    if None not in (minimum, maximum) and minimum > maximum:
        with pytest.raises(ValueError):
            faker.jsonschema_integer(
                minimum=minimum,
                maximum=maximum,
                multiple_of=multiple_of,
            )
        return

    try:
        result = faker.jsonschema_integer(
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
        assert minimum % multiple_of != 0
        assert maximum % multiple_of != 0
        return

    assert isinstance(result, int)
    if minimum is not None:
        assert result >= minimum
    if maximum is not None:
        assert result <= maximum
    if multiple_of is not None:
        assert result % multiple_of == 0, (result, multiple_of, result % multiple_of)


# ── from_schema round-trip tests ─────────────────────────────────────────


@pytest.mark.parametrize(
    "minimum,maximum",
    [
        (None, None),
        (0, 100),
        (-50, 50),
        (10, 10),
    ],
)
def test_from_schema_integer_round_trip(faker, repeats_for_fast, minimum, maximum):
    """from_schema round trip for integer with min/max constraints."""
    schema = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        validate(result, schema)


def test_from_schema_integer_multiple_of(faker, repeats_for_fast):
    """from_schema round trip with multipleOf."""
    schema = {"type": "integer", "minimum": 0, "maximum": 100, "multipleOf": 5}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        validate(result, schema)


def test_from_schema_integer_exclusive(faker, repeats_for_fast):
    """from_schema round trip with exclusiveMinimum / exclusiveMaximum."""
    schema = {
        "type": "integer",
        "minimum": 10,
        "maximum": 20,
        "exclusiveMin": True,
        "exclusiveMax": True,
    }
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, int)
        assert result > 10
        assert result < 20


# ── Draft-06+ exclusiveMinimum / exclusiveMaximum ────────────────────


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


def test_exclusive_direct_call_integer(faker, repeats_for_fast):
    """Direct call with exclusive_minimum/exclusive_maximum params."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_integer(exclusive_minimum=0, exclusive_maximum=10)
        assert isinstance(result, int)
        assert 0 < result < 10


# ── Negative exclusive bounds ────────────────────────────────────────


class TestNegativeExclusiveBoundsInteger:
    """Verify exclusive bounds work correctly for negative integer values."""

    def test_negative_exclusive_minimum_integer(self, faker, repeats_for_fast):
        """ExclusiveMinimum with negative value: result must be > boundary."""
        schema = {"type": "integer", "exclusiveMinimum": -5, "maximum": 0}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert result > -5, f"Expected > -5, got {result}"
            assert result <= 0
            validate(result, schema)

    def test_negative_exclusive_maximum_integer(self, faker, repeats_for_fast):
        """ExclusiveMaximum with negative value: result must be < boundary."""
        schema = {"type": "integer", "minimum": -10, "exclusiveMaximum": -5}
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert result >= -10
            assert result < -5, f"Expected < -5, got {result}"
            validate(result, schema)

    def test_negative_both_exclusive_integer(self, faker, repeats_for_fast):
        """Both exclusive bounds negative: -10 < result < -1."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": -10,
            "exclusiveMaximum": -1,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert -10 < result < -1, f"Expected -10 < x < -1, got {result}"
            validate(result, schema)

    def test_negative_exclusive_min_direct_call(self, faker, repeats_for_fast):
        """Direct call with negative exclusive_minimum."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(
                exclusive_minimum=-20, exclusive_maximum=-10
            )
            assert isinstance(result, int)
            assert -20 < result < -10

    def test_negative_exclusive_draft04_form(self, faker, repeats_for_fast):
        """Draft-04 boolean exclusiveMin/Max with negative values."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(
                minimum=-10, maximum=-5, exclusive_min=True, exclusive_max=True
            )
            assert isinstance(result, int)
            assert -10 < result < -5

    def test_zero_straddling_exclusive_bounds(self, faker, repeats_for_fast):
        """Exclusive bounds straddling zero: -3 < result < 3."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": -3,
            "exclusiveMaximum": 3,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert -3 < result < 3
            validate(result, schema)


# ── _safe_random_int edge cases ──────────────────────────────────────


class TestSafeRandomInt:
    """Edge cases for _safe_random_int that previously had unbounded recursion."""

    def test_both_none(self, faker, provider, repeats_for_fast):
        """Both min and max None should always terminate."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(None, None)
            assert isinstance(result, int)

    def test_equal_values(self, faker, provider, repeats_for_fast):
        """Equal min and max should return that value."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(5, 5)
            assert result == 5

    def test_negative_range(self, faker, provider, repeats_for_fast):
        """Negative min, None max should produce reasonable results."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(-100, None)
            assert isinstance(result, int)
            assert result >= -100

    def test_none_min(self, faker, provider, repeats_for_fast):
        """None min, specified max should produce values <= max."""
        for _ in range(repeats_for_fast):
            result = provider._safe_random_int(None, 50)
            assert isinstance(result, int)
            assert result <= 50


# ── multipleOf edge cases ────────────────────────────────────────────


class TestMultipleOfEdgeCasesInteger:
    """multipleOf with tricky integer constraint combinations."""

    def test_multiple_of_negative(self, faker, repeats_for_fast):
        """MultipleOf with negative min/max."""
        for _ in range(repeats_for_fast):
            result = faker.jsonschema_integer(minimum=-30, maximum=-10, multiple_of=5)
            assert isinstance(result, int)
            assert -30 <= result <= -10
            assert result % 5 == 0

    def test_multiple_of_with_exclusive_bounds(self, faker, repeats_for_fast):
        """MultipleOf combined with exclusive bounds."""
        schema = {
            "type": "integer",
            "exclusiveMinimum": 0,
            "exclusiveMaximum": 20,
            "multipleOf": 5,
        }
        for _ in range(repeats_for_fast):
            result = faker.from_schema(schema)
            assert isinstance(result, int)
            assert 0 < result < 20
            assert result % 5 == 0
            validate(result, schema)

    def test_multiple_of_unsatisfiable_raises(self, faker):
        """MultipleOf that can't be satisfied raises UnsatisfiableConstraintsError."""
        with pytest.raises(UnsatisfiableConstraintsError):
            faker.jsonschema_integer(minimum=1, maximum=4, multiple_of=5)
