# Quickstart

## Install

```bash
pip install faker-jsonschema
# or
uv add faker-jsonschema
```

Requires Python 3.11+ and [Faker](https://faker.readthedocs.io/) 18+.

## Register the provider

`faker-jsonschema` adds itself to an existing `Faker` instance via `add_provider`:

```python
from faker import Faker
from faker_jsonschema.provider import JSONSchemaProvider

fake = Faker()
fake.add_provider(JSONSchemaProvider)
```

## Generate data

Call `fake.from_jsonschema()` with any JSON Schema dict:

```python
schema = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "email": {"type": "string", "format": "email"},
        "active": {"type": "boolean"},
    },
    "required": ["id", "email"],
}

result = fake.from_jsonschema(schema)
# {'id': 8, 'email': 'christinaturner@example.net', 'active': False}
```

The returned value always conforms to the schema.

## Validate the output

Use [jsonschema](https://python-jsonschema.readthedocs.io/) validator library to assert conformance in tests:

```python
from jsonschema import validate

result = fake.from_jsonschema(schema)
validate(result, schema)  # raises if invalid
```

## Seed for reproducibility

Seed Faker before creating the instance to get deterministic output:

```python
Faker.seed(42)
fake = Faker()
fake.add_provider(JSONSchemaProvider)

result = fake.from_jsonschema({"type": "integer", "minimum": 1, "maximum": 100})
# Always produces the same value for the same seed
```

## Context options

`from_jsonschema()` accepts keyword arguments that control generation behaviour:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_depth` | `5` | Maximum nesting depth for recursive types (objects, arrays). Once reached, nested schemas generate flat (non-recursive) types instead. |
| `default_collection_max` | `50` | Upper bound used when no `maxItems` / `maxProperties` is specified. |
| `max_search` | `500` | Maximum attempts for brute-force constraint satisfaction (used by `not`, `pattern`+length combinations, etc.). |
| `default_property_schema` | `{"type": "string", "format": "user_name"}` | Schema applied when generating object property names (used for `additionalProperties` and `patternProperties` keys when arbitrary extra properties hav eto be generated). |

```python
result = fake.from_jsonschema(schema, max_depth=3, default_collection_max=10)
```

## Error handling

Two exceptions can be raised during generation:

| Exception | Meaning |
|-----------|---------|
| `UnsatisfiableConstraintsError` | The schema's constraints cannot simultaneously be satisfied — e.g. `minimum: 10, maximum: 5`, or `allOf` with contradicting types. |
| `NoExampleFoundError` | The generator exhausted its search budget (`max_search` attempts) without finding a conforming value — typically caused by very tight `pattern` + length constraints, or an over-constrained `not` schema. |

```python
from faker_jsonschema.provider import UnsatisfiableConstraintsError, NoExampleFoundError

try:
    result = fake.from_jsonschema(schema)
except UnsatisfiableConstraintsError as e:
    print("Schema is unsatisfiable:", e)
except NoExampleFoundError as e:
    print("Could not find a valid value:", e)
```
