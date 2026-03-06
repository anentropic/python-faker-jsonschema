import contextlib
import datetime
import inspect
import itertools
import json
import math
import operator
import quopri
import re
import sys
import warnings
from base64 import b16encode, b32encode, b64encode
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, StrEnum, auto
from functools import partial, reduce, wraps
from numbers import Number
from random import shuffle
from typing import (
    Final,
    Optional,
    TypeVar,
)

import pytz
from faker.providers import BaseProvider
from hypothesis import strategies as st
from jsonschema import ValidationError, validate
from wrapt import ObjectProxy

import js_regex

"""
TODO: rename as OpenAPI


string (this includes dates and files) TODO: generate picture files, see faker.image_url
number
integer
boolean
array
object

OpenAPI schemas can also use the following keywords that are not part of JSON
Schema:

deprecated
discriminator
example
externalDocs
nullable
readOnly
writeOnly
xml
"""


class NoExampleFoundError(Exception):
    pass


class UnsatisfiableConstraintsError(ValueError):
    pass


class NotSet(Enum):
    SENTINEL = auto()


class NumberMode(Enum):
    FLOAT = auto()
    INTEGER = auto()


class LengthType(Enum):
    FIXED = auto()
    VARIABLE_SINGULAR = auto()
    VARIABLE_RANGE = auto()
    UNCONSTRAINED = auto()


