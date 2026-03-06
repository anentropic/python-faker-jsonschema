# Numbers & Integers

Both `"type": "number"` (floating-point) and `"type": "integer"` support the same set of constraint keywords.

---

## Unconstrained

### `number`

```json
{"type": "number"}
```

```
306449350781176.75
```

### `integer`

```json
{"type": "integer"}
```

```
4270
```

**Strategy:** without bounds, picks from Faker's full numeric range. Use `minimum`/`maximum` to keep values in a practical range.

---

## Range constraints

### `minimum` / `maximum`

```json
{"type": "number", "minimum": 1.5, "maximum": 9.5}
```

```
8.271551564583998
```

```json
{"type": "integer", "minimum": 1, "maximum": 100}
```

```
8
```

**Strategy:** for `number`, generates a random float uniformly in `[minimum, maximum]`. For `integer`, generates a random int in `[minimum, maximum]`.

---

### `exclusiveMinimum` / `exclusiveMaximum`

Draft-06+ numeric form (a number, not a boolean):

```json
{"type": "number", "exclusiveMinimum": 0.0, "exclusiveMaximum": 1.0}
```

```
0.3542277718420278
```

Draft-04 boolean form is also accepted:

```json
{"type": "number", "minimum": 0.0, "maximum": 1.0, "exclusiveMinimum": true, "exclusiveMaximum": true}
```

**Strategy:** numeric exclusive bounds are converted to an open interval. For floats, a small epsilon is added/subtracted from the limit to stay strictly inside the boundary.

**Limitations:** draft-04 boolean `exclusiveMinimum`/`exclusiveMaximum` are supported, but numeric form (draft-06+) takes precedence when both are present.

---

## Multiple constraint

### `multipleOf`

```json
{"type": "number", "multipleOf": 0.25, "minimum": 0, "maximum": 5}
```

```
4.5
```

```json
{"type": "integer", "multipleOf": 7, "minimum": 0, "maximum": 100}
```

```
70
```

**Strategy:** enumerates all valid multiples inside the `[minimum, maximum]` range and picks one at random.

**Limitations:**

- `multipleOf` must be greater than zero.
- For unbounded ranges, the generator samples up to `max_search` candidates and picks the first valid multiple; very sparse ranges may raise `NoExampleFoundError`.
- Floating-point arithmetic is performed via `Decimal` to reduce precision errors, but edge cases near the boundary may still produce off-by-epsilon values.
