"""Tests for nullable_or_enum decorator, JsonEnum, and JsonVal."""

from jsonschema import validate

from faker_jsonschema.provider import JsonEnum, JsonVal

# ── JsonVal / JsonEnum utility tests ─────────────────────────────────


def test_jsonval_hashable():
    """JsonVal wraps arbitrary JSON values making them hashable."""
    v1 = JsonVal({"a": 1, "b": [2, 3]})
    v2 = JsonVal({"a": 1, "b": [2, 3]})
    v3 = JsonVal("hello")
    v4 = JsonVal([1, 2, 3])
    v5 = JsonVal(None)

    # equal values produce equal hashes
    assert hash(v1) == hash(v2)
    # different values (very likely) produce different hashes
    assert hash(v1) != hash(v3)
    # can be put in a set
    s = {v1, v2, v3, v4, v5}
    assert len(s) == 4  # v1 and v2 are equal

    # unwrap via __wrapped__
    assert v1.__wrapped__ == {"a": 1, "b": [2, 3]}
    assert v5.__wrapped__ is None


def test_jsonenum_creation():
    """JsonEnum is a FrozenSet of JsonVal."""
    enum = JsonEnum([1, "hello", {"key": "val"}, [1, 2], None])
    assert len(enum) == 5
    assert isinstance(enum, frozenset)
    # membership
    assert JsonVal(1) in enum
    assert JsonVal("hello") in enum
    assert JsonVal(None) in enum


# ── nullable ─────────────────────────────────────────────────────────


def test_nullable_string(faker):
    """nullable: true on string type → sometimes returns None."""
    schema = {"type": "string", "nullable": True}
    results = [faker.from_jsonschema(schema) for _ in range(200)]
    types = {type(r) for r in results}
    assert type(None) in types, "nullable string should sometimes produce None"
    assert str in types, "nullable string should sometimes produce a string"
    for r in results:
        assert r is None or isinstance(r, str)


def test_nullable_integer(faker):
    """nullable: true on integer type → sometimes returns None."""
    schema = {"type": "integer", "nullable": True}
    results = [faker.from_jsonschema(schema) for _ in range(200)]
    nones = sum(1 for r in results if r is None)
    ints = sum(1 for r in results if isinstance(r, int) and not isinstance(r, bool))
    assert nones > 0, "nullable integer should sometimes produce None"
    assert ints > 0, "nullable integer should sometimes produce an integer"


def test_nullable_boolean(faker):
    """nullable: true on boolean type → sometimes returns None."""
    schema = {"type": "boolean", "nullable": True}
    results = [faker.from_jsonschema(schema) for _ in range(200)]
    types = {type(r) for r in results}
    assert type(None) in types
    assert bool in types


def test_nullable_object(faker, repeats_for_slow):
    """nullable: true on object type → sometimes returns None."""
    schema = {
        "type": "object",
        "nullable": True,
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
        "additionalProperties": False,
    }
    results = [faker.from_jsonschema(schema) for _ in range(100)]
    nones = sum(1 for r in results if r is None)
    dicts = sum(1 for r in results if isinstance(r, dict))
    assert nones > 0, "nullable object should sometimes produce None"
    assert dicts > 0, "nullable object should sometimes produce an object"


# ── enum ─────────────────────────────────────────────────────────────


def test_enum_integer(faker, repeats_for_fast):
    """Enum on integer type → always one of the enum values."""
    schema = {"type": "integer", "enum": [1, 2, 3]}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in {1, 2, 3}
        validate(result, schema)


def test_enum_string(faker, repeats_for_fast):
    """Enum on string type → always one of the enum values."""
    schema = {"type": "string", "enum": ["hello", "world", "foo"]}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in {"hello", "world", "foo"}
        validate(result, schema)


def test_enum_mixed_types(faker, repeats_for_fast):
    """Enum with mixed types (no explicit type) → one of the enum values."""
    enum_values = ["a", 1, None, True]
    schema = {"enum": enum_values}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in enum_values
        validate(result, schema)


def test_enum_with_objects(faker, repeats_for_fast):
    """Enum containing dict values."""
    enum_values = [{"a": 1}, {"b": 2}]
    schema = {"enum": enum_values}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in enum_values
        validate(result, schema)


def test_enum_with_lists(faker, repeats_for_fast):
    """Enum containing list values."""
    enum_values = [[1, 2], [3, 4], [5]]
    schema = {"enum": enum_values}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in enum_values
        validate(result, schema)


def test_enum_single_value(faker, repeats_for_fast):
    """Enum with a single value → always that value (const-like)."""
    schema = {"type": "string", "enum": ["only_option"]}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == "only_option"


def test_enum_covers_all_values(faker):
    """Over many iterations, all enum values should appear."""
    enum_values = [1, 2, 3, 4, 5]
    schema = {"type": "integer", "enum": enum_values}
    results = {faker.from_jsonschema(schema) for _ in range(500)}
    assert results == set(enum_values), f"Missing: {set(enum_values) - results}"


# ── enum via compound schemas ────────────────────────────────────────


def test_enum_on_anyof(faker, repeats_for_fast):
    """Enum works through compound schema dispatch."""
    schema = {
        "anyOf": [
            {"type": "string"},
            {"type": "integer"},
        ],
        "enum": ["allowed", 42],
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result in {"allowed", 42}


# ── const (draft-06+) ────────────────────────────────────────────────


def test_const_string(faker, repeats_for_fast):
    """Const with string → always returns that exact string."""
    schema = {"const": "hello"}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == "hello"
        validate(result, schema)


def test_const_integer(faker, repeats_for_fast):
    """Const with integer → always returns that integer."""
    schema = {"const": 42}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == 42
        validate(result, schema)


def test_const_null(faker, repeats_for_fast):
    """Const with null → always returns None."""
    schema = {"const": None}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result is None
        validate(result, schema)


def test_const_object(faker, repeats_for_fast):
    """Const with object → always returns that exact object."""
    schema = {"const": {"key": "value"}}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == {"key": "value"}
        validate(result, schema)


def test_const_array(faker, repeats_for_fast):
    """Const with array → always returns that exact array."""
    schema = {"const": [1, 2, 3]}
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result == [1, 2, 3]
        validate(result, schema)


def test_const_in_properties(faker, repeats_for_fast):
    """Const values in object properties."""
    schema = {
        "type": "object",
        "properties": {
            "version": {"const": 2},
            "name": {"type": "string"},
        },
        "required": ["version", "name"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_fast):
        result = faker.from_jsonschema(schema)
        assert result["version"] == 2
        assert isinstance(result["name"], str)
        validate(result, schema)
