# Special Keywords

---

## `enum`

Restricts values to a fixed set. Elements can be of any JSON type, including `null`.

```json
{"enum": ["alpha", "beta", "gamma", 1, null]}
```

```python
"gamma"
```

**Strategy:** picks one element from the `enum` array uniformly at random. The `type` keyword (if present) is ignored when `enum` is set.

---

## `nullable` (OpenAPI)

An OpenAPI 3.0 extension. When `true`, the generator returns `null` approximately 50 % of the time; otherwise it generates a normal value from the `type`.

```json
{"type": "string", "format": "email", "nullable": true}
```

```python
"richard56@example.com"

# or on another call:
None
```

**Strategy:** a coin-flip at the start of generation; heads returns `None` immediately, tails proceeds with normal schema generation.

**Limitations:** `nullable` is not part of JSON Schema draft-07+; it is specific to OpenAPI 3.0. For JSON Schema 2019-09 and later, use `{"type": ["string", "null"]}` instead.

---

## `const`

Constrains the value to a single fixed value.

```json
{"const": "fixed-value"}
```

```python
"fixed-value"
```

**Strategy:** always returns the `const` value unchanged. Any `type` keyword alongside `const` is ignored.

---

## Type as array

`type` may be an array of type names. The generator picks one at random and generates a value of that type.

```json
{"type": ["string", "integer", "null"]}
```

```python
"From always activity test nearly out begin newspaper."

# or on another call:
42
# or on another call:
None
```

**Strategy:** one type is chosen uniformly at random from the array; generation then proceeds as if `{"type": "<chosen>"}` was specified.

---

## `if` / `then` / `else`

Conditional schema application. The generator randomly decides whether to satisfy the `if` schema:

- **satisfying `if`:** generates from the merged result of the base schema and `then` (if present).
- **not satisfying `if`:** generates from the merged result of the base schema and `else` (if present).

```json
{
  "type": "integer",
  "if":   {"minimum": 10},
  "then": {"multipleOf": 2},
  "else": {"maximum": 9}
}
```

```python
-20  # satisfied "else": value < 10
# or on another call:
16  # satisfied "if" + "then": value >= 10 and even
```

**Strategy:** the `if`/`then`/`else` branch is chosen randomly (50/50). The chosen sub-schema is merged with the root schema and generation proceeds from the merged result.

**Limitations:** the generator does not guarantee which branch it satisfies on any given call.

---

## `$ref`

References another schema defined in `$defs` (draft 2019-09+) or `definitions` (draft-07 and earlier) within the same root schema.

```json
{
  "$defs": {
    "Point": {
      "type": "object",
      "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
      "required": ["x", "y"]
    }
  },
  "$ref": "#/$defs/Point"
}
```

```python
{"x": -467939042953601.44, "y": -744861589451087.2}
```

**Strategy:** resolves the JSON Pointer in `$ref` against the root schema stored in the generation context, then generates from the referenced schema.

**Limitations:**

- Only local (`#/...`) references are supported. External URL references are not resolved.
- Circular `$ref` chains are detected; when the recursion depth exceeds `3 * max_depth`, a `UnsatisfiableConstraintsError` is raised.

---

## Boolean schemas

A JSON Schema can be the literal `true` or `false` instead of an object.

| Schema | Behaviour |
|--------|-----------|
| `true` | Equivalent to `{}` — generates any random JSON value. |
| `false` | Always raises `UnsatisfiableConstraintsError`; no value is valid. |

```json
true
```

```python
7698  # any JSON value
{"x": 1.5}  # any JSON value
[1, 2, 3]  # any JSON value
```
