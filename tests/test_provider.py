import itertools
import os
import random
from decimal import Decimal

import pytest
from faker import Faker

from faker_jsonschema.provider import JSONSchemaProvider


@pytest.fixture
def faker(record_property):
    seed = int(os.getenv("SEED", random.randint(0, 9999999)))
    record_property("SEED", seed)
    print("SEED={}  ".format(seed), end='')
    Faker.seed(seed)
    fake = Faker()
    fake.add_provider(JSONSchemaProvider)
    return fake


@pytest.mark.parametrize(
    "min_value,max_value",
    itertools.product(
        (None, 0, -10.99999, -10.00001, 10.00001, 10.99999, -10, 10, 9999),
        (None, 0, -10.99999, -10.00001, 10.00001, 10.99999, -10, 10, 9999),
    )
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
    "exclusive_min,exclusive_max",
    itertools.product(*[[True, False]]*2)
)
def test_jsonschema_number_invalid_exclusive_range(
    faker, exclusive_min, exclusive_max
):
    if True in (exclusive_min, exclusive_max):
        with pytest.raises(ValueError):
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
    "minimum,maximum,multiple_of",
    itertools.product(
        (None, 0, -10.99999, -10.00001, 10, 10.00001, 10.99999, -13, 13, 9999),
        (None, 0, -10.99999, -10.00001, 10, 10.00001, 10.99999, -13, 13, 9999),
        (None, -10, -3, -2.5, -1.33, 1.33, 2.5, 3, 10),
    )
)
def test_jsonschema_number(faker, minimum, maximum, multiple_of):
    if None not in (minimum, maximum):
        if (minimum > maximum):
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
    except ValueError:
        # we should only get ValueError if `multiple_of` was specified in
        # conjunction with manually-specified `minimum` and `maximum` values
        # where the range does not contain any multiple of `multiple_of`
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
            result, multiple_of, result % multiple_of)
