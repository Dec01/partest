"""Allure-aware assertion helpers."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import allure

from partest.redact import _field_value, _free_text, _is_secret_key, _mark_masked, _scrub_text
from partest.reporting.attach import _attach_failure_masked as attach_failure
from partest.reporting.attach import _attach_check_shown, attach_check, attach_json
from partest.reporting.templates import (
    ErrorTemplates,
    StepTemplates,
    _mismatch_shown,
    _shown,
    _status_shown,
)


def _line_masked(field: str, text: str) -> str:
    """A text value as free text, ``***`` under a secret field name — never parsed as JSON."""
    if _is_secret_key(field) and text:
        return "***"
    return _free_text(text)


def _first_chars(masked: Any, limit: int) -> Any:
    """Shorten after masking, never before: a cut can split a token the mask would find."""
    return masked[:limit] if isinstance(masked, str) else masked


def check_eq(actual: Any, expected: Any, *, field: str = "value", context: str = "") -> None:
    title = StepTemplates.assert_field(field, expected)
    with allure.step(title):
        ok = actual == expected
        attach_check(field=field, expected=expected, actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=field, expected=expected, actual=actual, context=context
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_ne(
    actual: Any, unexpected: Any, *, field: str = "value", context: str = ""
) -> None:
    title = f"Check «{field}» != {_shown(field, unexpected)}"
    with allure.step(title):
        ok = actual != unexpected
        # The attachment gets a wrapper built from the masked value (a second pass in
        # attach_check changes nothing); the message gets the shown label as it is.
        attach_check(
            field=field, expected={"!=": _field_value(field, unexpected)}, actual=actual, ok=ok
        )
        if not ok:
            msg = _mismatch_shown(
                field=field,
                expected=f"!= {_shown(field, unexpected)}",
                actual=_shown(field, actual),
                context=context or "values must differ",
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_true(
    condition: bool,
    *,
    field: str = "condition",
    expected: Any = True,
    actual: Any = None,
    context: str = "",
) -> None:
    with allure.step(StepTemplates.assert_field(field, expected)):
        attach_check(
            field=field,
            expected=expected,
            actual=actual if actual is not None else condition,
            ok=bool(condition),
        )
        if not condition:
            msg = ErrorTemplates.mismatch(
                field=field,
                expected=expected,
                actual=actual if actual is not None else condition,
                context=context,
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_false(
    condition: bool,
    *,
    field: str = "condition",
    expected: Any = False,
    actual: Any = None,
    context: str = "",
) -> None:
    check_true(
        not condition,
        field=field,
        expected=expected,
        actual=actual if actual is not None else condition,
        context=context,
    )


def check_in_list(
    items: Iterable[Any],
    *,
    value: Any,
    field: str = "id",
    list_name: str = "response",
) -> None:
    title = StepTemplates.assert_list_contains(field, value)
    with allure.step(title):
        seq = list(items) if not isinstance(items, list) else items
        if seq and isinstance(seq[0], dict):
            found = any(el.get(field) == value for el in seq)
        else:
            found = value in seq
        attach_json(
            "list_lookup",
            {
                "field": field,
                "value": _field_value(field, value),
                "found": found,
                "list_size": len(seq),
            },
        )
        if not found:
            msg = ErrorTemplates.not_in_list(item=value, field=field, list_name=list_name)
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_isinstance(actual: Any, expected_type: type, *, field: str = "value") -> None:
    with allure.step(f"Check type «{field}» is {expected_type.__name__}"):
        ok = isinstance(actual, expected_type)
        attach_check(
            field=field,
            expected=expected_type.__name__,
            actual=type(actual).__name__,
            ok=ok,
        )
        if not ok:
            msg = ErrorTemplates.type_mismatch(
                field=field, expected_type=expected_type.__name__, actual=actual
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_status(
    actual: Any, expected: Any, *, method: str = "", path: str = ""
) -> None:
    with allure.step(StepTemplates.assert_status(expected)):
        ok = actual == expected
        attach_check(field="status", expected=expected, actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.status(
                expected=expected, actual=actual, method=method, path=path
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_status_in(
    actual: Any,
    expected_set: Sequence[Any],
    *,
    method: str = "",
    path: str = "",
    context: str = "",
) -> None:
    allowed = tuple(expected_set)
    with allure.step(f"Check HTTP status in {_status_shown(allowed)}"):
        ok = actual in allowed
        attach_check(
            field="status", expected=f"in {_status_shown(allowed)}", actual=actual, ok=ok
        )
        if not ok:
            msg = _mismatch_shown(
                field="status",
                expected=f"one of {_status_shown(allowed)}",
                actual=_status_shown(actual),
                context=context or _scrub_text(f"{method} {path}".strip()),
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_in(
    member: Any, container: Any, *, field: str = "membership", context: str = ""
) -> None:
    with allure.step(f"Check: {_shown(field, member)} ∈ {field}"):
        try:
            ok = member in container
        except TypeError:
            ok = False
        attach_check(
            field=field, expected={"contains": _field_value(field, member)}, actual=container,
            ok=ok,
        )
        if not ok:
            msg = _mismatch_shown(
                field=field,
                expected=f"contains {_shown(field, member)}",
                actual=(
                    _shown(field, container)
                    if not isinstance(container, (list, dict))
                    else f"len={len(container)}"
                ),
                context=context,
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_not_in(
    member: Any, container: Any, *, field: str = "membership", context: str = ""
) -> None:
    with allure.step(f"Check: {_shown(field, member)} ∉ {field}"):
        try:
            ok = member not in container
        except TypeError:
            ok = True
        attach_check(
            field=field, expected={"not contains": _field_value(field, member)},
            actual=container, ok=ok,
        )
        if not ok:
            msg = _mismatch_shown(
                field=field,
                expected=f"not contains {_shown(field, member)}",
                actual="found in container",
                context=context,
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_len(obj: Any, expected_len: int, *, field: str = "length") -> None:
    actual_len = len(obj)
    with allure.step(f"Check len({field}) == {expected_len}"):
        ok = actual_len == expected_len
        attach_check(field=field, expected=expected_len, actual=actual_len, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=f"len({field})", expected=expected_len, actual=actual_len
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_not_empty(obj: Any, *, field: str = "value", context: str = "") -> None:
    with allure.step(f"Check «{field}» is not empty"):
        ok = bool(obj)
        attach_check(
            field=field,
            expected="non-empty",
            actual=obj if not isinstance(obj, (list, dict)) else f"len={len(obj)}",
            ok=ok,
        )
        if not ok:
            msg = ErrorTemplates.precondition(
                what=f"«{field}» must not be empty", detail=context
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_is_none(actual: Any, *, field: str = "value") -> None:
    check_eq(actual, None, field=field)


def check_not_startswith(text: Any, prefix: str, *, field: str = "value") -> None:
    s = str(text) if text is not None else ""
    # Text, not a document: masked as free text without reading it as JSON, which would strip
    # the very prefix (a BOM, a space, a line break) this check is about.
    shown_prefix, shown_text = _line_masked(field, prefix), _line_masked(field, s)
    with allure.step(f"Check «{field}» does not start with {shown_prefix!r}"):
        ok = not s.startswith(prefix)
        _attach_check_shown(
            field=field, expected={"not startswith": shown_prefix},
            actual=_first_chars(shown_text, 80), ok=ok,
        )
        if not ok:
            msg = _mismatch_shown(
                field=field,
                expected=f"not startswith {shown_prefix!r}",
                actual=repr(shown_text),
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_between(
    actual: Any,
    low: Any,
    high: Any,
    *,
    field: str = "value",
    inclusive: bool = True,
) -> None:
    ok = (low <= actual <= high) if inclusive else (low <= actual < high)
    exp = f"[{_shown(field, low)}, {_shown(field, high)}{']' if inclusive else ')'}"
    with allure.step(f"Check «{field}» in {exp}"):
        attach_check(
            field=field,
            expected={
                "between": [_field_value(field, low), _field_value(field, high)],
                "inclusive": inclusive,
            },
            actual=actual,
            ok=ok,
        )
        if not ok:
            msg = _mismatch_shown(field=field, expected=exp, actual=_shown(field, actual))
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))


def check_lt(actual: Any, bound: Any, *, field: str = "value") -> None:
    with allure.step(f"Check «{field}» < {_shown(field, bound)}"):
        ok = actual < bound
        attach_check(field=field, expected={"<": _field_value(field, bound)}, actual=actual, ok=ok)
        if not ok:
            msg = _mismatch_shown(
                field=field, expected=f"< {_shown(field, bound)}", actual=_shown(field, actual)
            )
            attach_failure(msg)
            raise _mark_masked(AssertionError(msg))
