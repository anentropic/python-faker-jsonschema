# Arrays

`{"type": "array"}` generates a random list. Without any `items` schema, elements are randomly typed.

---

## Item schema

### `items`

```json
{
  "type": "array",
  "items": {"type": "string"},
  "minItems": 2,
  "maxItems": 4
}
```

```python
["rgYiwK", "LLL-5683"]
```

**Strategy:** generates between `minItems` and `maxItems` elements (default range `0`–`default_collection_max`), each conforming to the `items` schema.

---

## Length constraints

### `minItems` / `maxItems`

```json
{"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 5}
```

```python
[6234, 4582, 8857, 8882]
```

**Strategy:** the array length is chosen uniformly at random in `[minItems, maxItems]`.

---

## Tuple validation

### `prefixItems` (draft 2020-12)

```json
{
  "type": "array",
  "prefixItems": [
    {"type": "integer"},
    {"type": "string"},
    {"type": "boolean"}
  ]
}
```

```python
[4372, "Exactly source bill risk evening.", False]
```

**Strategy:** generates exactly one item per entry in `prefixItems`, each from its own schema. Items beyond the prefix are not generated unless `items` is also specified.

When `items` is present alongside `prefixItems`, it acts as the schema for all items after the prefix:

```json
{
  "type": "array",
  "prefixItems": [
    {"type": "integer"},
    {"type": "string", "format": "first_name"},
    {"type": "boolean"}
  ],
  "items": {"type": "string", "enum": ["red", "green", "blue"]},
  "minItems": 5,
  "maxItems": 6
}
```

```python
[4644, "Randy", True, "blue", "blue"]
```

The first three positions are fixed by `prefixItems`; the remaining positions (here two extra) are generated from `items`.

### `items` as array + `additionalItems` (draft-04 – 2019-09)

Before draft 2020-12, tuple validation used `items` as an array of schemas and `additionalItems` for any items beyond that tuple:

```json
{
  "type": "array",
  "items": [{"type": "string"}, {"type": "integer"}],
  "additionalItems": {"type": "boolean"},
  "minItems": 4,
  "maxItems": 5
}
```

```python
["Return long bed after.", 6211, True, False]
```

The first two positions follow the `items` tuple schemas; the extra positions are generated from `additionalItems`. `additionalItems: false` disallows any items beyond the tuple. This schema form is only valid when validated with a draft-04 through 2019-09 validator.

---

## Uniqueness

### `uniqueItems`

```json
{
  "type": "array",
  "items": {"type": "integer", "minimum": 1, "maximum": 20},
  "uniqueItems": true,
  "minItems": 4,
  "maxItems": 6
}
```

```python
[14, 8, 1, 20, 13]
```

**Strategy:** generates candidate items one at a time, rejecting duplicates. For schemas with a finite value domain (e.g. a bounded integer range), the generator enumerates all possible values and samples without replacement.

**Limitations:**

- When the domain is large or unbounded, uniqueness is enforced by rejection sampling, which can be slow if `minItems` is close to the domain size.
- Requesting more unique items than the schema's domain permits raises `UnsatisfiableConstraintsError`.

---

## Contains constraint

### `contains`

```json
{
  "type": "array",
  "items": {"type": "integer"},
  "contains": {"type": "integer", "minimum": 100},
  "minItems": 3,
  "maxItems": 5
}
```

```python
[496, 1829, 1829]
```

**Strategy:** generates the required number of `contains`-matching items first (guaranteed to satisfy the constraint), then fills the remainder from the `items` schema.

---

### `minContains` / `maxContains`

```json
{
  "type": "array",
  "items": {"type": "integer"},
  "contains": {"type": "integer", "minimum": 100},
  "minContains": 2,
  "maxContains": 3,
  "minItems": 4,
  "maxItems": 6
}
```

```python
[777, 1937, 2848]
```

**Strategy:** picks a target contains-count uniformly in `[minContains, maxContains]`, generates exactly that many matching items, then fills the rest from `items`. Non-matching items are rejected if they accidentally satisfy `contains` beyond the budget.

**Limitations:**

- `minContains`/`maxContains` without a `contains` keyword are ignored.
- Near the `maxContains` boundary, rejection sampling may be needed; very tight budgets can exhaust `max_search` attempts.
