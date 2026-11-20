"""Reading what an AI provider answered, strictly.

A model's answer is untrusted text. ``read_json_object`` accepts exactly one JSON object, alone or
in a single code fence, and refuses everything else with a fixed message: nothing of the answer is
ever repeated in it, so that what the model wrote cannot travel back to it or into a log. What the
object has to look like is the business of the caller.
"""

import json
import math
import re
from typing import Any

_FENCE = re.compile(r"\A```(?:json)?[ \t]*\r?\n(.*)\r?\n```\Z", re.DOTALL)


class AnswerFormatError(Exception):
    """The answer is not one JSON object. ``str(error)`` is a fixed text, safe to show and to send
    back to the model."""


def read_json_object(text: str, max_chars: int) -> object:
    """The value of the one JSON object in ``text``.

    Refused (``AnswerFormatError``): an answer of more than ``max_chars`` characters, anything but
    one object (text around it, a list, a second object), a repeated key, ``NaN`` and ``Infinity``,
    and numbers or nesting too big to read. The result is a ``dict``; it is typed ``object`` so that
    callers check it, as they check everything else.
    """
    stripped = text.strip()
    if len(stripped) > max_chars:
        raise AnswerFormatError("The answer is too long.")
    fenced = _FENCE.match(stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        raise AnswerFormatError(
            "The answer is not one JSON object. Send the object and nothing else."
        )
    try:
        return json.loads(
            stripped,
            object_pairs_hook=_no_repeated_keys,
            parse_constant=_no_constants,
            parse_float=_finite_float,
        )
    except json.JSONDecodeError as error:
        # the decoder's message is one of a few fixed phrases; the position is only numbers
        raise AnswerFormatError(
            f"The answer is not valid JSON ({error.msg}, line {error.lineno}, "
            f"column {error.colno})."
        ) from None
    except _Refused as refused:
        raise AnswerFormatError(str(refused)) from None
    except ValueError, RecursionError:
        raise AnswerFormatError(
            "The answer holds a number or a nesting that cannot be read."
        ) from None


class _Refused(Exception):
    pass


def _no_repeated_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _Refused("A key is given twice in the same object.")
        result[key] = value
    return result


def _no_constants(_: str) -> Any:
    raise _Refused("NaN and Infinity are not allowed.")


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite float")
    return value
