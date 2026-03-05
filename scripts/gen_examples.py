"""
Generate example outputs for each JSON Schema feature covered in the docs.

Run with: uv run python scripts/gen_examples.py
Produces 5 values per schema so we can pick the most representative one.
"""

import json

from faker import Faker

from faker_jsonschema.provider import JSONSchemaProvider

Faker.seed(42)
fake = Faker()
fake.add_provider(JSONSchemaProvider)


def show(label: str, schema: dict | bool, n: int = 5) -> None:
    print(f"\n### {label}")
    print(f"Schema: {json.dumps(schema) if isinstance(schema, dict) else schema}")
    for i in range(n):
        try:
            val = (
                fake.from_jsonschema(schema)
                if isinstance(schema, dict)
                else fake.from_jsonschema(schema)
            )
            print(f"  [{i + 1}] {val!r}")
        except Exception as e:
            print(f"  [{i + 1}] ERROR: {e}")


# ── Strings ──────────────────────────────────────────────────────────────────
print("\n## STRINGS")

show("plain string", {"type": "string"})
show("minLength / maxLength", {"type": "string", "minLength": 6, "maxLength": 12})
show("pattern", {"type": "string", "pattern": "^[A-Z]{3}-[0-9]{4}$"})

for fmt in [
    "date",
    "date-time",
    "time",
    "duration",
    "email",
    "idn-email",
    "uuid",
    "uri",
    "uri-reference",
    "uri-template",
    "iri",
    "iri-reference",
    "hostname",
    "idn-hostname",
    "ipv4",
    "ipv6",
    "json-pointer",
    "relative-json-pointer",
    "regex",
    "password",
    "byte",
    "binary",
]:
    show(f"format: {fmt}", {"type": "string", "format": fmt})

show("contentEncoding: base64", {"type": "string", "contentEncoding": "base64"})

# ── Numbers ───────────────────────────────────────────────────────────────────
print("\n## NUMBERS")

show("plain number", {"type": "number"})
show("minimum / maximum", {"type": "number", "minimum": 1.5, "maximum": 9.5})
show(
    "exclusiveMinimum / exclusiveMaximum (draft-06+)",
    {"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0},
)
show(
    "multipleOf (float)",
    {"type": "number", "multipleOf": 0.25, "minimum": 0, "maximum": 5},
)
show("plain integer", {"type": "integer"})
show("integer minimum / maximum", {"type": "integer", "minimum": 1, "maximum": 100})
show(
    "integer multipleOf",
    {"type": "integer", "multipleOf": 7, "minimum": 0, "maximum": 100},
)

# ── Arrays ────────────────────────────────────────────────────────────────────
print("\n## ARRAYS")

show("plain array", {"type": "array"})
show(
    "items",
    {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
)
show(
    "prefixItems (tuple)",
    {
        "type": "array",
        "prefixItems": [{"type": "integer"}, {"type": "string"}, {"type": "boolean"}],
    },
)
show(
    "minItems / maxItems",
    {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 5},
)
show(
    "uniqueItems",
    {
        "type": "array",
        "items": {"type": "integer", "minimum": 1, "maximum": 20},
        "uniqueItems": True,
        "minItems": 4,
        "maxItems": 6,
    },
)
show(
    "contains",
    {
        "type": "array",
        "items": {"type": "integer"},
        "contains": {"type": "integer", "minimum": 100},
        "minItems": 3,
        "maxItems": 5,
    },
)
show(
    "minContains / maxContains",
    {
        "type": "array",
        "items": {"type": "integer"},
        "contains": {"type": "integer", "minimum": 100},
        "minContains": 2,
        "maxContains": 3,
        "minItems": 4,
        "maxItems": 6,
    },
)
show(
    "additionalItems (draft-04 tuple)",
    {
        "type": "array",
        "items": [{"type": "integer"}, {"type": "string"}],
        "additionalItems": {"type": "boolean"},
        "minItems": 3,
        "maxItems": 4,
    },
)

# ── Objects ───────────────────────────────────────────────────────────────────
print("\n## OBJECTS")

show("plain object", {"type": "object"})
show(
    "properties + required",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0, "maximum": 120},
            "email": {"type": "string", "format": "email"},
        },
        "required": ["name", "age"],
    },
)
show(
    "additionalProperties (schema)",
    {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "additionalProperties": {"type": "boolean"},
        "minProperties": 3,
        "maxProperties": 4,
    },
)
show(
    "additionalProperties: false",
    {
        "type": "object",
        "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
        "additionalProperties": False,
        "required": ["x", "y"],
    },
)
show(
    "patternProperties",
    {
        "type": "object",
        "patternProperties": {"^x-": {"type": "string"}},
        "minProperties": 2,
        "maxProperties": 3,
    },
)
show(
    "propertyNames",
    {
        "type": "object",
        "propertyNames": {"pattern": "^[a-z]{3,8}$"},
        "additionalProperties": {"type": "integer"},
        "minProperties": 2,
        "maxProperties": 3,
    },
)
show(
    "minProperties / maxProperties",
    {
        "type": "object",
        "additionalProperties": {"type": "boolean"},
        "minProperties": 2,
        "maxProperties": 3,
    },
)
show(
    "dependentRequired",
    {
        "type": "object",
        "properties": {
            "credit_card": {"type": "string"},
            "billing_address": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "dependentRequired": {"credit_card": ["billing_address"]},
    },
)
show(
    "dependentSchemas",
    {
        "type": "object",
        "properties": {
            "plan": {"type": "string", "enum": ["free", "pro"]},
        },
        "required": ["plan"],
        "dependentSchemas": {
            "plan": {
                "properties": {"seats": {"type": "integer", "minimum": 1}},
            }
        },
    },
)

# ── Boolean & Null ────────────────────────────────────────────────────────────
print("\n## BOOLEAN & NULL")

show("boolean", {"type": "boolean"})
show("null", {"type": "null"})

# ── Compound ──────────────────────────────────────────────────────────────────
print("\n## COMPOUND")

show(
    "allOf (merges constraints)",
    {
        "allOf": [
            {"type": "string", "minLength": 5},
            {"type": "string", "maxLength": 10},
        ]
    },
)
show("anyOf", {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "boolean"}]})
show(
    "oneOf",
    {
        "oneOf": [
            {"type": "integer", "multipleOf": 3},
            {"type": "integer", "multipleOf": 5},
        ]
    },
)
show("not (excludes a type)", {"not": {"type": "string"}})
show("not (excludes a pattern)", {"type": "string", "not": {"pattern": "^[0-9]+$"}})

# ── Special ───────────────────────────────────────────────────────────────────
print("\n## SPECIAL")

show("enum", {"enum": ["alpha", "beta", "gamma", 1, None]})
show("nullable (OpenAPI)", {"type": "string", "format": "email", "nullable": True})
show("const", {"const": "fixed-value"})
show("type as array", {"type": ["string", "integer", "null"]})
show(
    "if / then / else",
    {
        "type": "integer",
        "if": {"minimum": 10},
        "then": {"multipleOf": 2},
        "else": {"maximum": 9},
    },
)
show(
    "$ref",
    {
        "$defs": {
            "Point": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
                "required": ["x", "y"],
            }
        },
        "$ref": "#/$defs/Point",
    },
)
show("boolean schema: true", True)
