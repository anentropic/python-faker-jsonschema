import math
import operator
import sys
from base64 import b64encode
from decimal import Decimal
from enum import auto, Enum
from functools import partial
from numbers import Number
from typing import Optional, Tuple

from faker.providers import BaseProvider
from hypothesis import strategies as st
from typing_extensions import Final

"""
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


class NumberMode(Enum):
    FLOAT = auto()
    INTEGER = auto()


class JSONSchemaProvider(BaseProvider):

    STRING_FORMAT_SYNONYMS = {
        'uuid': 'uuid4',
        'date-time': 'date_time',
    }

    FLOAT_OFFSET: Final = float("0.{}1".format("0" * (sys.float_info.dig - 2)))

    def base64_bytes(self, min_length: int, max_length: int) -> bytes:
        """
        Base64 values always have length which is a multiple of 4
        and the encoded value will be 4/3 * longer than the original.
        """
        # adjust values to what is possible after encoding
        min_length = min_length + 4 - (min_length % 4)
        max_length = max_length - (max_length % 4)
        if max_length < min_length:
            raise ValueError(
                "max_length must be >= min_length after rounding (base64 "
                "encoded values have length that is a multiple of 4)"
            )
        og_min = math.ceil(min_length * 3 / 4)
        og_max = math.floor(max_length * 3 / 4)
        original = self.generator.pystr(min_chars=og_min, max_chars=og_max)
        return b64encode(original.encode())

    def jsonschema_string(
        self,
        min_length: int = 0,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        format_: Optional[str] = None,
        max_attempts: int = 1250,  # TODO: too big? (tests are slow)
    ) -> str:
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
            max_attempts: if `pattern` or `format_` are used in conjunction
                with `min_length` or `max_length` then we have to search for
                values which meet all constraints. We don't want to search
                forever so we limit the search attempts.

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
            binary: binary data, used to describe files (see Files below)

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
        """
        if max_length is not None and max_length < min_length:
            raise ValueError("max_length must be >= min_length")

        def valid(val) -> bool:
            if len(val) < min_length:
                return False
            if max_length is not None and len(val) > max_length:
                return False
            return True

        def search(generator) -> str:
            for _ in range(max_attempts):
                example = generator()
                if valid(example):
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
                    f"pattern: /{pattern}/ and min_length: {min_length}, "
                    f"max_length: {max_length} after {max_attempts} attempts."
                ) from e
        elif format_ is not None and format_ not in ("byte", "binary"):
            # (returns early)
            # NOTE: we will 'fall through' if no matching faker can be found
            try:
                format_ = self.STRING_FORMAT_SYNONYMS[format_]
            except KeyError:
                pass
            try:
                generator = getattr(self.generator, format_)
            except AttributeError:
                pass
            else:
                try:
                    return search(generator)
                except NoExampleFoundError as e:
                    raise NoExampleFoundError(
                        f"Unable to generate any random value that matches "
                        f"format: {format_} and min_length: {min_length}, "
                        f"max_length: {max_length} after {max_attempts} attempts."
                    ) from e

        if max_length is None:
            # the faker providers all need a max
            max_length = 255

        # special cases:
        # (returns early)
        if format_ == "byte":
            return self.base64_bytes(
                min_length=min_length, max_length=max_length
            )
        elif format_ == "binary":
            length = self.generator.random_int(min_length, max_length)
            return self.generator.binary(length=length)

        if min_length > 5 and max_length > 10:
            # (returns early)
            # use the "lorem ipsum" provider
            # (...has a min length generatable of 5 chars)
            # NOTE: we will 'fall through' if no valid example can be found
            generator = partial(self.generator.text, max_nb_chars=max_length)
            try:
                return search(generator)
            except NoExampleFoundError:
                pass

        return self.generator.pystr(min_chars=min_length, max_chars=max_length)

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
            raise ValueError('min_value and max_value cannot be the same')
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
                    f"exclusive_min: {exclusive_min}, exclusive_max: {exclusive_max}"
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
                    f"cannot satisfy constraints multiple_of: {multiple_of}, "
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
            raise ValueError("invalid value for multiple_of: 0")

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
                    f"cannot satisfy constraints multiple_of: {multiple_of}, "
                    f"minimum: {original_min}, maximum: {original_max}, "
                    f"exclusive_min: {exclusive_min}, exclusive_max: {exclusive_max}"
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
