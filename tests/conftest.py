import os
import random

import pytest
from faker import Faker

from faker_jsonschema.provider import JSONSchemaProvider


@pytest.fixture(scope="session")
def faker(record_testsuite_property):
    seed = int(os.getenv("SEED", random.randint(0, 9999999)))
    # TODO if we made a plugin could we print this nicer?
    # https://docs.pytest.org/en/latest/writing_plugins.html#conftest-py-plugins
    record_testsuite_property("SEED", seed)
    print("SEED={}  ".format(seed), end='')

    Faker.seed(seed)
    fake = Faker()
    fake.add_provider(JSONSchemaProvider)
    return fake


@pytest.fixture(scope="session")
def repeats_for_slow(record_testsuite_property):
    count = 10
    record_testsuite_property("REPEATS", count)
    return count


@pytest.fixture(scope="session")
def repeats_for_fast(record_testsuite_property):
    count = 50
    record_testsuite_property("REPEATS", count)
    return count
