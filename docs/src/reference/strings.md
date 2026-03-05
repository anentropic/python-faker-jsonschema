# Strings

`{"type": "string"}` generates a random string. Without any constraints, Faker's default `text()` generator is used.

---

## Length constraints

### `minLength` / `maxLength`

```json
{"type": "string", "minLength": 6, "maxLength": 12}
```

```
'rgYiwK'
```

**Strategy:** generates a random alphanumeric string between `minLength` and `maxLength` characters.

---

## Pattern

### `pattern`

```json
{"type": "string", "pattern": "^[A-Z]{3}-[0-9]{4}$"}
```

```
'LLL-5683'
```

**Strategy:** uses [Hypothesis `st.from_regex`](https://hypothesis.readthedocs.io/en/latest/data.html#hypothesis.strategies.from_regex) to generate a string matching the regex. JSON Schema regexes are JavaScript-compatible (ECMA 262) so we have a custom translator before handing it off to the Hypothesis (Python) generator. Matching rules follow JS; without `^...$` anchors it matches as a substring.

**Limitations:**

- `pattern` and `format` are mutually exclusive — `pattern` takes precedence when both are specified.
- Very tight combinations of `pattern` + `minLength`/`maxLength` may exhaust the search budget and raise `NoExampleFoundError`.

---

## Format

### `format`

```json
{"type": "string", "format": "date"}
```

The `format` keyword selects a specific value generator. All supported formats are listed below.

| Format | Example | Notes |
|--------|---------|-------|
| `date` | `'2018-12-12'` | ISO 8601 date, always 10 characters |
| `date-time` | `'1989-09-22T15:57:18.372797+00:14'` | ISO 8601 datetime with timezone |
| `time` | `'04:36:05+02:00'` | RFC 3339 §5.6 full-time with UTC offset |
| `duration` | `'P5Y6M2DT21H58M21S'` | ISO 8601 / RFC 3339 Appendix A duration |
| `email` | `'christinaturner@example.net'` | ASCII email address |
| `idn-email` | `'clarence34@example.org'` | Internationalized email (RFC 6531); ASCII subset |
| `uuid` | `'2d06e8cf-3805-4907-acd6-6193c7468f59'` | UUID v4, always 36 characters |
| `uri` | `'https://manning.info/posts/list/taglogin.jsp'` | Absolute URI |
| `uri-reference` | `'/ozuI/LRVYBVE/f/hyctlqN'` | Absolute URI or relative reference path |
| `uri-template` | `'http://www.peterson.com/categories/tagshome.asp{XHRKw}'` | RFC 6570 URI Template |
| `iri` | `'https://www.turner.net/categorymain.php'` | IRI (RFC 3987); ASCII URIs are valid IRIs |
| `iri-reference` | `'/Iijda/JybooSdm'` | IRI-reference; reuses uri-reference logic |
| `hostname` | `'db-75.cook-santiago.com'` | DNS hostname |
| `idn-hostname` | `'desktop-77.johnson.org'` | Internationalized hostname (RFC 5890); ASCII subset |
| `ipv4` | `'216.215.4.203'` | IPv4 address |
| `ipv6` | `'89e0:6ab3:7250:ee18:260a:5963:dd81:b7f5'` | IPv6 address |
| `json-pointer` | `'/Svqy/uIQZzbA/TTwBxL/TYdOnGu'` | RFC 6901 JSON Pointer |
| `relative-json-pointer` | `'4/RkuzmDDZ/bRuaS/M'` | Relative JSON Pointer |
| `regex` | `'[A-Z][a-z]*'` | A valid regular expression pattern |
| `password` | `'ZZMda($#z(5RGF...'` | A strong password string |
| `byte` | `b'mRfl1duARQXk...'` | Base64-encoded bytes (`bytes` object) |
| `binary` | `b'\xf6\xcc\x0c...'` | Raw binary bytes (`bytes` object) |

**Strategy:** each format maps to a dedicated Faker generator method. The generated value is checked against any `minLength`/`maxLength` constraints; for variable-length formats, a fresh value is sampled until one fits (up to `max_search` attempts).

**Limitations:**

- `pattern` takes precedence over `format` when both are set.
- `byte` and `binary` return Python `bytes` objects rather than `str`. If your consumer requires a `str`, decode accordingly.
- `contentMediaType` is accepted in the schema but ignored during generation (it serves as a hint only).

---

## Content encoding

### `contentEncoding`

```json
{"type": "string", "contentEncoding": "base64"}
```

```
b'dGVzdA=='
```

**Strategy:** `"base64"` produces base64-encoded `bytes`. Only `"base64"` is currently supported.

**Limitations:** returns `bytes`, not `str`. Other encoding values (e.g. `"quoted-printable"`) are not supported and will fall through to plain string generation.
