import inspect
import itertools
import json
import math
import operator
import re
import sys
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
    FrozenSet,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import pytz
from jsonschema import validate, ValidationError
from faker.providers import BaseProvider
from hypothesis import strategies as st
from typing_extensions import Final
from wrapt import ObjectProxy

from .utils import intinf

"""
TODO: rename as OpenAPI


string (this includes dates and files) TODO: generate picture files
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


class UnsatisfiableConstraintsError(Exception):
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

    def validate_constraints(
        self, min_length: int, max_length: Optional[int]
    ) -> bool:
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
                if min_length > self.lengths.start:
                    return False
                # min_length is valid...
                if max_length is None or max_length >= self.lengths.stop:
                    return True
                offset = self.lengths.start % self.lengths.step
                nearest_to_min = (
                    min_length
                    + offset
                    - (min_length % self.lengths.stop)
                )
                max_reachable = (
                    self.lengths.stop
                    + offset
                    - (self.lengths.stop % self.lengths.step)
                    - (self.lengths.step
                        if self.lengths.stop in self.lengths
                        else 0)
                )
                return (
                    max_length >= nearest_to_min and
                    max_length >= max_reachable
                )
            else:
                return all(
                    len_ >= min_length and (
                        max_length is None or len_ <= max_length)
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
        return super().__new__(JsonVal(val) for val in values)


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
    max_search: Final[int] = 1250
    default_collection_max: Final[int] = 50


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


def _merge_schemas(left: SchemaT, right: SchemaT) -> SchemaT:
    assert left["type"] == right["type"]
    type_ = TypeName(left["type"])
    attr_map = TYPE_ATTR_MERGE_RESOLVERS[type_]
    merged = left.copy()
    for attr, resolver in attr_map.items():
        left = left.get(attr)
        right = right.get(attr)
        try:
            val = _merge_constraint(left, right, resolver)
        except UnsatisfiableConstraintsError as e:
            raise UnsatisfiableConstraintsError(
                "Cannot merge incompatible constraints "
                f"type: {type_}, "
                f"{attr}: {left} & {attr}: {right}"
            ) from e
        merged[attr] = val
    return merged


_numeric_attr_merge_funcs = {
    "minimum": max,
    "maximum": min,
    "exclusiveMin": operator.or_,
    "exclusiveMax": operator.or_,
    "multipleOf": _resolve_multiple_of,
}

TYPE_ATTR_MERGE_RESOLVERS = {
    TypeName.ARRAY: {
        "items": _merge_schemas,  # NOTE: relies on OpenAPI homogenous arrays
        "minItems": max,
        "maxItems": min,
        "uniqueItems": operator.or_,
    },
    TypeName.OBJECT: {
        "properties": _resolve_properties,
        "propertyNames": _merge_schemas,
        "required": lambda l, r: list(set(l) | set(r)),
        "additionalProperties": operator.or_,
        "minProperties": max,
        "maxProperties": min,
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
        arg: operator.itemgetter(
            re.sub(snake_case, to_camel_case, arg).rstrip("_")
        )
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
        # `jsonschema_basic_type_from_schema`
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
            # returned length is a multiple of 4
            lengths=range(0, intinf, 4),
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
    }

    FLOAT_OFFSET: Final = float("0.{}1".format("0" * (sys.float_info.dig - 2)))

    BASE_METHOD_MAP = {
        type_name: "jsonschema_{}".format(type_name.value)
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
        if max_length == 0:
            # b64encode(b'') == b''
            return b""
        original = self.generator.pystr(
            min_chars=min_length, max_chars=max_length
        )
        return b64encode(original.encode())

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

    def jsonschema_string(
        self,
        min_length: int = 0,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        format_: Optional[str] = None,
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

        def is_valid(val) -> bool:
            if len(val) < min_length:
                return False
            if max_length is not None and len(val) > max_length:
                return False
            return True

        T = TypeVar("T")

        def search(generator: Callable[..., T]) -> T:
            for _ in range(self._context.max_search):
                example = generator()
                if is_valid(example):
                    break
            else:
                raise NoExampleFoundError
            return example

        if pattern is not None:
            # (returns early)
            # NOTE: `format` is ignored if `pattern` is given
            regex_st = st.from_regex(pattern)
            try:
                # TODO suppress warning from Hypothesis
                return search(regex_st.example)
            except NoExampleFoundError as e:
                raise NoExampleFoundError(
                    f"Unable to generate any random value that matches "
                    f"pattern: /{pattern}/ and minLength: {min_length}, "
                    f"maxLength: {max_length} after {self._context.max_search} attempts."
                ) from e
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
                            f"maxLength: {max_length} after {self._context.max_search} attempts."
                        ) from e
            else:
                if not format_type.validate_constraints(min_length, max_length):
                    raise UnsatisfiableConstraintsError(
                        f"Constraints minLength: {min_length}, maxLength: "
                        f"{max_length} are incompatible with format: {format_}."
                    )

                method = getattr(
                    self, "_format_{}".format(format_.replace("-", "_"))
                )
                if format_type.length_type is LengthType.FIXED:
                    return method()
                elif format_type.length_type is LengthType.VARIABLE_SINGULAR:
                    return method(
                        length=self._safe_random_int(min_length, max_length)
                    )
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
                            f"maxLength: {max_length} after {self._context.max_search} attempts."
                        ) from e

        if max_length is None or (max_length and max_length > 20):
            # (returns early)
            # use the "lorem ipsum" provider
            # (...has a min length generatable of 5 chars)
            generator = partial(
                self.generator.text,
                max_nb_chars=max_length if max_length is not None else 255
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
            raise ValueError('min_value cannot be greater than max_value')
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
            minimum = min(offset_val(minimum, operator.add), maximum)
        if exclusive_max and maximum is not None:
            maximum = max(offset_val(maximum, operator.sub), minimum)

        safe_min = _make_safe(minimum)
        safe_max = _make_safe(maximum)

        if minimum is not None and minimum == maximum:
            # (returns early)
            if (
                multiple_of is not None and
                Decimal(str(minimum)) % Decimal(str(multiple_of)) != 0
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
                (safe_min % multiple_of == 0 and not exclusive_min) or
                (safe_max % multiple_of == 0 and not exclusive_max) or
                int(safe_min / multiple_of) != int(safe_max / multiple_of)
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

            for i in range(100):
                set_missing()
                if valid_range():
                    break
            else:
                raise StopIteration(
                    f"Could not find a valid minimum and maximum in 100 iterations",
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
        multiple_of: Optional[float] = None,
    ) -> float:
        return self._jsonschema_number(
            mode=NumberMode.FLOAT,
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
            multiple_of=multiple_of,
        )

    def jsonschema_integer(
        self,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
        exclusive_min: bool = False,
        exclusive_max: bool = False,
        multiple_of: Optional[int] = None,
    ) -> int:
        return self._jsonschema_number(
            mode=NumberMode.INTEGER,
            minimum=minimum,
            maximum=maximum,
            exclusive_min=exclusive_min,
            exclusive_max=exclusive_max,
            multiple_of=multiple_of,
        )

    def jsonschema_boolean(self) -> bool:
        return self.generator.boolean()

    def jsonschema_oneof(self, schemas: Iterable[JsonT]) -> JsonT:
        schema = self.generator.random_element(schemas)
        return self._from_schema(schema)

    def jsonschema_anyof(self, schemas: Iterable[JsonT]) -> JsonT:
        """
        Group all schemas by type. Randomly choose a type.
        Randomly combine one or more of the given schemas of that type
        according to the rules for `allOf`.
        """
        schema_map = dict(
            itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        )
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
        schema_map = dict(
            itertools.groupby(sorted(schemas, key=type_getter), type_getter)
        )
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
        (TODO: is this what the spec intended?)

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
            for _ in range(self._context.max_search):
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
                    f"not: /{schema}/ after {self._context.max_search} attempts."
                ) from e
        else:
            return generator()

    def _get_collection_max(self, min_: int):
        if min_ > self.context.default_collection_max:
            return self.generator.random_int(
                min_,
                min_ + self.context.default_collection_max
            )
        else:
            return self.generator.random_int(
                min_,
                self.context.default_collection_max
            )

    def jsonschema_array(
        self,
        items: Optional[SchemaT] = None,
        min_items: int = 0,
        max_items: Optional[int] = None,
        unique_items: bool = False,
    ) -> List[JsonT]:
        """
        NOTE:
        unlike pure JSON Schema, in OpenAPI arrays must be homogenous
        and schema is required
        """
        if min_items < 0:
            raise ValueError("minItems must be >= 0")
        if (
            max_items is not None and
            min_items > max_items
        ):
            raise ValueError("maxItems must be >= minItems")

        if items is None:
            type_, _ = self._random_type_method()
            items = {"type": type_.value}

        if max_items is None:
            max_items = self._get_collection_max(min_items)

        count = self._safe_random_int(min_items, max_items)
        dup_count = None
        if not unique_items and count > 1:
            dup_count = self.generator.random_int(0, count // 2)
            count -= dup_count

        generated = [
            self.descend_into(self._from_schema)(items)
            for _ in range(count)
        ]
        if not unique_items and dup_count:
            # insert duplicates
            duplicates = self.generator.random_sample(generated, length=dup_count)
            generated.extend(duplicates)
            shuffle(generated)

        return generated

    def jsonschema_object(
        self,
        properties: Optional[Dict[str, SchemaT]] = None,
        property_names: Optional[SchemaT] = None,
        required: Optional[List[str]] = None,
        additional_properties: bool = True,
        min_properties: int = 0,
        max_properties: Optional[int] = None,
    ) -> Dict[str, JsonT]:
        """
        TODO:
        more advanced validation rules in JSONSchema:
        https://json-schema.org/understanding-json-schema/reference/object.html#dependencies

        TODO: readOnly / writeOnly
        """
        if min_properties < 0:
            raise ValueError("minProperties must be >= 0")
        if (
            max_properties is not None and
            min_properties > max_properties
        ):
            raise ValueError("maxProperties must be >= minProperties")
        if (
            required is not None and
            min_properties > len(required)
        ):
            raise UnsatisfiableConstraintsError(
                f"Cannot satisfy minProperties: {min_properties} when "
                f"there are {len(required)} properties in required list."
            )
        if (
            max_properties is not None and
            required is not None and
            max_properties < len(required)
        ):
            raise UnsatisfiableConstraintsError(
                f"Cannot satisfy maxProperties: {max_properties} when "
                f"there are {len(required)} properties in required list."
            )

        if max_properties is None:
            max_properties = self._get_collection_max(min_properties)

        properties = properties or {}
        required = set(required or [])
        generated = {}

        def generate_values(attrs: Iterable[str]) -> None:
            for attr in attrs:
                # NOTE: we use the 'any' schema if not found
                schema = properties.get(attr, {})
                val = self.descend_into(self._from_schema)(schema)
                generated[attr] = val

        # generate 'required' properties
        if required:
            generate_values(required)

        # generate random number of 'non-required' properties
        _count = self.generator.random_int(
            0, min(len(properties), max_properties) - len(generated)
        )
        non_required_attrs = properties.keys() - required
        if non_required_attrs:
            sampled_non_required = self.generator.random_sample(
                properties.keys() - required,
                length=_count,
            )
            generate_values(sampled_non_required)

        # generate 'additional' (not in schema) properties?
        # TODO: bias towards none or few
        if additional_properties:
            _count = self.generator.random_int(
                0, max_properties - len(generated)
            )
            # generate random property names
            # TODO: bias towards short 'key-like' strings if no schema provided
            method = (
                partial(self.jsonschema_string_from_schema, schema=property_names)
                if property_names
                else self.jsonschema_string
            )
            generated_names = [
                method()
                for _ in range(_count)
            ]
            generate_values(generated_names)

        return generated

    @nullable_or_enum
    def jsonschema_basic_type_from_schema(
        self, schema: SchemaT, type_: TypeName
    ) -> JsonT:
        method = getattr(self, self.BASE_METHOD_MAP[type_])
        return method(**method.kwargs_from_schema(schema))

    @nullable_or_enum
    def jsonschema_compound_type_from_schema(
        self, schema: SchemaT, type_: TypeName
    ) -> JsonT:
        return getattr(self, self.BASE_METHOD_MAP[type_])(
            schema[type_.value]
        )

    @nullable_or_enum
    def jsonschema_any_from_schema(
        self, _: SchemaT
    ) -> Optional[JsonT]:
        # NOTE: `any` can still be `nullable` (...or `enum`?)
        # NOTE: `nullable_or_enum` needs the schema arg
        return self.jsonschema_any()

    def _from_schema(self, schema: SchemaT):
        """
        IMPORTANT:
        All recursive calls should use this private method instead of the
        public `from_schema` below so that `context._depth` is not reset.
        """
        try:
            type_ = TypeName(schema["type"])
        except KeyError:
            for type_ in COMPOUND_TYPES:
                if type_.value in schema:
                    return self.jsonschema_compound_type_from_schema(
                        schema, type_
                    )
            else:
                return self.jsonschema_any_from_schema(schema)
        else:
            return self.jsonschema_basic_type_from_schema(schema, type_)

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
    def context(self):
        if self._context is None:
            self._context = Context()
        return self._context

    def from_schema(
        self,
        schema: SchemaT,
        **context
    ):
        self._context = Context(**context)
        try:
            return self._from_schema(schema)
        finally:
            self._context = None
