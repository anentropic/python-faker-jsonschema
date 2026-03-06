# python-faker-jsonschema
Generate fake data matching a JSON Schema, using joke2k's Faker.

## Development

This project now uses [uv](https://docs.astral.sh/uv/) for dependency and environment management.
Python 3.11+ is required.

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
just test
```

## TODOs

- can we eliminate `NoExampleFoundError` failures?
- support other `contentEncoding` values besides `base64` e.g. `quoted-printable`
