import inspect
import itertools
import json
import math
import operator
import re
import sys
import warnings
from base64 import b64encode
from dataclasses import dataclass
from decimal import Decimal
from enum import auto, Enum
from functools import partial, reduce, wraps
from numbers import Number
from random import shuffle
from typing import (
    Callable,
    Dict,
    Final,
    FrozenSet,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import js_regex
import pytz
from jsonschema import validate, ValidationError
from faker.providers import BaseProvider
from hypothesis import strategies as st
from wrapt import ObjectProxy

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


class TypeName(str, Enum):
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


StrT = Union[str, bytes]

JsonT = Union[StrT, int, float, bool, None, List["JsonT"], Dict[str, "JsonT"]]

SchemaT = Dict[str, JsonT]

type_getter = operator.itemgetter("type")


@dataclass
class StringFormat:
    length_type: LengthType
    lengths: Optional[Union[Iterable[int], range]] = None
    return_type: StrT = str

    def validate_constraints(self, min_length: int, max_length: Optional[int]) -> bool:
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
                        len_ >= min_length
                        and (max_length is None or len_ <= max_length)
                        for len_ in self.lengths
                    )
                start = self.lengths.start
                stop = self.lengths.stop
                step = self.lengths.step
                if min_length <= start:
                    nearest_to_min = start
                else:
                    nearest_to_min = start + (
                        ((min_length - start + step - 1) // step) * step
                    )
                if nearest_to_min >= stop:
                    return False
                if max_length is not None and nearest_to_min > max_length:
                    return False
                return True
            else:
                return all(
                    len_ >= min_length and (max_length is None or len_ <= max_length)
                    for len_ in self.lengths
                )
        else:
            # UNCONSTRAINED means examples can be any length, we will have
            # to brute-force search for a matching example
            if self.length_type is LengthType.UNCONSTRAINED and max_length == 0:
                # I'm guessing that most UNCONSTRAINED generators will never
                # generate an empty string
                return False
            return True


class JsonVal(ObjectProxy):
    """
    "At last, I can put a dict in a set..."
    """

    def __init__(self, val: JsonT):
        super().__init__(val)
        self._self_hash = hash(json.dumps(val))

    def __hash__(self) -> int:
        return self._self_hash


EnumVal = TypeVar("EnumVal", bound=JsonT)


class JsonEnum(FrozenSet[JsonVal]):
    def __new__(cls, values: Iterable[EnumVal]) -> "JsonEnum[EnumVal]":
        return super().__new__(cls, (JsonVal(val) for val in values))


def nullable_or_enum(f):
    """
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
    _root_schema: Optional[SchemaT] = None


L = TypeVar("L", bound=JsonT)
R = TypeVar("R", bound=JsonT)


def _merge_constraint(
    left: Optional[L],
    right: Optional[R],
    resolver: Callable[[L, R], Union[L, R]],
) -> Optional[JsonT]:
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


def _resolve_equal_or_error(left: L, right: R) -> L:
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


def _resolve_properties(
    left: Dict[str, SchemaT], right: Dict[str, SchemaT]
) -> Dict[str, SchemaT]:
    properties = left.copy()
    for name, schema in right.items():
        if name in left:
            properties[name] = _merge_schemas(left[name], schema)
        else:
            properties[name] = schema
    return properties


def _resolve_additional_properties(
    left: Union[bool, SchemaT], right: Union[bool, SchemaT]
) -> Union[bool, SchemaT]:
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
    left: Dict[str, List[str]], right: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    merged = left.copy()
    for key, deps in right.items():
        if key in merged:
            merged[key] = list(set(merged[key]) | set(deps))
        else:
            merged[key] = deps
    return merged


def _resolve_dependent_schemas(
    left: Dict[str, SchemaT], right: Dict[str, SchemaT]
) -> Dict[str, SchemaT]:
    merged = left.copy()
    for key, schema in right.items():
        if key in merged:
            merged[key] = _merge_schemas(merged[key], schema)
        else:
            merged[key] = schema
    return merged


def _merge_schemas(left: SchemaT, right: SchemaT) -> SchemaT:
    assert left["type"] == right["type"]
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


def _resolve_prefix_items(left: List[SchemaT], right: List[SchemaT]) -> List[SchemaT]:
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

    def kwargs_from_schema(schema: SchemaT) -> Dict[str, JsonT]:
        kwargs = {}
        for arg, getter in getters.items():
            try:
                kwargs[arg] = getter(schema)
            except KeyError:
                pass
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
            length_type=LengthType.UNCONSTRAINED,
        ),
        "uuid": StringFormat(
            length_type=LengthType.FIXED,
            # a1a88cbb-7634-4504-a454-7bb8aec36a1e
            lengths=[36],
        ),
        "uri": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "hostname": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
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
            length_type=LengthType.UNCONSTRAINED,
        ),
        "uri-reference": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "uri-template": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "iri": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "iri-reference": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "idn-email": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "idn-hostname": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "json-pointer": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "relative-json-pointer": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
        "regex": StringFormat(
            length_type=LengthType.UNCONSTRAINED,
        ),
    }

    FLOAT_OFFSET: Final = float("0.{}1".format("0" * (sys.float_info.dig - 2)))

    BASE_METHOD_MAP = {
        type_name: "jsonschema_{}".format(type_name.value.lower())
        for type_name in TypeName
    }

    _context: Context = None

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
        return self.generator.password(length=length)

    def _format_byte(self, min_length: int, max_length: int) -> bytes:
        """
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

    def _format_binary(self, length: int) -> bytes:
        return self.generator.binary(length=length)

    def _format_email(self) -> str:
        return self.generator.email()

    def _format_uuid(self) -> str:
        return self.generator.uuid4()

    def _format_uri(self) -> str:
        return self.generator.uri()

    def _format_hostname(self) -> str:
        return self.generator.hostname()

    def _format_ipv4(self) -> str:
        return self.generator.ipv4()

    def _format_ipv6(self) -> str:
        return self.generator.ipv6()

    def _format_time(self) -> str:
        """RFC 3339 §5.6 full-time, e.g. '17:32:28+00:00'."""
        t = self.generator.time(pattern="%H:%M:%S")
        tz = pytz.timezone(self.generator.timezone())
        import datetime

        offset = tz.utcoffset(datetime.datetime.now())
        if offset is None or offset == datetime.timedelta(0):
            return f"{t}Z"
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{t}{sign}{hours:02d}:{minutes:02d}"

    def _format_duration(self) -> str:
        """ISO 8601 / RFC 3339 Appendix A duration, e.g. 'P3Y6M4DT12H30M5S'."""
        parts = []
        years = self.generator.random_int(0, 10)
        months = self.generator.random_int(0, 11)
        days = self.generator.random_int(0, 30)
        hours = self.generator.random_int(0, 23)
        minutes = self.generator.random_int(0, 59)
        seconds = self.generator.random_int(0, 59)
        if years:
            parts.append(f"{years}Y")
        if months:
            parts.append(f"{months}M")
        if days:
            parts.append(f"{days}D")
        time_parts = []
        if hours:
            time_parts.append(f"{hours}H")
        if minutes:
            time_parts.append(f"{minutes}M")
        if seconds:
            time_parts.append(f"{seconds}S")
        date_part = "".join(parts)
        time_part = "T" + "".join(time_parts) if time_parts else ""
        result = f"P{date_part}{time_part}"
        if result == "P":
            result = "PT0S"
        return result

    def _format_uri_reference(self) -> str:
        """URI-reference: either a URI or a relative-reference."""
        if self.generator.random_int(0, 1):
            return self.generator.uri()
        # relative reference
        path = "/".join(
            self.generator.pystr(min_chars=1, max_chars=8)
            for _ in range(self.generator.random_int(1, 4))
        )
        return f"/{path}"

    def _format_uri_template(self) -> str:
        """RFC 6570 URI Template, e.g. 'https://example.com/{id}'."""
        base = self.generator.uri()
        var_name = self.generator.pystr(min_chars=2, max_chars=8)
        return f"{base}{{{var_name}}}"

    def _format_iri(self) -> str:
        """IRI (RFC 3987). ASCII URIs are valid IRIs."""
        return self.generator.uri()

    def _format_iri_reference(self) -> str:
        """IRI-reference (RFC 3987). Reuse uri-reference logic."""
        return self._format_uri_reference()

    def _format_idn_email(self) -> str:
        """Internationalized email (RFC 6531). ASCII is a valid subset."""
        return self.generator.email()

    def _format_idn_hostname(self) -> str:
        """Internationalized hostname (RFC 5890). ASCII is a valid subset."""
        return self.generator.hostname()

    def _format_json_pointer(self) -> str:
        """RFC 6901 JSON Pointer, e.g. '/foo/bar/0'."""
        segments = [
            self.generator.pystr(min_chars=1, max_chars=8)
            for _ in range(self.generator.random_int(1, 5))
        ]
        return "/" + "/".join(segments)

    def _format_relative_json_pointer(self) -> str:
        """Relative JSON Pointer, e.g. '1/foo/bar'."""
        prefix = str(self.generator.random_int(0, 9))
        if self.generator.random_int(0, 1):
            segments = [
                self.generator.pystr(min_chars=1, max_chars=8)
                for _ in range(self.generator.random_int(1, 4))
            ]
            return prefix + "/" + "/".join(segments)
        return prefix + "#"

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
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        format_: Optional[str] = None,
        content_encoding: Optional[str] = None,
        content_media_type: Optional[str] = None,
    ) -> StrT:
        """
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
                and it seems useful behaviour)

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
        # When contentEncoding is "base64", generate base64-encoded content
        if content_encoding is not None:
            if content_encoding.lower() == "base64":
                return self._format_byte(
                    min_length=min_length,
                    max_length=max_length if max_length is not None else 255,
                )
            # For unknown encodings, fall through to normal generation

        def is_valid(val) -> bool:
            if len(val) < min_length:
                return False
            if max_length is not None and len(val) > max_length:
                return False
            return True

        T = TypeVar("T")

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
            # Use from_regex strategy with .example() for varied output;
            # hypothesis.find() shrinks to minimal examples which is not
            # suitable for data generation (always produces same value).
            regex_st = st.from_regex(re.compile(pattern))
            if max_length is not None:
                regex_st = regex_st.filter(lambda s: len(s) <= max_length)
            if min_length > 0:
                regex_st = regex_st.filter(lambda s: len(s) >= min_length)
            for _ in range(self.context.max_search):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        example = regex_st.example()
                except Exception:
                    break
                if is_valid(example):
                    return example
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
                            f"maxLength: {max_length} after {self.context.max_search} attempts."
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
                            f"maxLength: {max_length} after {self.context.max_search} attempts."
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

    def better_pyfloat(
        self, min_value: Optional[float], max_value: Optional[float]
    ) -> float:
        """
        `faker.pyfloat` only supports int for min and max value
        """
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

    def _safe_random_int(self, min_value: Optional[int], max_value: Optional[int]):
        """
        This method exists in faker/providers/python/__init__.py
        but it's not available in our provider because it's named as private

        Also: https://github.com/joke2k/faker/issues/1152  (fixed here)
        """
        if None not in (min_value, max_value) and min_value == max_value:
            return min_value
        orig_min_value = min_value
        orig_max_value = max_value

        if min_value is None and max_value is None:
            a, b = self.random_int(), self.random_int()
            min_value = min(a, b)
            max_value = max(a, b)
        elif min_value is None:
            min_value = max_value - self.random_int()
        elif max_value is None:
            max_value = min_value + self.random_int()

        if min_value == max_value:
            return self._safe_random_int(orig_min_value, orig_max_value)
        else:
            return self.random_int(min_value, max_value - 1)

    def _jsonschema_number(
        self,
        mode: NumberMode,
        minimum: Optional[Number] = None,
        maximum: Optional[Number] = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: Optional[Number] = None,
        exclusive_maximum: Optional[Number] = None,
        multiple_of: Optional[Number] = None,
    ) -> Number:
        if mode is NumberMode.FLOAT:

            def _make_safe(val):
                return Decimal(str(val)) if val is not None else val

            _cast: Final = float
            _offset: Final = self.FLOAT_OFFSET
            _generator: Final = self.better_pyfloat
        elif mode is NumberMode.INTEGER:

            def _make_safe(val):
                return val

            _cast: Final = int
            _offset: Final = 1
            _generator: Final = self._safe_random_int
        else:
            raise TypeError(mode)

        # TODO:
        # https://json-schema.org/draft-07/json-schema-validation.html#rfc.section.6.2.1
        # multiple_of must be > 0

        # Draft-06+ numeric exclusiveMinimum/exclusiveMaximum
        # These take precedence over the draft-04 boolean form
        if exclusive_minimum is not None:
            minimum = exclusive_minimum
            exclusive_min = True
        if exclusive_maximum is not None:
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
            offset = _offset
            if val < 0:
                offset = 0 - offset
            return op(val, offset)

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
            if (
                multiple_of is not None
                and Decimal(str(minimum)) % Decimal(str(multiple_of)) != 0
            ):
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
                raise StopIteration(
                    "Could not find a valid minimum and maximum in 100 iterations",
                    minimum,
                    maximum,
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

        def get_range() -> Tuple[int, int]:
            low = safe_min / multiple_of
            high = safe_max / multiple_of
            low, high = sorted((low, high))
            return math.ceil(low), math.floor(high)

        low, high = get_range()
        multiple = self.generator.random_int(low, high)
        return _cast(_make_safe(multiple) * multiple_of)

    def jsonschema_number(
        self,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: Optional[float] = None,
        exclusive_maximum: Optional[float] = None,
        multiple_of: Optional[float] = None,
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
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        exclusive_minimum: Optional[int] = None,
        exclusive_maximum: Optional[int] = None,
        multiple_of: Optional[int] = None,
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
        Group all schemas by type. Randomly choose a type.
        Randomly combine one or more of the given schemas of that type
        according to the rules for `allOf`.
        """
        schema_map = {
            k: list(v)
            for k, v in itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        }
        type_ = self.generator.random_element(schema_map.keys())
        type_schemas = schema_map[type_]
        sub_schemas = self.generator.random_sample(type_schemas, length=None)
        schema = compound_schema(sub_schemas)
        return self._from_schema(schema)

    def jsonschema_allof(self, schemas: Iterable[JsonT]) -> JsonT:
        """
        Make a compound schema from all members and return an object
        satisfying that.

        Even the spec says:
        "Note that it’s quite easy to create schemas that are logical
        impossibilities..."
        I think all mixed-type cases are impossible to satisfy (?)

        If they are all the same type we should AND their validation
        restrictions together and return for that.
        """
        schema_map = {
            k: list(v)
            for k, v in itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        }
        if len(schema_map) > 1:
            raise UnsatisfiableConstraintsError(
                f"Cannot satisfy allOf multiple types: {set(schema_map.keys())}"
            )
        schema = compound_schema(schemas)
        return self._from_schema(schema)

    def _random_type_method(self) -> Tuple[TypeName, Callable]:
        if self.context._depth < self.context.max_depth:
            types = BASIC_TYPES
        else:
            types = FLAT_TYPES
        type_ = self.generator.random_element(types)
        generator = getattr(self, self.BASE_METHOD_MAP[type_])
        if type_ in NESTED_TYPES:
            # TODO: I think in some cases we're double descending here
            # (i.e. the caller of `_random_type_method` already descended)
            generator = self.descend_into(generator)
        return type_, generator

    def jsonschema_any(self) -> JsonT:
        """
        We should generate a random element of any type. No restrictions.
        """
        _, generator = self._random_type_method()
        return generator()

    def jsonschema_not(self, schema: SchemaT) -> JsonT:
        """
        We should generate a random element of any type.

        If the randomly chosen type is the same type as the passed schema then
        check that it does not match the passed schema, if so regenerate.
        (Is this what the spec intended? I think it must be because that is
        what makes most sense from a validation-centric point of view)

        Raises:
            NoExampleFoundError
        """

        def is_valid(val) -> bool:
            try:
                validate(val, schema)
            except ValidationError:
                return False
            return True

        T = TypeVar("T")

        def search(generator: Callable[..., T]) -> T:
            for _ in range(self.context.max_search):
                example = generator()
                if not is_valid(example):
                    # we found a usable example
                    break
            else:
                raise NoExampleFoundError
            return example

        type_, generator = self._random_type_method()

        if type_ == schema["type"]:
            try:
                return search(generator)
            except NoExampleFoundError as e:
                raise NoExampleFoundError(
                    f"Unable to generate any random value that matches "
                    f"not: /{schema}/ after {self.context.max_search} attempts."
                ) from e
        else:
            return generator()

    def _get_collection_max(self, min_: int):
        if min_ > self.context.default_collection_max:
            return self.generator.random_int(
                min_, min_ + self.context.default_collection_max
            )
        else:
            return self.generator.random_int(min_, self.context.default_collection_max)

    def jsonschema_array(
        self,
        items: Optional[SchemaT] = None,
        prefix_items: Optional[List[SchemaT]] = None,
        additional_items: Optional[Union[bool, SchemaT]] = None,
        unevaluated_items: Optional[Union[bool, SchemaT]] = None,
        contains: Optional[SchemaT] = None,
        min_contains: Optional[int] = None,
        max_contains: Optional[int] = None,
        min_items: int = 0,
        max_items: Optional[int] = None,
        unique_items: bool = False,
    ) -> List[JsonT]:
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
        remaining_schema: Optional[SchemaT] = None
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

        # Ensure we have at least enough items for prefix
        effective_min = max(min_items, n_prefix) if prefix_items else min_items

        count = self._safe_random_int(effective_min, max_items)

        # Generate prefix items
        generated = []
        for i in range(min(count, n_prefix)):
            item = self.descend_into(self._from_schema)(prefix_items[i])
            generated.append(item)

        # Generate remaining items
        remaining_count = count - len(generated)
        if remaining_count > 0 and remaining_schema is not None:
            dup_count = 0
            actual_count = remaining_count
            if not unique_items and actual_count > 1:
                dup_count = self.generator.random_int(0, actual_count // 2)
                actual_count -= dup_count

            remaining = []
            duplicates = []
            for _ in range(actual_count * 3):  # allow retries for uniqueness
                item = self.descend_into(self._from_schema)(remaining_schema)
                if unique_items and (item in generated or item in remaining):
                    if not unique_items and len(duplicates) < dup_count:
                        duplicates.append(item)
                else:
                    remaining.append(item)
                if len(remaining) >= actual_count:
                    break

            if not unique_items:
                if len(duplicates) < dup_count and remaining:
                    diff = dup_count - len(duplicates)
                    top_up = self.generator.random_sample(remaining, length=diff)
                    duplicates.extend(top_up)
                remaining.extend(duplicates)
                shuffle(remaining)

            generated.extend(remaining)
        elif remaining_count > 0 and remaining_schema is None and not prefix_items:
            # No schema: generate random items
            dup_count = 0
            actual_count = remaining_count
            if not unique_items and actual_count > 1:
                dup_count = self.generator.random_int(0, actual_count // 2)
                actual_count -= dup_count

            remaining = []
            duplicates = []
            for _ in range(actual_count):
                type_, _ = self._random_type_method()
                item_schema = {"type": type_.value}
                item = self.descend_into(self._from_schema)(item_schema)
                if unique_items and (item in generated or item in remaining):
                    if not unique_items and len(duplicates) < dup_count:
                        duplicates.append(item)
                else:
                    remaining.append(item)

            if not unique_items:
                if len(duplicates) < dup_count and remaining:
                    diff = dup_count - len(duplicates)
                    top_up = self.generator.random_sample(remaining, length=diff)
                    duplicates.extend(top_up)
                remaining.extend(duplicates)
                shuffle(remaining)

            generated.extend(remaining)

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
                    generated[i] = self.descend_into(self._from_schema)(
                        unevaluated_items
                    )

        # Handle contains: ensure the array has items matching the contains schema
        if contains is not None:
            effective_min_contains = min_contains if min_contains is not None else 1
            effective_max_contains = max_contains

            # Count how many already match
            matching_count = 0
            for item in generated:
                try:
                    validate(item, contains)
                    matching_count += 1
                except ValidationError:
                    pass

            # Add items to satisfy minContains
            while matching_count < effective_min_contains:
                if max_items is not None and len(generated) >= max_items:
                    break
                item = self.descend_into(self._from_schema)(contains)
                generated.append(item)
                matching_count += 1

            # Remove excess matches to satisfy maxContains
            if (
                effective_max_contains is not None
                and matching_count > effective_max_contains
            ):
                excess = matching_count - effective_max_contains
                # Replace some matching items with non-matching ones
                for i in range(len(generated) - 1, -1, -1):
                    if excess <= 0:
                        break
                    try:
                        validate(generated[i], contains)
                    except ValidationError:
                        continue
                    # Replace with a random item that doesn't match
                    if remaining_schema is not None:
                        generated[i] = self.descend_into(self._from_schema)(
                            remaining_schema
                        )
                        excess -= 1

        return generated

    def jsonschema_object(
        self,
        properties: Optional[Dict[str, SchemaT]] = None,
        pattern_properties: Optional[Dict[str, SchemaT]] = None,
        property_names: Optional[SchemaT] = None,
        required: Optional[List[str]] = None,
        additional_properties: Union[bool, SchemaT] = True,
        unevaluated_properties: Union[bool, SchemaT, None] = None,
        min_properties: int = 0,
        max_properties: Optional[int] = None,
        dependent_required: Optional[Dict[str, List[str]]] = None,
        dependent_schemas: Optional[Dict[str, SchemaT]] = None,
    ) -> Dict[str, JsonT]:
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
        if (
            max_properties is not None
            and required is not None
            and max_properties < len(required)
        ):
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

        og_max_properties = max_properties
        properties = properties or {}
        pattern_properties = pattern_properties or {}
        required_set = set(required or [])
        generated = {}

        def _schema_for_key(attr: str) -> SchemaT:
            """Determine the schema for a property key.

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

        def generate_values(attrs: Iterable[str]) -> None:
            for attr in attrs:
                schema = _schema_for_key(attr)
                val = self.descend_into(self._from_schema)(schema)
                generated[attr] = val

        # generate 'required' properties
        if required_set:
            generate_values(required_set)

        if max_properties is None:
            max_properties = self._get_collection_max(
                max(min_properties, len(required_set))
            )

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
                    generate_values(sampled_non_required)
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
                except Exception:
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
            _val_schema = (
                additional_properties if isinstance(additional_properties, dict) else {}
            )
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
                            generated[dep] = self.descend_into(self._from_schema)(
                                schema
                            )

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
                            generated[dep_key] = self.descend_into(self._from_schema)(
                                sub
                            )
                        elif dep_key in dep_props:
                            # re-generate to match the dependent schema
                            sub = dep_props[dep_key]
                            generated[dep_key] = self.descend_into(self._from_schema)(
                                sub
                            )

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
                    generated[k] = self.descend_into(self._from_schema)(
                        unevaluated_properties
                    )

        return generated

    @nullable_or_enum
    def _jsonschema_basic_type_from_schema(
        self, schema: SchemaT, type_: TypeName
    ) -> JsonT:
        method = getattr(self, self.BASE_METHOD_MAP[type_])
        return method(**method.kwargs_from_schema(schema))

    @nullable_or_enum
    def _jsonschema_compound_type_from_schema(
        self, schema: SchemaT, type_: TypeName
    ) -> JsonT:
        return getattr(self, self.BASE_METHOD_MAP[type_])(schema[type_.value])

    @nullable_or_enum
    def _jsonschema_any_from_schema(self, _: SchemaT) -> Optional[JsonT]:
        # NOTE: `any` can still be `nullable` (...or `enum`?)
        # NOTE: `nullable_or_enum` needs the schema arg
        return self.jsonschema_any()

    def _from_schema(self, schema: SchemaT):
        """
        IMPORTANT:
        All recursive calls should use this private method instead of the
        public `from_schema` below so that `context._depth` is not reset.
        """
        # Handle boolean schemas (draft-06+)
        if schema is True or schema == {}:
            return self.jsonschema_any()
        if schema is False:
            raise UnsatisfiableConstraintsError(
                "Boolean schema 'false' rejects all instances."
            )

        # Handle $ref resolution
        if "$ref" in schema:
            schema = self._resolve_ref(schema)

        # Handle const (draft-06+)
        if "const" in schema:
            return schema["const"]

        # Handle if/then/else: randomly choose a branch and merge it
        if "if" in schema:
            schema = self._apply_if_then_else(schema)

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

    def _apply_if_then_else(self, schema: SchemaT) -> SchemaT:
        """Apply if/then/else by randomly choosing a branch.

        Randomly decide whether to satisfy the ``if`` condition.  When
        satisfied and ``then`` is present, merge ``then`` constraints into
        the schema.  When not satisfied and ``else`` is present, merge
        ``else`` constraints instead.  The ``if``, ``then``, and ``else``
        keys are stripped from the returned schema.
        """
        result = {k: v for k, v in schema.items() if k not in ("if", "then", "else")}
        then_schema = schema.get("then", {})
        else_schema = schema.get("else", {})

        # randomly choose to satisfy the if-condition or not
        satisfy_if = self.generator.random_int(0, 1)

        branch = then_schema if satisfy_if else else_schema
        if branch:
            # merge branch constraints into the base schema
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
        """Resolve a ``$ref`` against the root schema's ``$defs``/``definitions``.

        If the reference is a JSON pointer of the form ``#/$defs/<name>`` or
        ``#/definitions/<name>``, look into the root schema stored on
        ``Context``.  Any keys in *schema* alongside ``$ref`` are merged into
        the resolved schema (per draft 2019-09+, keywords may appear next to
        ``$ref``).
        """
        ref = schema["$ref"]
        root = self.context._root_schema
        if root is None:
            raise UnsatisfiableConstraintsError(
                f"Cannot resolve $ref {ref!r}: no root schema available."
            )

        resolved = None
        if ref.startswith("#/"):
            # walk the JSON pointer
            pointer = ref[2:].split("/")
            target = root
            for part in pointer:
                if isinstance(target, dict):
                    target = target.get(part)
                else:
                    target = None
                if target is None:
                    break
            if target is not None and isinstance(target, dict):
                resolved = target

        if resolved is None:
            raise UnsatisfiableConstraintsError(f"Cannot resolve $ref {ref!r}.")

        # Merge sibling keywords alongside $ref (draft 2019-09+)
        extra = {k: v for k, v in schema.items() if k != "$ref"}
        if extra:
            resolved = {**resolved, **extra}

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
    def _(self, context: Context):
        self._context = context

    def from_schema(self, schema: SchemaT, **context):
        self._context = Context(**context)
        # Store root schema for $ref resolution
        if isinstance(schema, dict):
            self.context._root_schema = schema
        try:
            return self._from_schema(schema)
        finally:
            self._context = None
