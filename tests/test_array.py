import pytest
from jsonschema import validate


# @pytest.mark.flaky(max_runs=50, min_passes=50)
@pytest.mark.parametrize(
    "schema",
    (
        {},
    )
)
def test_jsonschema_array_from_schema(
    faker, schema
):
    result = faker.jsonschema_array()
    assert isinstance(result, list)
