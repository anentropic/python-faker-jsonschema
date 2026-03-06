# faker-jsonschema

[ [Docs](https://anentropic.github.io/python-faker-jsonschema/) ]

`faker-jsonschema` is a [Faker](https://faker.readthedocs.io/) provider that generates random data conforming to a [JSON Schema](https://json-schema.org/).

Pass any JSON Schema dict to `faker.from_jsonschema()` and get back a valid, randomly generated value.

1800+ unit and PBT tests aiming to ensure correctness. Limitations of our strategies are acknowledged in the docs.

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

See the [full documentation here](https://anentropic.github.io/python-faker-jsonschema/).

## Acknowledgements

This project exists because I have used [joke2k's Faker lib](https://github.com/joke2k/faker) many times at work and find it an invaluable tool in tests.

JSON Schema has some property specs defined as regex in JS syntax. So we need a way to translate those into Python/PCRE syntax that we can execute. We have vendored a fork of the now unmaintained [`Zac-HD/js-regex`](https://github.com/Zac-HD/js-regex) lib for that purpose, which unlocked that feature for us.

And then we needed a way to generate random values that match such a regex, for this we make use of the brilliant [Hypothesis](https://hypothesis.readthedocs.io/en/latest/) Property-based testing library, which has a handy `from_regex()` generation strategy. We also have some PBT tests using Hypothesis for its intended purpose.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency and environment management.
Python 3.11+ is required.

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
just test
```

## TODOs

- can we eliminate more `NoExampleFoundError` failures?
- republish improved `js-regex` as new lib
- make regex support optional to avoid Hypothesis dependency, or implement own regex generation strategy
