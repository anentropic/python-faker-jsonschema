from jsonschema import validate


def test_jsonschema_boolean_direct(faker, repeats_for_fast):
    """Direct call returns a bool."""
    for _ in range(repeats_for_fast):
        result = faker.jsonschema_boolean()
        assert isinstance(result, bool)


def test_jsonschema_boolean_from_schema(faker, repeats_for_fast):
    """from_schema round-trip for boolean type."""
    schema = {"type": "boolean"}
    for _ in range(repeats_for_fast):
        result = faker.from_schema(schema)
        assert isinstance(result, bool)
        validate(result, schema)


def test_jsonschema_boolean_both_values(faker):
    """Over many iterations, both True and False should appear."""
    results = {faker.jsonschema_boolean() for _ in range(200)}
    assert True in results
    assert False in results
