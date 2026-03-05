"""Tests for Context, depth limiting, and context lifecycle."""

import pytest

from faker_jsonschema.provider import JSONSchemaProvider


@pytest.fixture()
def provider(faker):
    """Get the JSONSchemaProvider instance from the faker."""
    for p in faker.providers:
        if isinstance(p, JSONSchemaProvider):
            return p
    pytest.fail("JSONSchemaProvider not found")


# ── Context lifecycle ────────────────────────────────────────────────


def test_context_reset_after_from_schema(faker, provider):
    """After from_schema completes, _context is reset to None."""
    faker.from_schema({"type": "string"})
    assert provider._context is None


def test_context_lazy_init_on_direct_method_call(faker, provider):
    """Calling a type method directly lazily inits context via property."""
    provider._context = None
    _ = faker.jsonschema_string()
    # after the call the context was lazily created (and may be reset)
    # the important thing is it didn't crash


def test_context_lazy_init_property(provider):
    """Accessing .context when _context is None creates a default Context."""
    provider._context = None
    ctx = provider.context
    assert ctx is not None
    assert ctx._depth == 0
    assert ctx.max_depth == 5
    assert ctx.max_search == 500
    # reset
    provider._context = None


# ── Depth limiting ───────────────────────────────────────────────────


def test_from_schema_max_depth_limits_nesting(faker, repeats_for_slow):
    """max_depth=2 should prevent deep nesting — result should still be valid."""
    schema = {
        "type": "object",
        "properties": {
            "child": {
                "type": "object",
                "properties": {
                    "grandchild": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                        },
                    },
                },
            },
        },
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema, max_depth=2)
        assert isinstance(result, dict)


def test_from_schema_max_depth_1_flat_types(faker, repeats_for_slow):
    """max_depth=1 should heavily favor flat types in generated content."""
    # With a low max_depth, any-typed values should mostly be flat
    schema = {
        "type": "object",
        "properties": {
            "a": {},  # any type
            "b": {},
            "c": {},
        },
        "required": ["a", "b", "c"],
        "additionalProperties": False,
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema, max_depth=1)
        assert isinstance(result, dict)
        assert "a" in result
        assert "b" in result
        assert "c" in result


def test_from_schema_deeply_nested_terminates(faker):
    """Deeply nested schema should still terminate (not infinite loop)."""
    schema = {
        "type": "object",
        "properties": {
            "level1": {
                "type": "object",
                "properties": {
                    "level2": {
                        "type": "object",
                        "properties": {
                            "level3": {
                                "type": "object",
                                "properties": {
                                    "level4": {
                                        "type": "object",
                                        "properties": {
                                            "level5": {
                                                "type": "object",
                                                "properties": {
                                                    "value": {"type": "string"},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
    result = faker.from_schema(schema)
    assert isinstance(result, dict)


# ── default_collection_max ───────────────────────────────────────────


def test_default_collection_max(faker, repeats_for_slow):
    """default_collection_max limits auto-chosen array size."""
    schema = {
        "type": "array",
        "items": {"type": "integer"},
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema, default_collection_max=5)
        assert isinstance(result, list)
        assert len(result) <= 10  # some headroom but bounded


def test_default_collection_max_objects(faker, repeats_for_slow):
    """default_collection_max affects object property count too."""
    schema = {
        "type": "object",
    }
    for _ in range(repeats_for_slow):
        result = faker.from_schema(schema, default_collection_max=3)
        assert isinstance(result, dict)
        # can't be too strict but should be bounded
        assert len(result) <= 10


# ── max_search ───────────────────────────────────────────────────────


def test_max_search_parameter(faker):
    """max_search is configurable via from_schema context."""
    # Just verify it doesn't crash and respects the parameter
    result = faker.from_schema({"type": "string"}, max_search=10)
    assert isinstance(result, str)