class TypeName(StrEnum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"
    ONE_OF = "oneOf"  # data must be valid against only one of the sub-schemas
    ANY_OF = "anyOf"  # data must be valid against any one of the sub-schemas
    ALL_OF = "allOf"  # data must be valid against all of the sub-schemas
    ANY = "any"  # i.e. `JsonT`
    NOT = "not"  # "any, except ___"


FLAT_TYPES = {
    TypeName.STRING,
    TypeName.NUMBER,
    TypeName.INTEGER,
    TypeName.BOOLEAN,
    TypeName.NULL,
}

NESTED_TYPES = {
    TypeName.ARRAY,
    TypeName.OBJECT,
}

BASIC_TYPES = FLAT_TYPES | NESTED_TYPES

COMPOUND_TYPES = {
    TypeName.ONE_OF,
    TypeName.ANY_OF,
    TypeName.ALL_OF,
    TypeName.NOT,
}


StrT = str | bytes

JsonT = StrT | int | float | bool | None | list["JsonT"] | dict[str, "JsonT"]

SchemaT = dict[str, JsonT]

_NO_TYPE = "__no_type__"


def type_getter(schema):
    return schema.get("type", _NO_TYPE)


@dataclass
class StringFormat:
    length_type: LengthType
    lengths: Iterable[int] | range | None = None
    return_type: StrT = str

    def validate_constraints(self, min_length: int, max_length: int | None) -> bool:
        assert min_length >= 0
        assert max_length is None or max_length >= 0
        # VARIABLE_SINGULAR and VARIABLE_RANGE mean we can specify the length
        # to be generated, but possible values may still be constrained
        if self.lengths:
            # example will be one of several fixed lengths
            if isinstance(self.lengths, range):
                assert self.lengths.start >= 0
                assert self.lengths.stop > 0
                assert self.lengths.step > 0
                if self.length_type is not LengthType.VARIABLE_RANGE:
                    return all(
                        len_ >= min_length and (max_length is None or len_ <= max_length)
                        for len_ in self.lengths
                    )
                start = self.lengths.start
                stop = self.lengths.stop
                step = self.lengths.step
                if min_length <= start:
                    nearest_to_min = start
                else:
                    nearest_to_min = start + (((min_length - start + step - 1) // step) * step)
                if nearest_to_min >= stop:
                    return False
                return not (max_length is not None and nearest_to_min > max_length)
            else:
                return all(
                    len_ >= min_length and (max_length is None or len_ <= max_length)
                    for len_ in self.lengths
                )
        else:
            # UNCONSTRAINED means examples can be any length, we will have
            # to brute-force search for a matching example
            return not (self.length_type is LengthType.UNCONSTRAINED and max_length == 0)


class JsonVal(ObjectProxy):
    """Hashable JSON value wrapper -- at last, a dict in a set."""

    def __init__(self, val: JsonT):
        super().__init__(val)
        self._self_hash = hash(json.dumps(val))

    def __hash__(self) -> int:
        return self._self_hash


EnumVal = TypeVar("EnumVal", bound=JsonT)


class JsonEnum(frozenset[JsonVal]):
    def __new__(cls, values: Iterable[EnumVal]) -> "JsonEnum":
        return super().__new__(cls, (JsonVal(val) for val in values))


def nullable_or_enum(f):
    """
    Intercept `nullable` and `enum` before type-specific logic.

    Decorator for `JSONSchemaProvider.<type>_from_schema` methods to
    handle `nullable` and `enum` properties which are kind of
    orthogonal to the rest of the types.
    """

    @wraps(f)
    def wrapped(self, schema: SchemaT, *args, **kwargs):
        if schema.get("nullable") and self.generator.random_int(0, 1):
            return None
        if "enum" in schema:
            return self.jsonschema_enum(JsonEnum(schema["enum"]))
        return f(self, schema, *args, **kwargs)

    return wrapped


@dataclass
class Context:
    _depth: int = 0
    max_depth: Final[int] = 5
    max_search: Final[int] = 500
    default_collection_max: Final[int] = 50
    default_property_schema = {"type": "string", "format": "user_name"}
    _root_schema: SchemaT | None = None
    _ref_stack: list = None  # type: ignore[assignment]

    def __post_init__(self):
        if self._ref_stack is None:
            self._ref_stack = []


L = TypeVar("L", bound=JsonT)
R = TypeVar("R", bound=JsonT)
T = TypeVar("T")


def _merge_constraint(
    left: L | None,
    right: R | None,
    resolver: Callable[[L, R], L | R],
) -> JsonT | None:
    if left is not None:
        if right is not None:
            return resolver(left, right)
        else:
            return left
    else:
        if right is not None:
            return right
        else:
            return None


def _resolve_equal_or_error(left: L, right: JsonT) -> L:
    if left == right:
        return left
    else:
        raise UnsatisfiableConstraintsError


def _resolve_multiple_of(left: Number, right: Number) -> Number:
    if left % right == 0:
        return left
    elif right % left == 0:
        return right
    else:
        raise UnsatisfiableConstraintsError


def _resolve_properties(left: dict[str, SchemaT], right: dict[str, SchemaT]) -> dict[str, SchemaT]:
    properties = left.copy()
    for name, schema in right.items():
        if name in left:
            properties[name] = _merge_schemas(left[name], schema)
        else:
            properties[name] = schema
    return properties


def _resolve_additional_properties(left: bool | SchemaT, right: bool | SchemaT) -> bool | SchemaT:
    """Merge additionalProperties: False is strictest, schema beats True."""
    if left is False or right is False:
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return _merge_schemas(left, right)
    if isinstance(left, dict):
        return left
    if isinstance(right, dict):
        return right
    # both are True
    return True


def _resolve_dependent_required(
    left: dict[str, list[str]], right: dict[str, list[str]]
) -> dict[str, list[str]]:
    merged = left.copy()
    for key, deps in right.items():
        if key in merged:
            merged[key] = list(set(merged[key]) | set(deps))
        else:
            merged[key] = deps
    return merged


def _resolve_dependent_schemas(
    left: dict[str, SchemaT], right: dict[str, SchemaT]
) -> dict[str, SchemaT]:
    merged = left.copy()
    for key, schema in right.items():
        if key in merged:
            merged[key] = _merge_schemas(merged[key], schema)
        else:
            merged[key] = schema
    return merged


def _merge_schemas(left: SchemaT, right: SchemaT) -> SchemaT:
    left_type = left.get("type")
    right_type = right.get("type")
    if left_type is None and right_type is None:
        # Neither schema has a type — just shallow-merge keys.
        merged = left.copy()
        merged.update(right)
        return merged
    if left_type is None:
        left = {**left, "type": right_type}
    elif right_type is None:
        right = {**right, "type": left_type}
    elif left_type != right_type:
        raise UnsatisfiableConstraintsError(
            f"Cannot merge schemas with different types: {left_type} vs {right_type}"
        )
    type_ = TypeName(left["type"])
    attr_map = TYPE_ATTR_MERGE_RESOLVERS[type_]
    merged = left.copy()
    for attr, resolver in attr_map.items():
        this_left = left.get(attr)
        this_right = right.get(attr)
        try:
            val = _merge_constraint(this_left, this_right, resolver)
        except UnsatisfiableConstraintsError as e:
            raise UnsatisfiableConstraintsError(
                "Cannot merge incompatible constraints "
                f"type: {type_}, "
                f"{attr}: {this_left} & {attr}: {this_right}"
            ) from e
        if val is not None:
            merged[attr] = val
    return merged


_numeric_attr_merge_funcs = {
    "minimum": max,
    "maximum": min,
    "exclusiveMin": operator.or_,
    "exclusiveMax": operator.or_,
    "exclusiveMinimum": max,
    "exclusiveMaximum": min,
    "multipleOf": _resolve_multiple_of,
}


def _resolve_prefix_items(left: list[SchemaT], right: list[SchemaT]) -> list[SchemaT]:
    """Merge prefixItems: merge pairwise, keep longer."""
    result = []
    for i in range(max(len(left), len(right))):
        if i < len(left) and i < len(right):
            result.append(_merge_schemas(left[i], right[i]))
        elif i < len(left):
            result.append(left[i])
        else:
            result.append(right[i])
    return result


TYPE_ATTR_MERGE_RESOLVERS = {
    TypeName.ARRAY: {
        "items": _merge_schemas,  # NOTE: relies on OpenAPI homogenous arrays
        "prefixItems": _resolve_prefix_items,
        "additionalItems": _resolve_additional_properties,  # same semantics
        "unevaluatedItems": _resolve_additional_properties,
        "contains": _merge_schemas,
        "minContains": max,
        "maxContains": min,
        "minItems": max,
        "maxItems": min,
        "uniqueItems": operator.or_,
    },
    TypeName.OBJECT: {
        "properties": _resolve_properties,
        "patternProperties": _resolve_properties,
        "propertyNames": _merge_schemas,
        "required": lambda left, right: list(set(left) | set(right)),
        "additionalProperties": _resolve_additional_properties,
        "minProperties": max,
        "maxProperties": min,
        "dependentRequired": _resolve_dependent_required,
        "dependentSchemas": _resolve_dependent_schemas,
        "unevaluatedProperties": _resolve_additional_properties,
    },
    TypeName.NUMBER: _numeric_attr_merge_funcs,
    TypeName.INTEGER: _numeric_attr_merge_funcs,
    TypeName.STRING: {
        "minLength": max,
        "maxLength": min,
        # (I can't think of a way to combine arbitrary regexes)
        "pattern": _resolve_equal_or_error,
        # (`format`s are likely to be mutually exclusive)
        "format": _resolve_equal_or_error,
        "contentEncoding": _resolve_equal_or_error,
        "contentMediaType": _resolve_equal_or_error,
    },
}


def compound_schema(schemas: Iterable[SchemaT]) -> SchemaT:
    return reduce(_merge_schemas, schemas)


def kwargs_from_schema_factory(method):
    arg_names = inspect.getfullargspec(method).args
    snake_case = r"_([a-z])"

    def to_camel_case(match: re.Match) -> str:
        return f"{match.groups()[0].upper()}"

    getters = {
        arg: operator.itemgetter(re.sub(snake_case, to_camel_case, arg).rstrip("_"))
        for arg in arg_names
        if arg != "self"
    }

    def kwargs_from_schema(schema: SchemaT) -> dict[str, JsonT]:
        kwargs = {}
        for arg, getter in getters.items():
            with contextlib.suppress(KeyError):
                kwargs[arg] = getter(schema)
        return kwargs

    return kwargs_from_schema


class JSONSchemaProviderMetaclass(type):
    def __new__(cls, name, bases, attrs):
        cls = type.__new__(cls, name, bases, attrs)
        # attach pre-generated kwargs-from-schema getters to the
        # `jsonschema_string` etc methods used by
        # `_jsonschema_basic_type_from_schema`
        for type_ in BASIC_TYPES:
            method = getattr(cls, cls.BASE_METHOD_MAP[type_])
            method.kwargs_from_schema = kwargs_from_schema_factory(method)
        return cls


class JSONSchemaProvider(BaseProvider, metaclass=JSONSchemaProviderMetaclass):
    STRING_FORMATS = {
        # defined in OpenAPI spec:
        # ----------
        "date": StringFormat(
            length_type=LengthType.FIXED,
            # 2009-05-08
            lengths=[10],
        ),
        "date-time": StringFormat(
            length_type=LengthType.FIXED,
            # 2009-05-08T19:12:48+01:56
            lengths=[25],
        ),
        "password": StringFormat(
            length_type=LengthType.VARIABLE_SINGULAR,
        ),
        "byte": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            return_type=bytes,
            # returned length is a multiple of 4 (default maxLength is 255)
            lengths=range(0, 256, 4),
        ),
        "binary": StringFormat(
            length_type=LengthType.VARIABLE_SINGULAR,
            return_type=bytes,
        ),
        # mentioned in OpenAPI spec as examples:
        # ----------
        "email": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(3, 255),
        ),
        "uuid": StringFormat(
            length_type=LengthType.FIXED,
            # a1a88cbb-7634-4504-a454-7bb8aec36a1e
            lengths=[36],
        ),
        "uri": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(10, 2084),
        ),
        "hostname": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 254),
        ),
        "ipv4": StringFormat(
            length_type=LengthType.FIXED,
            # 0.0.0.0 -> 255.255.255.255
            lengths=range(7, 16),
        ),
        "ipv6": StringFormat(
            length_type=LengthType.FIXED,
            # :: -> 1000:1000:1000:1000:1000:1abc:1007:1def
            lengths=range(2, 40),
        ),
        # JSON Schema draft-07+ formats:
        "time": StringFormat(
            length_type=LengthType.FIXED,
            # 17:32:28+00:00 -> 17:32:28+05:30
            lengths=range(8, 15),
        ),
        "duration": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(3, 33),
        ),
        "uri-reference": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 2084),
        ),
        "uri-template": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(10, 2084),
        ),
        "iri": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(10, 2084),
        ),
        "iri-reference": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 2084),
        ),
        "idn-email": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(3, 255),
        ),
        "idn-hostname": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 254),
        ),
        "json-pointer": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 256),
        ),
        "relative-json-pointer": StringFormat(
            length_type=LengthType.VARIABLE_RANGE,
            lengths=range(1, 256),
        ),
        "regex": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
    }

    FLOAT_OFFSET: Final = float("0.{}1".format("0" * (sys.float_info.dig - 2)))

    BASE_METHOD_MAP = {type_name: f"jsonschema_{type_name.value.lower()}" for type_name in TypeName}

    _context: Optional["Context"] = None

    def jsonschema_enum(self, enum: JsonEnum) -> JsonT:
        # enum contains actual values, not sub-schema
        return self.generator.random_element(enum).__wrapped__

    def _format_date(self) -> str:
        return self.generator.date()

    def _format_date_time(self, tzinfo=None) -> str:
        if not tzinfo:
            tzinfo = pytz.timezone(self.generator.timezone())
        return self.generator.iso8601(tzinfo=tzinfo)

    def _format_password(self, length: int) -> str:
        if length < 4:
            # Faker's password() requires >= 4 chars for character-class guarantees
            return self.generator.pystr(min_chars=length, max_chars=length)
        return self.generator.password(length=length)

    def _format_byte(self, min_length: int, max_length: int) -> bytes:
        """
        Generate base64-encoded bytes.

        Base64 values always have length which is a multiple of 4
        and the encoded value will be 4/3 * longer than the original.
        """
        valid_encoded_lengths = [
            length for length in range(min_length, max_length + 1) if length % 4 == 0
        ]
        if not valid_encoded_lengths:
            raise UnsatisfiableConstraintsError(
                f"Constraints minLength: {min_length}, maxLength: "
                f"{max_length} are incompatible with format: byte."
            )

        encoded_length = self.generator.random_element(valid_encoded_lengths)
        if encoded_length == 0:
            return b""

        chunk_count = encoded_length // 4
        min_raw_length = max(1, (chunk_count * 3) - 2)
        max_raw_length = chunk_count * 3
        raw_length = self._safe_random_int(min_raw_length, max_raw_length + 1)
        return b64encode(self.generator.binary(length=raw_length))

    def _encode_base32(self, min_length: int, max_length: int) -> bytes:
        """Generate base32-encoded bytes (RFC 4648 §6). Encoded length is a multiple of 8."""
        valid_encoded_lengths = [
            length for length in range(min_length, max_length + 1) if length % 8 == 0
        ]
        if not valid_encoded_lengths:
            raise UnsatisfiableConstraintsError(
                f"Constraints minLength: {min_length}, maxLength: "
                f"{max_length} are incompatible with contentEncoding: base32."
            )
        encoded_length = self.generator.random_element(valid_encoded_lengths)
        if encoded_length == 0:
            return b""
        chunk_count = encoded_length // 8
        min_raw_length = max(1, chunk_count * 5 - 4)
        max_raw_length = chunk_count * 5
        raw_length = self._safe_random_int(min_raw_length, max_raw_length + 1)
        return b32encode(self.generator.binary(length=raw_length))

    def _encode_base16(self, min_length: int, max_length: int) -> bytes:
        """Generate base16-encoded bytes (RFC 4648 §8). Encoded length is always even."""
        valid_encoded_lengths = [
            length for length in range(min_length, max_length + 1) if length % 2 == 0
        ]
        if not valid_encoded_lengths:
            raise UnsatisfiableConstraintsError(
                f"Constraints minLength: {min_length}, maxLength: "
                f"{max_length} are incompatible with contentEncoding: base16."
            )
        encoded_length = self.generator.random_element(valid_encoded_lengths)
        if encoded_length == 0:
            return b""
        raw_length = encoded_length // 2
        return b16encode(self.generator.binary(length=raw_length))

    def _encode_7bit(self, min_length: int, max_length: int) -> bytes:
        """Generate 7bit-encoded bytes (RFC 2045 §2.7). Printable ASCII, no NUL, no bare CR/LF."""
        n = self._safe_random_int(min_length, max_length + 1)
        if n == 0:
            return b""
        octets = list(range(0x20, 0x7F))  # 0x20–0x7E inclusive
        return bytes(self.generator.random_elements(elements=octets, length=n, unique=False))

    def _encode_8bit(self, min_length: int, max_length: int) -> bytes:
        """
        Generate 8bit-encoded bytes (RFC 2045 §2.8).

        Allows octets >127, no NUL, no bare CR/LF.
        """
        n = self._safe_random_int(min_length, max_length + 1)
        if n == 0:
            return b""
        octets = [*range(0x20, 0x7F), *range(0x80, 0x100)]
        return bytes(self.generator.random_elements(elements=octets, length=n, unique=False))

    def _encode_binary(self, min_length: int, max_length: int) -> bytes:
        """Generate binary-encoded bytes (RFC 2045 §2.9). Any octet sequence."""
        n = self._safe_random_int(min_length, max_length + 1)
        return self.generator.binary(length=n)

    # Printable ASCII chars safe for QP input: 0x21–0x7E excluding '=' (0x3D)
    _QP_INPUT_CHARS: Final[list[int]] = [c for c in range(0x21, 0x7F) if c != 0x3D]

    def _encode_quoted_printable(self, min_length: int, max_length: int) -> bytes:
        r"""
        Generate quoted-printable-encoded bytes (RFC 2045 §6.7).

        Input uses only printable ASCII excluding '=', so chars encode 1:1.
        The only expansion is soft line breaks (=\r\n every 76 chars, ~4%
        overhead). A retry loop adjusts raw input length until the encoded
        output falls within [min_length, max_length].
        """
        # Estimate: encoded ≈ raw + (raw // 76) * 3
        # Start below max to account for line-break overhead
        target = (min_length + max_length) // 2
        raw_length = max(0, int(target * 0.95))
        for _ in range(self.context.max_search):
            if raw_length == 0:
                encoded = b""
            else:
                raw = bytes(
                    self.generator.random_elements(
                        elements=self._QP_INPUT_CHARS, length=raw_length, unique=False
                    )
                )
                encoded = quopri.encodestring(raw, quotetabs=True)
            encoded_len = len(encoded)
            if min_length <= encoded_len <= max_length:
                return encoded
            # Adjust: if too short grow, if too long shrink
            if encoded_len < min_length:
                raw_length += max(1, (min_length - encoded_len))
            else:
                raw_length = max(0, raw_length - max(1, (encoded_len - max_length)))
        raise UnsatisfiableConstraintsError(
            f"Constraints minLength: {min_length}, maxLength: "
            f"{max_length} are incompatible with contentEncoding: quoted-printable."
        )

    def _format_binary(self, length: int) -> bytes:
        return self.generator.binary(length=length)

    def _format_email(self, min_length: int = 0, max_length: int = 254) -> str:
        """
        Length-aware email: vary local-part and domain to hit target.

        RFC 5321: local part max 64, total max 254, min ~3 (``a@b``).
        """
        _LOCAL_MAX = 64

        # Work out how long the domain needs to be.
        # min total = local + "@" + domain, with local capped at 64
        # So domain must be >= min_length - 64 - 1
        domain_min_len = max(1, min_length - _LOCAL_MAX - 1)

        # And domain must be short enough: max total = local(>=1) + "@" + domain
        domain_max_len = max(1, max_length - 2)  # at least 1 char local + "@"

        domain = self.generator.domain_name()

        # If domain is too short, add subdomains
        while len(domain) < domain_min_len:
            gap = domain_min_len - len(domain) - 1  # -1 for "."
            if gap < 1:
                break
            label_len = min(gap, self.generator.random_int(2, 12))
            label = self.generator.pystr(min_chars=label_len, max_chars=label_len)
            domain = f"{label}.{domain}"

        # If domain is too long, generate a shorter one
        if len(domain) > domain_max_len:
            tld = self.generator.tld()
            if len(tld) + 1 > domain_max_len:
                domain = tld[: max(1, domain_max_len)]
            else:
                label_budget = domain_max_len - len(tld) - 1
                label = self.generator.pystr(
                    min_chars=max(1, label_budget),
                    max_chars=max(1, label_budget),
                )
                domain = f"{label}.{tld}"

        suffix_len = 1 + len(domain)  # "@" + domain
        local_min = max(1, min_length - suffix_len)
        local_max = min(_LOCAL_MAX, max_length - suffix_len)
        if local_max < 1:
            local_max = 1
        if local_min > local_max:
            local_min = local_max
        local = self.generator.pystr(min_chars=local_min, max_chars=local_max)
        return f"{local}@{domain}"

    def _format_uuid(self) -> str:
        return self.generator.uuid4()

    def _format_uri(self, min_length: int = 0, max_length: int = 2083) -> str:
        """Length-aware URI: vary path length to hit target."""
        scheme = self.generator.random_element(["http", "https"])
        host = self.generator.domain_name()
        base = f"{scheme}://{host}"
        if len(base) >= max_length:
            return base[:max_length]
        remaining = max(0, min_length - len(base) - 1)  # -1 for "/"
        path_max = max_length - len(base) - 1
        if remaining > 0 and path_max > 0:
            path = self.generator.pystr(
                min_chars=min(remaining, path_max),
                max_chars=min(path_max, max(remaining, path_max)),
            )
            return f"{base}/{path}"
        elif path_max > 0:
            path_len = self.generator.random_int(1, min(path_max, 20))
            path = self.generator.pystr(min_chars=path_len, max_chars=path_len)
            return f"{base}/{path}"
        return base

    def _format_hostname(self, min_length: int = 0, max_length: int = 253) -> str:
        """
        Length-aware hostname: vary subdomain labels to hit target.

        RFC 1123: max 253 chars, each label max 63 chars.
        """
        tld = self.generator.tld()
        base_domain = self.generator.pystr(min_chars=2, max_chars=min(10, 63))
        hostname = f"{base_domain}.{tld}"
        # Add subdomain labels to reach min_length
        while len(hostname) < min_length:
            # Need this many more chars; each label costs label_len + 1 (for ".")
            gap = min_length - len(hostname)
            # Label must be at least 1 char; the "." adds 1 more
            label_len = min(gap - 1, 63)  # -1 accounts for the "." separator
            if label_len < 1:
                # Gap is 1 char — can't add a label (need at least "x.")
                # Extend the base domain instead
                hostname = self.generator.pystr(min_chars=1, max_chars=1) + hostname
                break
            label_max = min(label_len, self.generator.random_int(2, min(12, 63)))
            label = self.generator.pystr(min_chars=label_max, max_chars=label_max)
            hostname = f"{label}.{hostname}"
        return hostname[:max_length]

    def _format_ipv4(self) -> str:
        return self.generator.ipv4()

    def _format_ipv6(self) -> str:
        return self.generator.ipv6()

    def _format_time(self) -> str:
        """RFC 3339 §5.6 full-time, e.g. '17:32:28+00:00'."""
        t = self.generator.time(pattern="%H:%M:%S")
        tz = pytz.timezone(self.generator.timezone())
        offset = tz.utcoffset(datetime.datetime.now())
        if offset is None or offset == datetime.timedelta(0):
            return f"{t}Z"
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{t}{sign}{hours:02d}:{minutes:02d}"

    def _format_duration(self, min_length: int = 0, max_length: int = 32) -> str:
        """
        ISO 8601 / RFC 3339 Appendix A duration, e.g. 'P3Y6M4DT12H30M5S'.

        Length-aware: include/omit components to hit target length.
        Min ``P0D`` (3 chars). Normal generation uses realistic calendar
        values (max 20 chars). Fallback inflates component values up to
        4 digits for longer targets (max 32 chars).
        """
        # All possible components with their (suffix, max_value) pairs
        date_components = [
            ("Y", 10),  # years:   "0Y".."10Y"   = 2-3 chars
            ("M", 11),  # months:  "0M".."11M"   = 2-3 chars
            ("D", 30),  # days:    "0D".."30D"   = 2-3 chars
        ]
        time_components = [
            ("H", 23),  # hours:   "0H".."23H"   = 2-3 chars
            ("M", 59),  # minutes: "0M".."59M"   = 2-3 chars
            ("S", 59),  # seconds: "0S".."59S"   = 2-3 chars
        ]

        def build() -> str:
            parts = []
            for suffix, max_val in date_components:
                if self.generator.random_int(0, 1):
                    val = self.generator.random_int(0, max_val)
                    parts.append(f"{val}{suffix}")
            time_parts = []
            for suffix, max_val in time_components:
                if self.generator.random_int(0, 1):
                    val = self.generator.random_int(0, max_val)
                    time_parts.append(f"{val}{suffix}")
            date_part = "".join(parts)
            time_part = "T" + "".join(time_parts) if time_parts else ""
            result = f"P{date_part}{time_part}"
            if result == "P":
                result = "PT0S"
            return result

        # Try a few times to hit the length range
        for _ in range(20):
            result = build()
            if min_length <= len(result) <= max_length:
                return result

        # Fallback: include all components, inflating value ranges until
        # min_length is reached (RFC 3339 allows 1*DIGIT per component)
        if min_length > 3:
            max_multiplier = 1
            for _ in range(5):
                parts = []
                for suffix, max_val in date_components:
                    hi = max(max_val, 10) * max_multiplier
                    parts.append(f"{self.generator.random_int(1, hi)}{suffix}")
                time_parts = []
                for suffix, max_val in time_components:
                    hi = max(max_val, 10) * max_multiplier
                    time_parts.append(f"{self.generator.random_int(1, hi)}{suffix}")
                result = "P" + "".join(parts) + "T" + "".join(time_parts)
                if len(result) >= min_length:
                    return result[:max_length] if len(result) > max_length else result
                max_multiplier *= 10
            return result[:max_length] if len(result) > max_length else result
        # Minimal
        return "PT0S"[:max_length]

    def _format_uri_reference(self, min_length: int = 0, max_length: int = 2083) -> str:
        """URI-reference: either a URI or a relative-reference."""
        if min_length > 10 or self.generator.random_int(0, 1):
            return self._format_uri(min_length=min_length, max_length=max_length)
        # relative reference — vary path length
        budget = max_length - 1  # leading "/"
        path_min = max(1, min_length - 1)
        path_len = self.generator.random_int(path_min, min(budget, max(path_min, 20)))
        path = self.generator.pystr(min_chars=path_len, max_chars=path_len)
        return f"/{path}"

    def _format_uri_template(self, min_length: int = 0, max_length: int = 2083) -> str:
        """RFC 6570 URI Template, e.g. 'https://example.com/{id}'."""
        # Reserve space for template variable suffix "{xx}" = 4 chars min
        var_len = self.generator.random_int(2, 8)
        suffix_len = var_len + 2  # { + var + }
        uri = self._format_uri(
            min_length=max(0, min_length - suffix_len),
            max_length=max_length - suffix_len,
        )
        var_name = self.generator.pystr(min_chars=var_len, max_chars=var_len)
        return f"{uri}{{{var_name}}}"

    def _format_iri(self, min_length: int = 0, max_length: int = 2083) -> str:
        """IRI (RFC 3987). ASCII URIs are valid IRIs."""
        return self._format_uri(min_length=min_length, max_length=max_length)

    def _format_iri_reference(self, min_length: int = 0, max_length: int = 2083) -> str:
        """IRI-reference (RFC 3987). Reuse uri-reference logic."""
        return self._format_uri_reference(min_length=min_length, max_length=max_length)

    def _format_idn_email(self, min_length: int = 0, max_length: int = 254) -> str:
        """Internationalized email (RFC 6531). ASCII is a valid subset."""
        return self._format_email(min_length=min_length, max_length=max_length)

    def _format_idn_hostname(self, min_length: int = 0, max_length: int = 253) -> str:
        """Internationalized hostname (RFC 5890). ASCII is a valid subset."""
        return self._format_hostname(min_length=min_length, max_length=max_length)

    def _format_json_pointer(self, min_length: int = 0, max_length: int = 255) -> str:
        """RFC 6901 JSON Pointer, e.g. '/foo/bar/0'."""
        # Build segments to fill the target length
        result = ""
        target = self.generator.random_int(max(1, min_length), max_length)
        while len(result) < target:
            remaining = target - len(result) - 1  # -1 for "/"
            if remaining < 1:
                result += "/"
                break
            seg_len = min(remaining, self.generator.random_int(1, 8))
            seg = self.generator.pystr(min_chars=seg_len, max_chars=seg_len)
            result += "/" + seg
        return result[:max_length]

    def _format_relative_json_pointer(self, min_length: int = 0, max_length: int = 255) -> str:
        """Relative JSON Pointer, e.g. '1/foo/bar'."""
        prefix = str(self.generator.random_int(0, 9))
        if max_length <= 2 or (min_length <= 2 and self.generator.random_int(0, 1)):
            return (prefix + "#")[:max_length]
        # Build path segments to fill target length
        result = prefix
        target = self.generator.random_int(max(len(prefix), min_length), max_length)
        while len(result) < target:
            remaining = target - len(result) - 1  # -1 for "/"
            if remaining < 1:
                result += "/"
                break
            seg_len = min(remaining, self.generator.random_int(1, 8))
            seg = self.generator.pystr(min_chars=seg_len, max_chars=seg_len)
            result += "/" + seg
        return result[:max_length]

    def _format_regex(self) -> str:
        """A valid regular expression."""
        patterns = [
            r"^[a-z]+$",
            r"\d{2,4}-\d{2}-\d{2}",
            r"[A-Z][a-z]*",
            r"^\S+@\S+\.\S+$",
            r"(foo|bar|baz)",
            r"[0-9a-fA-F]+",
            r".{1,10}",
        ]
        return self.generator.random_element(patterns)

    def jsonschema_string(
        self,
        min_length: int = 0,
        max_length: int | None = None,
        pattern: str | None = None,
        format_: str | None = None,
        content_encoding: str | None = None,
        content_media_type: str | None = None,
    ) -> StrT:
        """
        Generate a fake string value.

        Args:
            min_length: we will try to respect this for all strategies
            max_length: we will try to respect this for all strategies
            pattern: "The regular expression syntax used is from JavaScript
                (more specifically, ECMA 262). Without ^...$, pattern works as
                a partial match, that is, matches any string that contains the
                specified regular expression."
                ...but obviously we just use python built-in regex
            format_: OpenAPI mandates some specific formats, others are allowed
                without having a formal meaning in the spec. We will attempt to
                match the format to a faker method (since many of them coincide
                and it seems useful behaviour).
            content_encoding: draft 2019-09+ content encoding (e.g. "base64").
            content_media_type: draft 2019-09+ media type hint.

        Raises:
            NoExampleFoundError
            UnsatifiableConstraintsError
            ValueError

        String length can be restricted using `min_length` and `max_length`.

        An optional `format` modifier serves as a hint at the contents and
        format of the string. OpenAPI defines the following built-in string
        formats:
            date: full-date notation as defined by RFC 3339, section 5.6, for
                example, `2017-07-21`
            date-time: the date-time notation as defined by RFC 3339, section
                5.6, for example, `2017-07-21T17:32:28Z`
            password: a hint to UIs to mask the input
            byte: base64-encoded characters, for example
                `U3dhZ2dlciByb2Nrcw==`
                NOTE: JSONSchema spec defines this as `contentEncoding: base64`
            binary: binary data, used to describe files (see Files below)
                probably only applicable to non-JSON payloads

        However, `format` is an open value, so you can use any formats, even
        those not defined by the OpenAPI Specification, such as:
            email
            uuid
            uri
            hostname
            ipv4
            ipv6
            and others

        NOTE: for our purposes we will treat `format` as the name of a faker
        and ensure that we have coverage for all those mentioned above.

        The `pattern` keyword lets you define a regular expression template for
        the string value.

        NOTE: obviously it is possible to specify `min_length`, `max_length`
        and `pattern` such that no valid value exists.

        NOTE: we treat `format` and `pattern` as exclusive (with `pattern`
        taking precedence if defined) since for most values of `format` the
        regex validation would either be redundant or we have no strategy short
        of brute force that could generate examples matching both constraints.
        """
        if min_length < 0:
            raise ValueError("minLength must be >= 0")
        if max_length is not None and max_length < min_length:
            raise ValueError("maxLength must be >= minLength")

        # Handle contentEncoding (draft 2019-09+)
        if content_encoding is not None:
            _max = max_length if max_length is not None else 255
            match content_encoding.lower():
                case "base64":
                    return self._format_byte(min_length=min_length, max_length=_max)
                case "base32":
                    return self._encode_base32(min_length=min_length, max_length=_max)
                case "base16":
                    return self._encode_base16(min_length=min_length, max_length=_max)
                case "7bit":
                    return self._encode_7bit(min_length=min_length, max_length=_max)
                case "8bit":
                    return self._encode_8bit(min_length=min_length, max_length=_max)
                case "binary":
                    return self._encode_binary(min_length=min_length, max_length=_max)
                case "quoted-printable":
                    return self._encode_quoted_printable(min_length=min_length, max_length=_max)
                case _:
                    pass  # Unknown encoding: fall through to normal string generation

        def is_valid(val) -> bool:
            if len(val) < min_length:
                return False
            return not (max_length is not None and len(val) > max_length)

        def search(generator: Callable[..., T]) -> T:
            for _ in range(self.context.max_search):
                example = generator()
                if is_valid(example):
                    break
            else:
                raise NoExampleFoundError
            return example

        if pattern is not None:
            # (returns early)
            # NOTE: `format` is ignored if `pattern` is given
            # Validate as JS regex (raises NotJavascriptRegex for incompatible patterns)
            js_regex.compile(pattern)

            # JSON Schema `pattern` uses partial match (re.search), so for
            # patterns without an end anchor we can pad short results with
            # random characters to meet minLength.
            has_end_anchor = bool(
                re.search(r"(?<!\\)\$\Z", pattern) or re.search(r"(?<!\\)\\[Zz]\Z", pattern)
            )
            can_pad = not has_end_anchor and min_length > 0

            # Use from_regex strategy with .example() for varied output;
            # hypothesis.find() shrinks to minimal examples which is not
            # suitable for data generation (always produces same value).
            regex_st = st.from_regex(re.compile(pattern))
            if min_length > 0:
                regex_st = regex_st.filter(lambda s: len(s) >= min_length)
            if max_length is not None:
                regex_st = regex_st.filter(lambda s: len(s) <= max_length)
            compiled = re.compile(pattern)
            for _ in range(self.context.max_search):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        example = regex_st.example()
                except Exception:  # noqa: BLE001 — Hypothesis .example() can raise many internal errors
                    break
                if is_valid(example):
                    return example
                # If too short and pattern allows padding, extend
                if can_pad and len(example) < min_length:
                    padding_needed = min_length - len(example)
                    if max_length is not None:
                        pad_max = max_length - len(example)
                    else:
                        pad_max = padding_needed
                    if pad_max >= padding_needed:
                        padding = self.generator.pystr(
                            min_chars=padding_needed,
                            max_chars=pad_max,
                        )
                        padded = example + padding
                        if compiled.search(padded) and is_valid(padded):
                            return padded
            raise UnsatisfiableConstraintsError(
                f"Unable to generate any random value that matches "
                f"pattern: /{pattern}/ and minLength: {min_length}, "
                f"maxLength: {max_length} after {self.context.max_search} attempts."
            )
        elif format_ is not None:
            # (returns early)
            # NOTE: we will 'fall through' if no matching faker can be found
            try:
                format_type = self.STRING_FORMATS[format_]
            except KeyError:
                try:
                    faker_method = getattr(self.generator, format_)
                except AttributeError:
                    pass
                else:
                    try:
                        return search(lambda: str(faker_method()))
                    except NoExampleFoundError as e:
                        raise UnsatisfiableConstraintsError(
                            f"Unable to generate any random value that matches "
                            f"format: {format_} and minLength: {min_length}, "
                            f"maxLength: {max_length} after "
                            f"{self.context.max_search} attempts."
                        ) from e
            else:
                if not format_type.validate_constraints(min_length, max_length):
                    raise UnsatisfiableConstraintsError(
                        f"Constraints minLength: {min_length}, maxLength: "
                        f"{max_length} are incompatible with format: {format_}."
                    )

                method = getattr(self, "_format_{}".format(format_.replace("-", "_")))
                if format_type.length_type is LengthType.FIXED:
                    return method()
                elif format_type.length_type is LengthType.VARIABLE_SINGULAR:
                    return method(length=self._safe_random_int(min_length, max_length))
                elif format_type.length_type is LengthType.VARIABLE_RANGE:
                    return method(
                        min_length=min_length,
                        max_length=max_length if max_length is not None else 255,
                    )
                elif format_type.length_type is LengthType.UNCONSTRAINED:
                    try:
                        return search(method)
                    except NoExampleFoundError as e:
                        raise UnsatisfiableConstraintsError(
                            f"Unable to generate any random value that matches "
                            f"format: {format_} and minLength: {min_length}, "
                            f"maxLength: {max_length} after "
                            f"{self.context.max_search} attempts."
                        ) from e

        if max_length is None or (max_length and max_length > 20):
            # (returns early)
            # use the "lorem ipsum" provider
            # (...has a min length generatable of 5 chars)
            generator = partial(
                self.generator.text,
                max_nb_chars=max_length if max_length is not None else 255,
            )
            # NOTE: we will 'fall through' if no valid example can be found
            try:
                return search(generator)
            except NoExampleFoundError:
                pass

        return self.generator.pystr(
            min_chars=min_length,
            max_chars=max_length if max_length is not None else 255,
        )

    def better_pyfloat(self, min_value: float | None, max_value: float | None) -> float:
        """`faker.pyfloat` only supports int for min and max value."""
        if None not in (min_value, max_value) and min_value > max_value:
            raise ValueError("min_value cannot be greater than max_value")
        if None not in (min_value, max_value) and min_value == max_value:
            # `faker.pyfloat` doesn't allow this but I don't see why not
            return float(min_value)

        if min_value is None:
            min_value = float("-" + ("9" * sys.float_info.dig))
        if max_value is None:
            max_value = float("9" * sys.float_info.dig)

        return self.generator.random.uniform(min_value, max_value)

    def _safe_random_int(self, min_value: int | None, max_value: int | None):
        """
        Safe random int generation (mirrors faker's private helper).

        Exists in faker/providers/python/__init__.py
        but it's not available in our provider because it's named as private.

        Also: https://github.com/joke2k/faker/issues/1152  (fixed here)
        """
        if None not in (min_value, max_value) and min_value == max_value:
            return min_value

        for _ in range(100):
            a_min = min_value
            a_max = max_value

            if a_min is None and a_max is None:
                a, b = self.random_int(), self.random_int()
                a_min = min(a, b)
                a_max = max(a, b)
            elif a_min is None:
                a_min = a_max - self.random_int()
            elif a_max is None:
                a_max = a_min + self.random_int()

            if a_min != a_max:
                return self.random_int(a_min, a_max - 1)

        # fallback: if we couldn't get a range after 100 attempts,
        # return min_value or max_value or 0
        return min_value if min_value is not None else (max_value if max_value is not None else 0)

    # ── Finite-domain detection for uniqueItems ──────────────────────

    #: Largest domain we'll enumerate exhaustively.  Keeps memory and
    #: generation time bounded while covering all practical cases
    #: (bounded integers up to 1000, enums, booleans, etc.).
    _FINITE_DOMAIN_MAX: Final[int] = 1000

    @staticmethod
    def _matches_schema(value: JsonT, schema: SchemaT) -> bool:
        """Return True if *value* validates against *schema*."""
        try:
            validate(value, schema)
            return True
        except ValidationError:
            return False

    def _generate_remaining_items(
        self,
        generate_item: Callable[[], JsonT],
        count: int,
        unique_items: bool,
        existing: list[JsonT],
        accept_item: Callable[[JsonT], bool],
        contains: SchemaT | None,
        contains_budget: int | None,
        retry_factor: int = 3,
    ) -> list[JsonT]:
        """
        Generate *count* array items with shared uniqueness/duplicate logic.

        Parameters
        ----------
        generate_item:
            Zero-arg callable that produces one item.
        count:
            Target number of items to generate.
        unique_items:
            When ``True``, reject duplicate items.
        existing:
            Items already in the array (for uniqueness checks).
        accept_item:
            Callable that returns ``True`` if the item is acceptable
            (e.g. not exceeding ``maxContains``).
        contains:
            The ``contains`` sub-schema, if any (used for duplicate top-up
            budget filtering).
        contains_budget:
            Remaining budget for contains-matching items, or ``None``.
        retry_factor:
            Multiplier on ``actual_count`` for the retry loop (schema-based
            generation uses 3; random-type generation uses 1).
        """
        dup_count = 0
        actual_count = count
        if not unique_items and actual_count > 1:
            dup_count = self.generator.random_int(0, actual_count // 2)
            actual_count -= dup_count

        items: list[JsonT] = []
        duplicates: list[JsonT] = []
        for _ in range(max(actual_count * retry_factor, actual_count)):
            try:
                item = generate_item()
            except UnsatisfiableConstraintsError:
                break
            if unique_items and (item in existing or item in items):
                pass
            elif not accept_item(item):
                pass  # would exceed maxContains
            else:
                items.append(item)
            if (
                not unique_items
                and len(duplicates) < dup_count
                and (item in existing or item in items)
                and accept_item(item)
            ):
                duplicates.append(item)
            if len(items) >= actual_count:
                break

        if not unique_items:
            if len(duplicates) < dup_count and items:
                diff = dup_count - len(duplicates)
                pool = items
                if contains_budget is not None and contains is not None:
                    pool = [x for x in items if not self._matches_schema(x, contains)]
                    if not pool:
                        pool = items  # best effort
                top_up = self.generator.random_sample(pool, length=min(diff, len(pool)))
                for dup_item in top_up:
                    if accept_item(dup_item):
                        duplicates.append(dup_item)
            items.extend(duplicates)

        return items

    def _enumerate_finite_domain(self, schema: SchemaT) -> list[JsonT] | None:
        """
        Return all possible values for *schema*, or ``None`` if infinite.

        Return all possible values for *schema*, or ``None`` if the domain
        is infinite or too large to enumerate.

        Recognised finite domains
        ─────────────────────────
        • ``{"type": "boolean"}``                          → [false, true]
        • ``{"type": "null"}``                             → [null]
        • ``{"enum": [...]}``                              → the enum values
        • ``{"const": x}``                                 → [x]
        • ``{"type": "integer", "minimum": a, "maximum": b}``
           (with optional exclusive variants and multipleOf)
        • nullable variants of all the above (adds ``null``)
        • ``{"type": ["boolean", "null"]}`` etc.           → union of types
        """
        # const — always a single value
        if "const" in schema:
            return [schema["const"]]

        # enum — explicit finite set
        if "enum" in schema:
            vals = list(schema["enum"])
            return vals if len(vals) <= self._FINITE_DOMAIN_MAX else None

        type_val = schema.get("type")
        if type_val is None:
            return None

        # type as array: union of types, e.g. ["boolean", "null"]
        if isinstance(type_val, list):
            combined: list[JsonT] = []
            seen: set[JsonVal] = set()
            for t in type_val:
                sub = self._enumerate_finite_domain({**schema, "type": t})
                if sub is None:
                    return None
                for v in sub:
                    key = JsonVal(v)
                    if key not in seen:
                        seen.add(key)
                        combined.append(v)
                if len(combined) > self._FINITE_DOMAIN_MAX:
                    return None
            return combined

        nullable = schema.get("nullable", False)

        if type_val == "boolean":
            domain: list[JsonT] = [False, True]
            if nullable:
                domain.append(None)
            return domain

        if type_val == "null":
            return [None]

        if type_val == "integer":
            domain_or_none = self._enumerate_integer_domain(schema)
            if domain_or_none is None:
                return None
            if nullable and None not in domain_or_none:
                domain_or_none.append(None)
            return domain_or_none

        return None

    @staticmethod
    def _decode_integer_bounds(schema: SchemaT) -> tuple[int, int, int] | None:
        """
        Return ``(lo, hi, step)`` for a bounded integer schema, or ``None``.

        Unlike :meth:`_enumerate_integer_domain`, no size cap is applied.
        *step* equals ``multipleOf`` when present, otherwise 1.  *lo* is
        already adjusted to the first valid multiple when ``multipleOf`` is
        set.  Returns ``None`` when the schema is unbounded or the range is
        empty / unsatisfiable.
        """
        raw_lo = schema.get("minimum")
        raw_hi = schema.get("maximum")
        excl_lo = schema.get("exclusiveMinimum")
        excl_hi = schema.get("exclusiveMaximum")

        if excl_lo is not None:
            eff_lo = excl_lo + 1
        elif raw_lo is not None:
            eff_lo = raw_lo
        else:
            return None  # unbounded below

        if excl_hi is not None:
            eff_hi = excl_hi - 1
        elif raw_hi is not None:
            eff_hi = raw_hi
        else:
            return None  # unbounded above

        if eff_hi < eff_lo:
            return None  # empty / unsatisfiable

        multiple_of = schema.get("multipleOf")
        if multiple_of is not None:
            if multiple_of <= 0:
                return None
            first = math.ceil(eff_lo / multiple_of) * multiple_of
            if first > eff_hi:
                return None
            return (int(first), int(eff_hi), int(multiple_of))

        return (int(eff_lo), int(eff_hi), 1)

    def _enumerate_integer_domain(self, schema: SchemaT) -> list[JsonT] | None:
        """
        Enumerate all integers satisfying the schema's bounds.

        Returns ``None`` if the domain is unbounded or too large to
        enumerate (> :attr:`_FINITE_DOMAIN_MAX`).  Returns ``[]`` when the
        schema is bounded but unsatisfiable (empty range, no valid
        ``multipleOf`` candidate, etc.).
        """
        bounds = self._decode_integer_bounds(schema)
        if bounds is None:
            # _decode_integer_bounds returns None for two reasons:
            # (a) missing minimum/maximum → unbounded → return None
            # (b) bounded but empty range → return []
            has_lo = schema.get("exclusiveMinimum") is not None or schema.get("minimum") is not None
            has_hi = schema.get("exclusiveMaximum") is not None or schema.get("maximum") is not None
            return [] if (has_lo and has_hi) else None

        lo, hi, step = bounds
        count = (hi - lo) // step + 1 if step > 1 else hi - lo + 1

        if count > self._FINITE_DOMAIN_MAX:
            return None
        return [lo + i * step for i in range(int(count))]

    def _sample_unique_from_integer_range(
        self,
        lo: int,
        hi: int,
        step: int,
        count: int,
        excluded: set[JsonVal],
    ) -> list[int] | None:
        """
        Sample *count* unique integers from ``{lo, lo+step, ..., hi}``.

        Excluding values already present in *excluded*.

        Uses a partial (partial-selection) Fisher-Yates shuffle on a
        virtual index array, so no O(n) list materialisation is needed.
        Time and space: O(*count*).

        Returns ``None`` if fewer than *count* values are available after
        applying exclusions.
        """
        n_total = (hi - lo) // step + 1
        if count <= 0:
            return []
        if count > n_total:
            return None

        # Count excluded integers that actually land on a step boundary
        # inside our range.  bool is a subclass of int, so we must
        # explicitly exclude booleans (True/False are not integers in JSON).
        n_excluded_in_range = sum(
            1
            for jv in excluded
            if not isinstance(jv.__wrapped__, bool)
            and isinstance(jv.__wrapped__, int)
            and lo <= jv.__wrapped__ <= hi
            and (jv.__wrapped__ - lo) % step == 0
        )
        if count > n_total - n_excluded_in_range:
            return None

        # Partial Fisher-Yates on virtual indices 0 … n_total-1.
        # mapping[i] = logical index at slot i (implicit identity when absent).
        # We discover excluded values lazily and swap them to the tail.
        mapping: dict[int, int] = {}
        result: list[int] = []
        available_end = n_total - 1

        # Safety bound: worst case we need to skip every excluded value
        # before finding count good ones.
        max_iters = count + n_excluded_in_range + 16
        iters = 0

        while len(result) < count and iters < max_iters:
            iters += 1
            front = len(result)
            j = self.generator.random_int(front, available_end)
            idx_j = mapping.get(j, j)
            idx_front = mapping.get(front, front)
            val = lo + idx_j * step

            if JsonVal(val) in excluded:
                # Move this excluded slot out of the live range
                mapping[j] = mapping.get(available_end, available_end)
                mapping[available_end] = idx_j
                available_end -= 1
            else:
                # Accept: swap slot j into slot front
                mapping[front] = idx_j
                mapping[j] = idx_front
                result.append(val)

        return result if len(result) == count else None

    def _jsonschema_number(
        self,
        mode: NumberMode,
        minimum: Number | None = None,
        maximum: Number | None = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: Number | None = None,
        exclusive_maximum: Number | None = None,
        multiple_of: Number | None = None,
    ) -> Number:
        if mode is NumberMode.FLOAT:

            def _make_safe(val):
                return Decimal(str(val)) if val is not None else val

            _cast: Final = float
            _offset: Final = self.FLOAT_OFFSET
            _generator: Final = self.better_pyfloat
        elif mode is NumberMode.INTEGER:

            def _make_safe_int(val):
                return val

            _make_safe = _make_safe_int

            _cast: Final = int
            _offset: Final = 1
            _generator: Final = self._safe_random_int
        else:
            raise TypeError(mode)

        # TODO:
        # https://json-schema.org/draft-07/json-schema-validation.html#rfc.section.6.2.1
        # multiple_of must be > 0

        # Draft-06+ numeric exclusiveMinimum/exclusiveMaximum
        # These take precedence over the draft-04 boolean form.
        # When both forms are present, use the stricter (tighter) bound.
        if exclusive_minimum is not None and (minimum is None or exclusive_minimum >= minimum):
            minimum = exclusive_minimum
            exclusive_min = True
        if exclusive_maximum is not None and (maximum is None or exclusive_maximum <= maximum):
            maximum = exclusive_maximum
            exclusive_max = True

        original_min = minimum
        original_max = maximum

        if None not in (minimum, maximum):
            if maximum < minimum:
                raise ValueError("maximum must be >= minimum")
            diff = maximum - minimum
            min_diff = 0
            if exclusive_min:
                min_diff += _offset
            if exclusive_max:
                min_diff += _offset
            if diff < min_diff:
                raise UnsatisfiableConstraintsError(
                    f"cannot satisfy constraints "
                    f"minimum: {original_min}, maximum: {original_max}, "
                    f"exclusiveMin: {exclusive_min}, exclusiveMax: {exclusive_max}"
                )

        def offset_val(val, op):
            return op(val, _offset)

        # `better_pyfloat` range is inclusive
        if exclusive_min and minimum is not None:
            offset_min = offset_val(minimum, operator.add)
            minimum = min(offset_min, maximum) if maximum is not None else offset_min
        if exclusive_max and maximum is not None:
            offset_max = offset_val(maximum, operator.sub)
            maximum = max(offset_max, minimum) if minimum is not None else offset_max

        safe_min = _make_safe(minimum)
        safe_max = _make_safe(maximum)

        if minimum is not None and minimum == maximum:
            # (returns early)
            if multiple_of is not None and Decimal(str(minimum)) % Decimal(str(multiple_of)) != 0:
                raise UnsatisfiableConstraintsError(
                    f"cannot satisfy constraints multipleOf: {multiple_of}, "
                    f"minimum: {original_min}, maximum: {original_max}"
                )
            return _cast(minimum)

        if None not in (minimum, maximum) and maximum < minimum:
            raise ValueError("maximum must be >= minimum")

        if multiple_of is None:
            # (returns early)
            return _generator(min_value=minimum, max_value=maximum)

        # `multiple_of` is a massive PITA...
        multiple_of = _make_safe(multiple_of)

        if multiple_of == 0:
            raise ValueError("invalid value for multipleOf: 0")

        if minimum is None and maximum is None:
            multiple = self.generator.random_int()
            return _cast(_make_safe(multiple) * multiple_of)

        def valid_range() -> bool:
            return (
                (safe_min % multiple_of == 0 and not exclusive_min)
                or (safe_max % multiple_of == 0 and not exclusive_max)
                or int(safe_min / multiple_of) != int(safe_max / multiple_of)
            )

        if None in (minimum, maximum):
            # we need to choose a range that satisfies `multiple_of`
            def set_missing() -> None:
                nonlocal safe_min, safe_max
                if maximum is None:
                    assert minimum is not None
                    safe_max = safe_min + self.generator.random_int()
                elif minimum is None:
                    assert maximum is not None
                    safe_min = safe_max - self.generator.random_int()

            for _ in range(100):
                set_missing()
                if valid_range():
                    break
            else:
                raise UnsatisfiableConstraintsError(
                    f"Could not find a valid range for multipleOf: {multiple_of}, "
                    f"minimum: {original_min}, maximum: {original_max} "
                    f"in 100 iterations"
                )
        else:
            # minmimum and maximum were both specified
            if not valid_range():
                # range does not include any multiples of `multiple_of`
                raise UnsatisfiableConstraintsError(
                    f"cannot satisfy constraints multipleOf: {multiple_of}, "
                    f"minimum: {original_min}, maximum: {original_max}, "
                    f"exclusiveMin: {exclusive_min}, exclusiveMax: {exclusive_max}"
                )

        def get_range() -> tuple[int, int]:
            low = safe_min / multiple_of
            high = safe_max / multiple_of
            low, high = sorted((low, high))
            return math.ceil(low), math.floor(high)

        low, high = get_range()
        multiple = self.generator.random_int(low, high)
        return _cast(_make_safe(multiple) * multiple_of)

    def jsonschema_number(
        self,
        minimum: float | None = None,
        maximum: float | None = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: float | None = None,
        exclusive_maximum: float | None = None,
        multiple_of: float | None = None,
    ) -> float:
        return self._jsonschema_number(
            mode=NumberMode.FLOAT,
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
            exclusive_minimum=exclusive_minimum,
            exclusive_maximum=exclusive_maximum,
            multiple_of=multiple_of,
        )

    def jsonschema_integer(
        self,
        minimum: int | None = None,
        maximum: int | None = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: int | None = None,
        exclusive_maximum: int | None = None,
        multiple_of: int | None = None,
    ) -> int:
        return self._jsonschema_number(
            mode=NumberMode.INTEGER,
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
            exclusive_minimum=exclusive_minimum,
            exclusive_maximum=exclusive_maximum,
            multiple_of=multiple_of,
        )

    def jsonschema_boolean(self) -> bool:
        return self.generator.boolean()

    def jsonschema_null(self) -> None:
        return None

    def jsonschema_oneof(self, schemas: Iterable[JsonT]) -> JsonT:
        schema = self.generator.random_element(schemas)
        return self._from_schema(schema)

    def jsonschema_anyof(self, schemas: Iterable[JsonT]) -> JsonT:
        """
        Group all schemas by type and randomly combine.

        Randomly choose a type. Randomly combine one or more of the given
        schemas of that type according to the rules for `allOf`.
        Schemas without an explicit ``type`` (e.g. ``{"const": 1}``) are
        each treated as a standalone candidate.
        """
        schema_map = {
            k: list(v) for k, v in itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        }
        # Untyped schemas are standalone candidates — pick one directly
        untyped = schema_map.pop(_NO_TYPE, [])
        candidates: list[SchemaT] = []
        for type_key, type_schemas in schema_map.items():
            candidates.append(("typed", type_key, type_schemas))
        for s in untyped:
            candidates.append(("untyped", None, [s]))
        if not candidates:
            raise UnsatisfiableConstraintsError("anyOf has no candidate schemas")
        choice = self.generator.random_element(candidates)
        kind, type_key, group = choice
        if kind == "untyped":
            return self._from_schema(group[0])
        sub_schemas = self.generator.random_sample(group, length=None)
        schema = compound_schema(sub_schemas)
        return self._from_schema(schema)

    def jsonschema_allof(self, schemas: Iterable[JsonT]) -> JsonT:
        """
        Make a compound schema from all members and generate a value.

        Even the spec says:
        "Note that it’s quite easy to create schemas that are logical
        impossibilities..."
        I think all mixed-type cases are impossible to satisfy (?)

        If they are all the same type we should AND their validation
        restrictions together and return for that.
        Schemas without an explicit ``type`` are merged in without
        type-conflict checks (``_merge_schemas`` propagates the type
        from the typed side).
        """
        schema_map = {
            k: list(v) for k, v in itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        }
        # Untyped schemas are compatible with any type — don’t count as a conflict
        schema_map.pop(_NO_TYPE, None)
        if len(schema_map) > 1:
            raise UnsatisfiableConstraintsError(
                f"Cannot satisfy allOf multiple types: {set(schema_map.keys())}"
            )
        schema = compound_schema(schemas)
        return self._from_schema(schema)

    def _random_type_method(self) -> tuple[TypeName, Callable]:
        types = BASIC_TYPES if self.context._depth < self.context.max_depth else FLAT_TYPES
        type_ = self.generator.random_element(types)
        generator = getattr(self, self.BASE_METHOD_MAP[type_])
        if type_ in NESTED_TYPES:
            # TODO: I think in some cases we're double descending here
            # (i.e. the caller of `_random_type_method` already descended)
            generator = self.descend_into(generator)
        return type_, generator

    def jsonschema_any(self) -> JsonT:
        """We should generate a random element of any type. No restrictions."""
        _, generator = self._random_type_method()
        return generator()

    def _random_type_method_excluding(
        self, exclude_type: TypeName | None
    ) -> tuple[TypeName, Callable]:
        """
        Pick a random type and its generator, excluding *exclude_type*.

        In JSON Schema ``integer`` is a subtype of ``number``, so excluding
        ``number`` also excludes ``integer`` (an integer would still validate
        against ``{"type": "number"}``).
        """
        types = BASIC_TYPES if self.context._depth < self.context.max_depth else FLAT_TYPES
        if exclude_type is not None:
            exclude = {exclude_type}
            # integer is a subtype of number in JSON Schema:
            # an integer validates against {type: "number"}, and a
            # whole-number float validates against {type: "integer"}.
            if exclude_type in (TypeName.NUMBER, TypeName.INTEGER):
                exclude.update({TypeName.NUMBER, TypeName.INTEGER})
            types = types - exclude
        if not types:
            raise NoExampleFoundError(f"No alternative types available (excluding {exclude_type}).")
        type_ = self.generator.random_element(types)
        generator = getattr(self, self.BASE_METHOD_MAP[type_])
        if type_ in NESTED_TYPES:
            generator = self.descend_into(generator)
        return type_, generator

    def jsonschema_not(self, schema: SchemaT) -> JsonT:
        """
        Generate a random value that does NOT validate against *schema*.

        Strategy:
        - If the schema has a ``type``, prefer generating a different type
          (guaranteed to not validate, no retry needed).
        - With small probability, try generating a same-type value that
          violates the schema's constraints (for variety).
        - If same-type attempts fail quickly, fall back to a different type.

        Raises:
            NoExampleFoundError
            UnsatisfiableConstraintsError: if the negated schema accepts
                everything (``{}`` or ``True``), making it impossible to
                generate any conforming value.
        """
        # {} and True are the "accept everything" schemas; NOT {} forbids all
        # values — there is nothing to generate.
        if schema is True or schema == {}:
            raise UnsatisfiableConstraintsError(
                "'not: {}' (or 'not: true') rejects every instance; "
                "cannot generate a conforming value."
            )

        def is_valid(val) -> bool:
            try:
                validate(val, schema)
            except ValidationError:
                return False
            return True

        not_type_str = schema.get("type") if isinstance(schema, dict) else None
        not_type = TypeName(not_type_str) if not_type_str is not None else None

        # If schema has a type, bias strongly toward a different type.
        # ~85% of the time pick a different type (guaranteed success).
        # ~15% of the time try same-type for variety (may need retry).
        _SAME_TYPE_CHANCE = 15  # percent
        _QUICK_TRIES = 20

        if not_type is not None:
            try_same_type = self.generator.random_int(1, 100) <= _SAME_TYPE_CHANCE
        else:
            # No type in schema — can't bias, just generate and reject
            try_same_type = True

        if try_same_type:
            type_, generator = self._random_type_method()
            same_type = not_type is not None and (
                type_ == not_type or {not_type, type_} <= {TypeName.NUMBER, TypeName.INTEGER}
            )
            if same_type:
                # Quick search: try a small number of attempts
                for _ in range(_QUICK_TRIES):
                    example = generator()
                    if not is_valid(example):
                        return example
                # Quick search failed — fall back to a different type
            elif not_type is None:
                # Untyped schema — must validate the generated value
                for _ in range(_QUICK_TRIES):
                    example = generator()
                    if not is_valid(example):
                        return example
                # Random generation failed; try targeted inversion for
                # numeric keyword schemas (e.g. {"minimum": 0})
                if isinstance(schema, dict):
                    inverted = self._invert_numeric_not_schema(schema)
                    if inverted is not None:
                        try:
                            result = self._from_schema(inverted)
                            if not is_valid(result):
                                return result
                        except (UnsatisfiableConstraintsError, NoExampleFoundError):
                            pass
                    inverted_str = self._invert_string_not_schema(schema)
                    if inverted_str is not None:
                        try:
                            result = self._from_schema(inverted_str)
                            if not is_valid(result):
                                return result
                        except (UnsatisfiableConstraintsError, NoExampleFoundError):
                            pass
                raise NoExampleFoundError(
                    f"Could not generate a value not matching untyped schema {schema!r}"
                )
            else:
                # Different type chosen randomly — no retry needed
                return generator()

        # Pick a type that's different from the NOT schema's type
        type_, generator = self._random_type_method_excluding(not_type)
        return generator()

    @staticmethod
    def _invert_numeric_not_schema(schema: SchemaT) -> SchemaT | None:
        """
        Build a numeric schema whose values violate the given constraints.

        Returns ``None`` if the schema has no invertible numeric keywords.
        """
        _NUMERIC_KW = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
        if not (set(schema.keys()) & _NUMERIC_KW):
            return None
        inverted: SchemaT = {"type": "number"}
        if "minimum" in schema:
            inverted["exclusiveMaximum"] = schema["minimum"]
        if "maximum" in schema:
            inverted["exclusiveMinimum"] = schema["maximum"]
        if "exclusiveMinimum" in schema:
            inverted["maximum"] = schema["exclusiveMinimum"]
        if "exclusiveMaximum" in schema:
            inverted["minimum"] = schema["exclusiveMaximum"]
        return inverted

    @staticmethod
    def _invert_string_not_schema(schema: SchemaT) -> SchemaT | None:
        """
        Build a string schema whose values violate the given constraints.

        Returns ``None`` if the schema has no invertible string keywords.
        """
        _STRING_KW = {"minLength", "maxLength", "pattern"}
        if not (set(schema.keys()) & _STRING_KW):
            return None
        inverted: SchemaT = {"type": "string"}
        if "minLength" in schema and schema["minLength"] > 0:
            inverted["maxLength"] = schema["minLength"] - 1
        elif "maxLength" in schema:
            inverted["minLength"] = schema["maxLength"] + 1
        else:
            return None
        return inverted

    def _get_collection_max(self, min_: int):
        if min_ > self.context.default_collection_max:
            return self.generator.random_int(min_, min_ + self.context.default_collection_max)
        else:
            return self.generator.random_int(min_, self.context.default_collection_max)

    def jsonschema_array(
        self,
        items: SchemaT | None = None,
        prefix_items: list[SchemaT] | None = None,
        additional_items: bool | SchemaT | None = None,
        unevaluated_items: bool | SchemaT | None = None,
        contains: SchemaT | None = None,
        min_contains: int | None = None,
        max_contains: int | None = None,
        min_items: int = 0,
        max_items: int | None = None,
        unique_items: bool = False,
    ) -> list[JsonT]:
        """
        Generate a list conforming to JSON Schema array constraints.

        Supports:
        - items (single schema or absent)
        - prefixItems (draft 2020-12 tuple validation)
        - additionalItems (draft-04 through 2019-09)
        - unevaluatedItems (draft 2019-09+)
        - contains / minContains / maxContains
        - minItems / maxItems / uniqueItems
        """
        if min_items < 0:
            raise ValueError("minItems must be >= 0")
        if max_items is not None and min_items > max_items:
            raise ValueError("maxItems must be >= minItems")

        prefix_items = prefix_items or []
        n_prefix = len(prefix_items)

        # Determine the schema for remaining (non-prefix) items
        remaining_schema: SchemaT | None = None
        if prefix_items and items is not None:
            # Draft 2020-12: items applies after prefixItems
            # items: false → no additional items beyond prefix
            if items is False:
                remaining_schema = None
            elif items is True:
                remaining_schema = {}
            else:
                remaining_schema = items
        elif prefix_items and additional_items is not None:
            # Draft-04 through 2019-09: additionalItems applies after tuple items
            if additional_items is False:
                remaining_schema = None  # no additional items allowed
            elif isinstance(additional_items, dict):
                remaining_schema = additional_items
            else:
                remaining_schema = None  # True means any schema
                if additional_items is True:
                    remaining_schema = {}
        elif items is not None:
            # Standard homogeneous array
            if items is False:
                remaining_schema = None
            elif items is True:
                remaining_schema = {}
            else:
                remaining_schema = items
        else:
            # No item schema at all — pick a random type
            if not prefix_items:
                type_, _ = self._random_type_method()
                remaining_schema = {"type": type_.value}

        if max_items is None:
            max_items = self._get_collection_max(max(min_items, n_prefix))

        # When no remaining items are allowed, cap at prefix length
        if remaining_schema is None and prefix_items:
            max_items = min(max_items, n_prefix)

        # ── Plan contains items upfront ─────────────────────────────
        # Instead of generating the array and hoping items match contains,
        # we decide how many contains-matching items to produce first,
        # generate them from the contains schema, then fill remaining
        # slots from the items/remaining schema.
        n_contains_target = 0
        if contains is not None:
            eff_min_c = min_contains if min_contains is not None else 1
            eff_max_c = max_contains

            # How many slots are available after prefix items?
            capacity = max_items - n_prefix
            capacity = max(capacity, 0)

            # Upper bound for contains items to generate
            if eff_max_c is not None:
                upper = min(eff_max_c, capacity)
            else:
                # No maxContains — generate a few more than the minimum
                upper = min(eff_min_c + 2, capacity)
            upper = max(upper, eff_min_c)

            if capacity >= eff_min_c:
                n_contains_target = self._safe_random_int(eff_min_c, upper)
            else:
                # Can't fit minContains — best effort
                n_contains_target = max(capacity, 0)

        # Ensure we have at least enough items for prefix + contains
        effective_min = max(min_items, n_prefix) if prefix_items else min_items
        if n_contains_target > 0:
            effective_min = max(effective_min, n_prefix + n_contains_target)
        # Clamp to max_items in case of conflicting constraints
        effective_min = min(effective_min, max_items)

        count = self._safe_random_int(effective_min, max_items)

        # When uniqueItems is requested, cap count at the domain size so we
        # never ask for more unique values than actually exist.
        if unique_items and remaining_schema is not None:
            domain = self._enumerate_finite_domain(remaining_schema)
            if domain is not None:
                # Also account for contains domain extending the pool
                if contains is not None:
                    contains_domain_pre = self._enumerate_finite_domain(contains)
                    if contains_domain_pre is not None:
                        all_vals = {JsonVal(v) for v in domain}
                        for v in contains_domain_pre:
                            all_vals.add(JsonVal(v))
                        total_unique = len(all_vals) + n_prefix
                    else:
                        # contains domain unknown — can't bound precisely
                        total_unique = None
                else:
                    total_unique = len(domain) + n_prefix
                if total_unique is not None:
                    if total_unique < min_items:
                        raise UnsatisfiableConstraintsError(
                            f"Cannot generate {min_items} unique items "
                            f"from a domain of size {total_unique}"
                        )
                    if count > total_unique:
                        count = max(effective_min, min(count, total_unique))

        # Generate prefix items
        generated: list[JsonT] = []
        for i in range(min(count, n_prefix)):
            item = self.descend_into(self._from_schema)(prefix_items[i])
            generated.append(item)

        # Generate contains items from the contains schema
        contains_items: list[JsonT] = []
        if n_contains_target > 0 and contains is not None:
            # Clamp in case count can't fit all planned contains items
            n_contains_target = min(n_contains_target, count - len(generated))

            # Finite-domain fast path for uniqueItems
            contains_domain = self._enumerate_finite_domain(contains) if unique_items else None
            if unique_items and contains_domain is not None:
                # Remove already-used values (from prefix items)
                used = {JsonVal(v) for v in generated}
                available = [v for v in contains_domain if JsonVal(v) not in used]
                take = min(n_contains_target, len(available))
                contains_items = self.generator.random_sample(available, length=take)
            elif (
                unique_items
                and contains is not None
                and contains.get("type") == "integer"
                and not contains.get("nullable", False)
            ):
                # Large bounded integer contains schema: partial Fisher-Yates
                bounds = self._decode_integer_bounds(contains)
                sampled: list[int] | None = None
                if bounds is not None:
                    used = {JsonVal(v) for v in generated}
                    sampled = self._sample_unique_from_integer_range(
                        *bounds, n_contains_target, used
                    )
                if sampled is not None:
                    contains_items = sampled
                else:
                    # Fisher-Yates unavailable (unbounded or domain too small);
                    # fall back to retry-based generation.
                    for _ in range(n_contains_target * 3):
                        item = self.descend_into(self._from_schema)(contains)
                        if unique_items and (item in generated or item in contains_items):
                            continue
                        contains_items.append(item)
                        if len(contains_items) >= n_contains_target:
                            break
            else:
                for _ in range(n_contains_target * 3):  # retries for uniqueItems
                    item = self.descend_into(self._from_schema)(contains)
                    if unique_items and (item in generated or item in contains_items):
                        continue
                    contains_items.append(item)
                    if len(contains_items) >= n_contains_target:
                        break

        # Generate remaining items from items/remaining schema
        remaining_count = count - len(generated) - len(contains_items)
        remaining_count = max(remaining_count, 0)
        remaining: list[JsonT] = []

        # When maxContains is set, remaining items might accidentally match
        # the contains schema.  Track how many contains-matches we have so
        # far and reject items that would push us over maxContains.
        _contains_budget: int | None = None  # None = unlimited
        if contains is not None and max_contains is not None:
            # contains_items were generated to match; count them against the budget
            _contains_budget = max_contains - len(contains_items)
            # prefix items might also match
            for item in generated:
                try:
                    validate(item, contains)
                    _contains_budget -= 1
                except ValidationError:
                    pass

        def _accept_item(item: JsonT) -> bool:
            """Return True if item is allowed w.r.t. maxContains budget."""
            nonlocal _contains_budget
            if _contains_budget is None:
                return True
            try:
                validate(item, contains)
            except ValidationError:
                return True  # doesn't match contains → always OK
            # Matches contains — only accept if we have budget left
            if _contains_budget > 0:
                _contains_budget -= 1
                return True
            return False

        if remaining_count > 0 and remaining_schema is not None:
            # Finite-domain fast path for uniqueItems
            remaining_domain = (
                self._enumerate_finite_domain(remaining_schema) if unique_items else None
            )
            if unique_items and remaining_domain is not None:
                used = {JsonVal(v) for v in generated + contains_items}
                available = [v for v in remaining_domain if JsonVal(v) not in used]
                # Also filter by contains budget
                if _contains_budget is not None:
                    non_matching = [v for v in available if not self._matches_schema(v, contains)]
                    matching = [v for v in available if self._matches_schema(v, contains)]
                    # Take non-matching first, then fill with matching up to budget
                    budget = max(_contains_budget, 0)
                    take_matching = min(
                        max(remaining_count - len(non_matching), 0),
                        budget,
                        len(matching),
                    )
                    pool = non_matching + matching[:take_matching]
                    take = min(remaining_count, len(pool))
                    remaining = self.generator.random_sample(pool, length=take)
                else:
                    take = min(remaining_count, len(available))
                    remaining = self.generator.random_sample(available, length=take)
            elif (
                unique_items
                and remaining_schema.get("type") == "integer"
                and not remaining_schema.get("nullable", False)
            ):
                # Large bounded integer range: partial Fisher-Yates — O(count)
                # time/space without materialising the full domain list.
                bounds = self._decode_integer_bounds(remaining_schema)
                if bounds is not None:
                    used = {JsonVal(v) for v in generated + contains_items}
                    sampled = self._sample_unique_from_integer_range(*bounds, remaining_count, used)
                    remaining = sampled if sampled is not None else []
                else:
                    remaining = []
            else:

                def _gen_from_schema():
                    return self.descend_into(self._from_schema)(remaining_schema)

                remaining = self._generate_remaining_items(
                    generate_item=_gen_from_schema,
                    count=remaining_count,
                    unique_items=unique_items,
                    existing=generated + contains_items,
                    accept_item=_accept_item,
                    contains=contains,
                    contains_budget=_contains_budget,
                    retry_factor=3,
                )

        elif remaining_count > 0 and remaining_schema is None and not prefix_items:
            # No schema: generate random items
            def _gen_random_type():
                type_, _ = self._random_type_method()
                return self.descend_into(self._from_schema)({"type": type_.value})

            remaining = self._generate_remaining_items(
                generate_item=_gen_random_type,
                count=remaining_count,
                unique_items=unique_items,
                existing=generated + contains_items,
                accept_item=_accept_item,
                contains=contains,
                contains_budget=_contains_budget,
                retry_factor=1,
            )

        # Combine: shuffle non-prefix items together so contains items
        # are distributed throughout the array rather than clustered
        non_prefix = contains_items + remaining
        shuffle(non_prefix)
        generated.extend(non_prefix)

        # Handle unevaluatedItems: apply to positions not covered by
        # prefixItems, items, or contains
        if unevaluated_items is not None and unevaluated_items is not True:
            evaluated_up_to = n_prefix if prefix_items else 0
            if remaining_schema is not None:
                evaluated_up_to = len(generated)  # items covered everything
            if unevaluated_items is False:
                generated = generated[:evaluated_up_to]
            elif isinstance(unevaluated_items, dict):
                for i in range(evaluated_up_to, len(generated)):
                    generated[i] = self.descend_into(self._from_schema)(unevaluated_items)

        return generated

    def jsonschema_object(
        self,
        properties: dict[str, SchemaT] | None = None,
        pattern_properties: dict[str, SchemaT] | None = None,
        property_names: SchemaT | None = None,
        required: list[str] | None = None,
        additional_properties: bool | SchemaT = True,
        unevaluated_properties: bool | SchemaT | None = None,
        min_properties: int = 0,
        max_properties: int | None = None,
        dependent_required: dict[str, list[str]] | None = None,
        dependent_schemas: dict[str, SchemaT] | None = None,
    ) -> dict[str, JsonT]:
        """
        Generate fake data conforming to a JSON Schema object type.

        Supports: properties, patternProperties, propertyNames, required,
        additionalProperties (bool or schema), unevaluatedProperties,
        minProperties, maxProperties, dependentRequired, dependentSchemas.

        TODO: readOnly / writeOnly
        """
        if min_properties < 0:
            raise ValueError("minProperties must be >= 0")
        if max_properties is not None and min_properties > max_properties:
            raise ValueError("maxProperties must be >= minProperties")
        if max_properties is not None and required is not None and max_properties < len(required):
            raise UnsatisfiableConstraintsError(
                f"Cannot satisfy maxProperties: {max_properties} when "
                f"there are {len(required)} properties in required list."
            )
        _allows_additional = additional_properties is not False
        if not _allows_additional:
            _available = len(properties or {})
            if pattern_properties:
                # each pattern can contribute at least one property
                _available += len(pattern_properties)
            if min_properties > _available:
                raise UnsatisfiableConstraintsError(
                    f"Cannot satisfy minProperties: {min_properties} when "
                    f"there are {_available} properties in schema and "
                    f"additionalProperties is False."
                )

        if not _allows_additional and required:
            declared = set((properties or {}).keys())
            undeclared = set(required) - declared
            if pattern_properties:
                undeclared = {
                    k for k in undeclared if not any(re.search(p, k) for p in pattern_properties)
                }
            if undeclared:
                raise UnsatisfiableConstraintsError(
                    f"Required properties {undeclared} not declared in "
                    f"properties and additionalProperties is false."
                )

        og_max_properties = max_properties
        properties = properties or {}
        pattern_properties = pattern_properties or {}
        required_set = set(required or [])
        generated = {}

        def _schema_for_key(attr: str) -> SchemaT:
            """
            Determine the schema for a property key.

            Checks properties, then patternProperties, then
            additionalProperties (if schema), else empty schema.
            """
            if attr in properties:
                return properties[attr]
            for pattern, pschema in pattern_properties.items():
                if re.search(pattern, attr):
                    return pschema
            if isinstance(additional_properties, dict):
                return additional_properties
            return {}

        def generate_values(attrs: Iterable[str], tolerant: bool = False) -> None:
            for attr in attrs:
                schema = _schema_for_key(attr)
                try:
                    val = self.descend_into(self._from_schema)(schema)
                except UnsatisfiableConstraintsError:
                    if not tolerant:
                        raise
                    continue
                generated[attr] = val

        # generate 'required' properties
        if required_set:
            generate_values(required_set)

        if max_properties is None:
            max_properties = self._get_collection_max(max(min_properties, len(required_set)))

        # generate random number of 'non-required' declared properties
        if len(generated) <= max_properties:
            min_needed = max(0, min_properties - len(generated))
            _max_gen = min(len(properties), max_properties) - len(generated)
            if _max_gen > min_needed:
                _count = self.generator.random_int(min_needed, _max_gen)
                non_required_attrs = properties.keys() - required_set
                if non_required_attrs:
                    sampled_non_required = self.generator.random_sample(
                        tuple(non_required_attrs),
                        length=_count,
                    )
                    generate_values(sampled_non_required, tolerant=True)
                    min_needed = max(0, min_needed - len(sampled_non_required))

        # generate patternProperties entries
        if pattern_properties and len(generated) < max_properties:
            min_needed = max(0, min_properties - len(generated))
            for pattern, pschema in pattern_properties.items():
                if len(generated) >= max_properties:
                    break
                # check if any already-generated key matches this pattern
                already_matched = any(re.search(pattern, k) for k in generated)
                if already_matched and min_needed <= 0:
                    continue
                # generate a key name matching the pattern
                _name_schema = {"type": "string", "pattern": pattern}
                try:
                    key = self.descend_into(self._from_schema)(_name_schema)
                except UnsatisfiableConstraintsError:
                    continue
                if key not in generated:
                    val = self.descend_into(self._from_schema)(pschema)
                    generated[key] = val
                    min_needed = max(0, min_needed - 1)

        # generate 'additional' (not in schema) properties?
        min_needed = max(0, min_properties - len(generated))
        if (
            _allows_additional
            and len(generated) < max_properties
            and (min_needed > 0 or self.generator.random_int(0, 1))
        ):
            _remaining = max_properties - len(generated)
            _count = self.generator.random_int(min(min_needed, _remaining), _remaining)
            if og_max_properties is None:
                # lots of additional_properties just feels weird
                _surplus = _count - min_needed
                _surplus = _surplus // 3 if _surplus > 3 else _surplus
                _count = min_needed + _surplus

            # generate random property names
            if property_names is None:
                property_names = self.context.default_property_schema
            _name_schema = {"type": "string"}
            _name_schema.update(property_names)
            method = partial(self._from_schema, schema=_name_schema)
            # generate unique names to avoid dict key collisions
            generated_names: list[str] = []
            existing_keys = set(generated.keys())
            for _ in range(_count * 5):  # allow retries for uniqueness
                name = method()
                if name not in existing_keys:
                    generated_names.append(name)
                    existing_keys.add(name)
                if len(generated_names) >= _count:
                    break

            # generate values — use additionalProperties schema if provided
            _val_schema = additional_properties if isinstance(additional_properties, dict) else {}
            for name in generated_names:
                generated[name] = self.descend_into(self._from_schema)(_val_schema)

        # enforce dependentRequired: if a trigger key is present,
        # all its dependent keys must also be present
        if dependent_required:
            for trigger, deps in dependent_required.items():
                if trigger in generated:
                    for dep in deps:
                        if dep not in generated:
                            schema = _schema_for_key(dep)
                            generated[dep] = self.descend_into(self._from_schema)(schema)

        # enforce dependentSchemas: if a trigger key is present,
        # merge the dependent schema constraints into the result
        if dependent_schemas:
            for trigger, dep_schema in dependent_schemas.items():
                if trigger in generated:
                    # dependent schema is an object schema — generate any
                    # required properties and merge into result
                    dep_required = dep_schema.get("required", [])
                    dep_props = dep_schema.get("properties", {})
                    for dep_key in dep_required:
                        if dep_key not in generated:
                            sub = dep_props.get(dep_key, {})
                            generated[dep_key] = self.descend_into(self._from_schema)(sub)
                        elif dep_key in dep_props:
                            # re-generate to match the dependent schema
                            sub = dep_props[dep_key]
                            generated[dep_key] = self.descend_into(self._from_schema)(sub)

        # enforce unevaluatedProperties
        if unevaluated_properties is not None:
            evaluated_keys = set(properties.keys())
            for pattern in pattern_properties:
                for k in list(generated.keys()):
                    if re.search(pattern, k):
                        evaluated_keys.add(k)
            # keys from dependentSchemas also count as evaluated
            if dependent_schemas:
                for trigger, dep_schema in dependent_schemas.items():
                    if trigger in generated:
                        for k in dep_schema.get("properties", {}):
                            evaluated_keys.add(k)

            unevaluated = set(generated.keys()) - evaluated_keys
            if unevaluated_properties is False:
                # remove unevaluated properties
                for k in unevaluated:
                    del generated[k]
            elif isinstance(unevaluated_properties, dict):
                # re-generate unevaluated values to match the schema
                for k in unevaluated:
                    generated[k] = self.descend_into(self._from_schema)(unevaluated_properties)

        return generated

    @nullable_or_enum
    def _jsonschema_basic_type_from_schema(self, schema: SchemaT, type_: TypeName) -> JsonT:
        method = getattr(self, self.BASE_METHOD_MAP[type_])
        return method(**method.kwargs_from_schema(schema))

    @nullable_or_enum
    def _jsonschema_compound_type_from_schema(self, schema: SchemaT, type_: TypeName) -> JsonT:
        return getattr(self, self.BASE_METHOD_MAP[type_])(schema[type_.value])

    @nullable_or_enum
    def _jsonschema_any_from_schema(self, _: SchemaT) -> JsonT | None:
        # NOTE: `any` can still be `nullable` (...or `enum`?)
        # NOTE: `nullable_or_enum` needs the schema arg
        return self.jsonschema_any()

    def _from_schema(self, schema: SchemaT):
        """
        Generate from schema (internal recursive entry point).

        All recursive calls should use this private method instead of the
        public `from_schema` below so that `context._depth` is not reset.
        """
        # Handle boolean schemas (draft-06+)
        if schema is True or schema == {}:
            return self.jsonschema_any()
        if schema is False:
            raise UnsatisfiableConstraintsError("Boolean schema 'false' rejects all instances.")

        _pushed_ref = None

        # Handle $ref resolution
        if "$ref" in schema:
            ref = schema["$ref"]
            self.context._ref_stack.append(ref)
            _pushed_ref = ref
            try:
                schema = self._resolve_ref(schema)
            except UnsatisfiableConstraintsError:
                self.context._ref_stack.pop()
                raise

        try:
            return self.__from_schema_inner(schema)
        finally:
            if _pushed_ref is not None:
                self.context._ref_stack.pop()

    def __from_schema_inner(self, schema: SchemaT):

        # Handle const (draft-06+)
        if "const" in schema:
            return schema["const"]

        # Handle if/then/else: randomly choose a branch and merge it
        if "if" in schema:
            schema = self._apply_if_then_else(schema)

        # Pre-process draft-04 through 2019-09 tuple-form items.
        # When "items" is a list of schemas it acts like "prefixItems" in
        # draft 2020-12.  Normalise to prefixItems so the array generator
        # handles it correctly.  "additionalItems" is kept as-is; the array
        # generator already understands it once prefix_items is populated.
        if isinstance(schema.get("items"), list):
            schema = dict(schema)  # shallow copy — do not mutate caller's dict
            schema["prefixItems"] = schema.pop("items")

        # Pre-process legacy "dependencies" keyword (draft-04 through draft-07)
        # Split into "dependentRequired" (array values) and
        # "dependentSchemas" (schema values) for the object generator.
        if "dependencies" in schema:
            schema = dict(schema)  # shallow copy to avoid mutating caller's dict
            deps = schema.pop("dependencies")
            dep_required = schema.get("dependentRequired", {})
            dep_schemas = schema.get("dependentSchemas", {})
            for key, val in deps.items():
                if isinstance(val, list):
                    # Array of strings → dependentRequired
                    existing = dep_required.get(key, [])
                    dep_required[key] = list(set(existing) | set(val))
                elif isinstance(val, dict):
                    # Schema → dependentSchemas
                    dep_schemas[key] = val
            if dep_required:
                schema["dependentRequired"] = dep_required
            if dep_schemas:
                schema["dependentSchemas"] = dep_schemas

        # Handle enum without type (intercepted here because nullable_or_enum
        # decorator only fires on type-dispatched methods)
        if "enum" in schema and "type" not in schema:
            # Check for compound types first
            for type_ in COMPOUND_TYPES:
                if type_.value in schema:
                    return self._jsonschema_compound_type_from_schema(schema, type_)
            return self.jsonschema_enum(JsonEnum(schema["enum"]))

        try:
            type_val = schema["type"]
        except KeyError:
            for type_ in COMPOUND_TYPES:
                if type_.value in schema:
                    return self._jsonschema_compound_type_from_schema(schema, type_)
            else:
                return self._jsonschema_any_from_schema(schema)
        else:
            # Handle type as array (draft-06+): e.g. {"type": ["string", "null"]}
            if isinstance(type_val, list):
                chosen = self.generator.random_element(type_val)
                schema = {**schema, "type": chosen}
                type_val = chosen
            type_ = TypeName(type_val)
            return self._jsonschema_basic_type_from_schema(schema, type_)

    _NEGATABLE_NUMERIC_KEYS = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
    }
    _NEGATABLE_STRING_KEYS = {"minLength", "maxLength"}

    @staticmethod
    def _negate_if_constraints(if_schema: SchemaT) -> SchemaT:
        """
        Invert simple keyword constraints from an ``if`` schema.

        Returns a schema whose constraints are the logical negation of
        the if-schema's keyword constraints.  Only handles flat numeric
        and string-length keywords; complex or nested schemas return
        an empty dict (best-effort).
        """
        negated: SchemaT = {}
        for key, val in if_schema.items():
            if key == "type":
                continue
            elif key == "minimum":
                negated["exclusiveMaximum"] = val
            elif key == "maximum":
                negated["exclusiveMinimum"] = val
            elif key == "exclusiveMinimum":
                negated["maximum"] = val
            elif key == "exclusiveMaximum":
                negated["minimum"] = val
            elif key == "minLength":
                if val > 0:
                    negated["maxLength"] = val - 1
            elif key == "maxLength":
                negated["minLength"] = val + 1
            else:
                # Can't negate complex keywords — skip
                return {}
        return negated

    def _apply_if_then_else(self, schema: SchemaT) -> SchemaT:
        """
        Apply if/then/else by randomly choosing a branch.

        Randomly decide whether to satisfy the ``if`` condition.  When
        satisfied, merge both the ``if`` condition and ``then`` constraints
        into the schema so the generated value satisfies the if-condition.
        When not satisfied, merge the negation of the ``if`` condition and
        the ``else`` constraints.  The ``if``, ``then``, and ``else``
        keys are stripped from the returned schema.

        Merging uses :func:`_merge_schemas` (the same logic as ``allOf``)
        when both sides share a ``type``, giving proper constraint
        intersection (``max(minimum)``, ``min(maximum)``, deep property
        merge, etc.).  Falls back to shallow key-level merge when the
        base schema has no ``type``.
        """
        result = {k: v for k, v in schema.items() if k not in ("if", "then", "else")}
        if_schema = schema.get("if", {})
        then_schema = schema.get("then", {})
        else_schema = schema.get("else", {})

        # randomly choose to satisfy the if-condition or not
        satisfy_if = self.generator.random_int(0, 1)

        if satisfy_if:
            # Merge if-condition + then-branch so value satisfies the if
            branches = [s for s in [if_schema, then_schema] if s]
        else:
            # Merge negated if-condition + else-branch
            negated_if = self._negate_if_constraints(if_schema) if if_schema else {}
            branches = [s for s in [negated_if, else_schema] if s]

        if not branches:
            return result

        base_type = result.get("type")
        for branch in branches:
            if base_type is not None and not isinstance(base_type, list):
                branch_with_type = {"type": base_type, **branch}
                try:
                    result = _merge_schemas(result, branch_with_type)
                except (UnsatisfiableConstraintsError, KeyError):
                    result = self._shallow_merge_branch(result, branch)
            else:
                result = self._shallow_merge_branch(result, branch)

        return result

    @staticmethod
    def _shallow_merge_branch(base: SchemaT, branch: SchemaT) -> SchemaT:
        """
        Merge *branch* into *base* with shallow dict/list handling.

        Used as a fallback when :func:`_merge_schemas` cannot be applied
        (e.g., no ``type`` on the base schema).
        """
        result = dict(base)
        for key, val in branch.items():
            if key in result:
                existing = result[key]
                if isinstance(existing, dict) and isinstance(val, dict):
                    existing_copy = existing.copy()
                    existing_copy.update(val)
                    result[key] = existing_copy
                elif isinstance(existing, list) and isinstance(val, list):
                    result[key] = list(set(existing) | set(val))
                else:
                    result[key] = val
            else:
                result[key] = val
        return result

    def _resolve_ref(self, schema: SchemaT) -> SchemaT:
        """
        Resolve a ``$ref`` against the root schema's ``$defs``/``definitions``.

        If the reference is a JSON pointer of the form ``#/$defs/<name>`` or
        ``#/definitions/<name>``, look into the root schema stored on
        ``Context``.  Any keys in *schema* alongside ``$ref`` are merged into
        the resolved schema (per draft 2019-09+, keywords may appear next to
        ``$ref``).

        Circular references are detected via a ref stack on the context.
        When a circular ref is detected at or beyond max_depth, an
        UnsatisfiableConstraintsError is raised instead of recursing.
        """
        ref = schema["$ref"]
        root = self.context._root_schema
        if root is None:
            raise UnsatisfiableConstraintsError(
                f"Cannot resolve $ref {ref!r}: no root schema available."
            )

        # Detect circular $ref: if we've already seen this ref in the
        # current resolution chain AND we're well beyond max_depth,
        # stop to prevent infinite recursion.  We use a generous limit
        # (3x max_depth) because optional circular refs legitimately
        # recurse a few times before depth limiting kicks in.
        if ref in self.context._ref_stack and self.context._depth >= self.context.max_depth * 3:
            raise UnsatisfiableConstraintsError(
                f"Circular $ref {ref!r} detected at depth "
                f"{self.context._depth} (max_depth={self.context.max_depth})."
            )

        resolved = None
        if ref.startswith("#/"):
            # walk the JSON pointer
            pointer = ref[2:].split("/")
            target = root
            for part in pointer:
                target = target.get(part) if isinstance(target, dict) else None
                if target is None:
                    break
            if target is not None and isinstance(target, dict):
                resolved = target

        if resolved is None:
            raise UnsatisfiableConstraintsError(f"Cannot resolve $ref {ref!r}.")

        # Merge sibling keywords alongside $ref (draft 2019-09+)
        extra = {k: v for k, v in schema.items() if k != "$ref"}
        if extra:
            resolved_type = resolved.get("type")
            if resolved_type and not isinstance(resolved_type, list):
                extra_with_type = {"type": resolved_type, **extra}
                try:
                    resolved = _merge_schemas(resolved, extra_with_type)
                except UnsatisfiableConstraintsError:
                    resolved = {**resolved, **extra}
            else:
                resolved = self._shallow_merge_branch(resolved, extra)

        return resolved

    def descend_into(self, f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            self.context._depth += 1
            try:
                return f(*args, **kwargs)
            finally:
                self.context._depth -= 1

        return wrapped

    @property
    def context(self) -> Context:
        if self._context is None:
            self._context = Context()
        return self._context

    @context.setter
    def context(self, context: Context):
        self._context = context

    def from_jsonschema(self, schema: SchemaT, **context):
        self._context = Context(**context)
        # Store root schema for $ref resolution
        if isinstance(schema, dict):
            self.context._root_schema = schema
        try:
            return self._from_schema(schema)
        finally:
            self._context = None
