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
- For unanchored patterns (no `$` end anchor), short regex matches are automatically padded with random characters to meet `minLength`, since JSON Schema `pattern` uses substring matching (`re.search`).
- Anchored patterns (`^...$`) with very tight `minLength`/`maxLength` constraints may exhaust the search budget and raise `NoExampleFoundError`.

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
| `byte` | `'bVJmbDFkdUFSUVhr...'` | Base64-encoded string |
| `binary` | `'\u00f6\u00cc\f6...'` | Binary data returned as a Python `str` |

**Strategy:** each format maps to a dedicated generator method. Most variable-length formats (`email`, `uri`, `hostname`, `duration`, `json-pointer`, etc.) are length-aware — they accept `minLength`/`maxLength` and produce output in that range directly, without retry. If the requested length falls outside the format's valid bounds (e.g. `minLength: 300` for `email`, which exceeds the RFC 5321 maximum of 254), an `UnsatisfiableConstraintsError` is raised. Fixed-length formats (`date`, `uuid`, etc.) ignore length constraints. The `regex` format and any unknown format resolved via Faker fall back to retry sampling (up to `max_search` attempts).

**Limitations:**

- `pattern` takes precedence over `format` when both are set.
- `binary` uses a Latin-1 decoded string so each byte value maps losslessly onto one code point. This keeps the JSON Schema type as `string`, but the result may contain non-printable characters.
- `contentMediaType` is accepted in the schema but ignored during generation (it serves as a hint only).
- `password` with `maxLength < 4` produces random alphanumeric strings instead of strong passwords (Faker's `password()` generator requires at least 4 characters for its character-class guarantees).
- `duration` generates realistic calendar values (years <= 10, months <= 11, etc.) for typical lengths (up to 20 chars). When `minLength` exceeds 20, the fallback inflates component values beyond realistic ranges to reach the target. Maximum achievable length is 32 characters; `minLength > 32` raises `UnsatisfiableConstraintsError`.

---

## Content encoding

### `contentEncoding`

All RFC-defined `contentEncoding` values are supported. All return Python `str` values so the generated instance still conforms to JSON Schema `type: string`. Unknown values fall through to plain string generation.

| Value | RFC | Description |
|---|---|---|
| `"base64"` | RFC 4648 §4 | 64-character alphabet; encoded length is a multiple of 4 |
| `"base32"` | RFC 4648 §6 | 32-character alphabet; encoded length is a multiple of 8 |
| `"base16"` | RFC 4648 §8 | Hex alphabet; encoded length is always even |
| `"7bit"` | RFC 2045 §2.7 | Printable ASCII (0x20–0x7E); no NUL or bare CR/LF |
| `"8bit"` | RFC 2045 §2.8 | Printable ASCII + octets >127; no NUL or bare CR/LF |
| `"binary"` | RFC 2045 §2.9 | Any octet sequence |
| `"quoted-printable"` | RFC 2045 §6.7 | Printable ASCII encoded per QP rules |

```json
{"type": "string", "contentEncoding": "base64"}
```

```
'dGVzdA=='
```

```json
{"type": "string", "contentEncoding": "base32"}
```

```
'ORSXG5BR'
```

```json
{"type": "string", "contentEncoding": "base16"}
```

```
'48656C6C6F'
```

```json
{"type": "string", "contentEncoding": "quoted-printable"}
```

```
'Hello World'
```

**Strategy:** `minLength`/`maxLength` constrain the *encoded* output length. For `base64`, `base32`, and `base16`, the generator first chooses a valid encoded length and then generates raw bytes that encode to that length before decoding the encoded result back to text.

**Limitations:** `binary` and `8bit` may contain non-printable characters because they preserve arbitrary octets inside a Python string. For `base64`, `base32`, and `base16`, an `UnsatisfiableConstraintsError` is raised if no valid encoded length can fit within the requested range.
