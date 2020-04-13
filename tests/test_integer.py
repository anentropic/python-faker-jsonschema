import itertools

import pytest

from faker_jsonschema.provider import UnsatisfiableConstraintsError


def test_jsonschema_integer_invalid_multiple(faker):
    with pytest.raises(ValueError):
        faker.jsonschema_integer(
            minimum=1,
            maximum=5,
            multiple_of=0,
        )


@pytest.mark.parametrize(
    "exclusive_min,exclusive_max",
    itertools.product(*[[True, False]]*2)
)
def test_jsonschema_integer_invalid_exclusive_range(
    faker, exclusive_min, exclusive_max
):
    if True in (exclusive_min, exclusive_max):
        with pytest.raises(ValueError):
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


@pytest.mark.flaky(max_runs=25, min_passes=25)
@pytest.mark.parametrize(
    "minimum,maximum,exclusive_min,exclusive_max",
    itertools.product(
        (10,),
        (12,),
        (True, False),
        (True, False),
    )
)
def test_jsonschema_integer_exclusive_range(
    faker, minimum, maximum, exclusive_min, exclusive_max
):
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
    )
)
def test_jsonschema_integer(faker, minimum, maximum, multiple_of):
    if None not in (minimum, maximum):
        if (minimum > maximum):
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
        assert result % multiple_of == 0, (
            result, multiple_of, result % multiple_of)
