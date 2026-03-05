import os
import random

import pytest
from faker import Faker

from faker_jsonschema.provider import JSONSchemaProvider

_DEFAULT_REPEATS_SLOW = 10
_DEFAULT_REPEATS_FAST = 50


@pytest.fixture(scope="session")
def faker(record_testsuite_property):
    seed = int(os.getenv("SEED", random.randint(0, 9999999)))
    # TODO if we made a plugin could we print this nicer?
    # https://docs.pytest.org/en/latest/writing_plugins.html#conftest-py-plugins
    record_testsuite_property("SEED", seed)
    print(f"SEED={seed}  ", end="")

    Faker.seed(seed)
    fake = Faker()
    fake.add_provider(JSONSchemaProvider)
    return fake


@pytest.fixture(scope="session")
def repeats_for_slow(record_testsuite_property):
    count = int(os.getenv("REPEATS_SLOW", _DEFAULT_REPEATS_SLOW))
    record_testsuite_property("REPEATS_SLOW", count)
    return count


@pytest.fixture(scope="session")
def repeats_for_fast(record_testsuite_property):
    count = int(os.getenv("REPEATS_FAST", _DEFAULT_REPEATS_FAST))
    record_testsuite_property("REPEATS_FAST", count)
    return count


@pytest.fixture()
def provider(faker):
    """Get the JSONSchemaProvider instance from the faker."""
    for p in faker.providers:
        if isinstance(p, JSONSchemaProvider):
            return p
    pytest.fail("JSONSchemaProvider not found")
