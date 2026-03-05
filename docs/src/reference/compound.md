# Compound Keywords

Compound keywords combine or restrict multiple schemas.

---

## `allOf`

All sub-schemas must be satisfied simultaneously. The generator merges them into a single schema before generating.

```json
{
  "allOf": [
    {"type": "string", "minLength": 5},
    {"type": "string", "maxLength": 10}
  ]
}
```

```python
"eDPVAeCOB"
```

**Strategy:** all sub-schemas are merged via the same constraint-merge logic used internally. Conflicting constraints (e.g. incompatible types, `minimum > maximum`) raise `UnsatisfiableConstraintsError`.

**Limitations:** merging is keyword-based. Semantic conflicts that cannot be detected statically (e.g. two mutually exclusive `pattern` values) will not be caught until generation fails.

---

## `anyOf`

At least one sub-schema must be satisfied. The generator picks one sub-schema's type at random and generates from the subset of `anyOf` branches that share that type.

```json
{
  "anyOf": [
    {"type": "string"},
    {"type": "integer"},
    {"type": "boolean"}
  ]
}
```

```python
2233
```

**Strategy:** branches are grouped by `type`. One type is chosen at random; all branches of that type are merged and used for generation.

**Limitations:** cross-type compatibility is not checked. If branches with the same type have contradictory constraints, `UnsatisfiableConstraintsError` may be raised.

---

## `oneOf`

Exactly one sub-schema must be satisfied. The generator picks one branch at random and generates from it.

```json
{
  "oneOf": [
    {"type": "integer", "multipleOf": 3},
    {"type": "integer", "multipleOf": 5}
  ]
}
```

```python
16476
```

**Strategy:** selects one branch uniformly at random and generates from it.

**Limitations:** the generator does not verify mutual exclusivity. A value generated from one `oneOf` branch might also satisfy another branch; if strict `oneOf` semantics are required, validate the result with `jsonschema.validate()`.

---

## `not`

The generated value must not conform to the given schema.

**Excluding a type:**

```json
{"not": {"type": "string"}}
```

```python
834844010457502.2
```

**Excluding a pattern:**

```json
{"type": "string", "not": {"pattern": "^[0-9]+$"}}
```

```python
"Forward even deal evidence by maintain."
```

**Strategy:** generates values and rejects any that satisfy the `not` schema, repeating up to `max_search` times.

**Limitations:** brute-force rejection sampling. We short-circuit the `{"not": {}}` case, which forbids everything, but if the `not` schema is non-empty and very broad then generation will exhaust the search budget and raise `NoExampleFoundError`. Very narrow allowed spaces are slow.
