# faker-jsonschema

`faker-jsonschema` is a [Faker](https://faker.readthedocs.io/) provider that generates random data conforming to a [JSON Schema](https://json-schema.org/).

Pass any JSON Schema dict to `faker.from_jsonschema()` and get back a valid, randomly generated value.

## Install

```bash
pip install faker-jsonschema
# or
uv add faker-jsonschema
```

## Usage

```python
from faker import Faker
from faker_jsonschema.provider import JSONSchemaProvider

fake = Faker()
fake.add_provider(JSONSchemaProvider)

schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["name", "score"],
}

print(fake.from_jsonschema(schema))
# {'name': 'Doctor pass describe matter.', 'score': 8}
```

New to the library? Start with the [Quickstart](quickstart.md).
Ready to look up a specific keyword? Jump straight to the [Reference](reference/strings.md).
