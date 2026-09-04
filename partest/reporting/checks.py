"""Allure-aware assertion helpers."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import allure

from partest.reporting.attach import attach_check, attach_failure, attach_json
from partest.reporting.templates import ErrorTemplates, StepTemplates


def _safe_json(data: Any, limit: int = 500) -> str:
    import json

    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False, default=str)
        else:
            text = str(data)
    except Exception:
        text = repr(data)
    return text[:limit] + ("…" if len(text) > limit else "")


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
            raise AssertionError(msg)


def check_ne(
    actual: Any, unexpected: Any, *, field: str = "value", context: str = ""
) -> None:
    title = f"Check «{field}» != {unexpected!r}"
    with allure.step(title):
        ok = actual != unexpected
        attach_check(field=field, expected=f"!= {unexpected!r}", actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=field,
                expected=f"!= {unexpected!r}",
                actual=actual,
                context=context or "values must differ",
            )
            attach_failure(msg)
            raise AssertionError(msg)


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
            raise AssertionError(msg)


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
                "value": value,
                "found": found,
                "list_size": len(seq),
            },
        )
        if not found:
            msg = ErrorTemplates.not_in_list(item=value, field=field, list_name=list_name)
            attach_failure(msg)
            raise AssertionError(msg)


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
            raise AssertionError(msg)


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
            raise AssertionError(msg)


def check_status_in(
    actual: Any,
    expected_set: Sequence[Any],
    *,
    method: str = "",
    path: str = "",
    context: str = "",
) -> None:
    allowed = tuple(expected_set)
    with allure.step(f"Check HTTP status in {allowed}"):
        ok = actual in allowed
        attach_check(field="status", expected=f"in {allowed}", actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(
                field="status",
                expected=f"one of {allowed}",
                actual=actual,
                context=context or f"{method} {path}".strip(),
            )
            attach_failure(msg)
            raise AssertionError(msg)


def check_in(
    member: Any, container: Any, *, field: str = "membership", context: str = ""
) -> None:
    with allure.step(f"Check: {member!r} ∈ {field}"):
        try:
            ok = member in container
        except TypeError:
            ok = False
        attach_check(
            field=field, expected=f"contains {member!r}", actual=_safe_json(container), ok=ok
        )
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=field,
                expected=f"contains {member!r}",
                actual=container if not isinstance(container, (list, dict)) else f"len={len(container)}",
                context=context,
            )
            attach_failure(msg)
            raise AssertionError(msg)


def check_not_in(
    member: Any, container: Any, *, field: str = "membership", context: str = ""
) -> None:
    with allure.step(f"Check: {member!r} ∉ {field}"):
        try:
            ok = member not in container
        except TypeError:
            ok = True
        attach_check(
            field=field,
            expected=f"not contains {member!r}",
            actual=_safe_json(container),
            ok=ok,
        )
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=field,
                expected=f"not contains {member!r}",
                actual="found in container",
                context=context,
            )
            attach_failure(msg)
            raise AssertionError(msg)


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
            raise AssertionError(msg)


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
            raise AssertionError(msg)


def check_is_none(actual: Any, *, field: str = "value") -> None:
    check_eq(actual, None, field=field)


def check_not_startswith(text: Any, prefix: str, *, field: str = "value") -> None:
    s = str(text) if text is not None else ""
    with allure.step(f"Check «{field}» does not start with {prefix!r}"):
        ok = not s.startswith(prefix)
        attach_check(
            field=field, expected=f"not startswith {prefix!r}", actual=s[:80], ok=ok
        )
        if not ok:
            msg = ErrorTemplates.mismatch(
                field=field, expected=f"not startswith {prefix!r}", actual=s
            )
            attach_failure(msg)
            raise AssertionError(msg)


def check_between(
    actual: Any,
    low: Any,
    high: Any,
    *,
    field: str = "value",
    inclusive: bool = True,
) -> None:
    if inclusive:
        ok = low <= actual <= high
        exp = f"[{low}, {high}]"
    else:
        ok = low <= actual < high
        exp = f"[{low}, {high})"
    with allure.step(f"Check «{field}» in {exp}"):
        attach_check(field=field, expected=exp, actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(field=field, expected=exp, actual=actual)
            attach_failure(msg)
            raise AssertionError(msg)


def check_lt(actual: Any, bound: Any, *, field: str = "value") -> None:
    with allure.step(f"Check «{field}» < {bound}"):
        ok = actual < bound
        attach_check(field=field, expected=f"< {bound}", actual=actual, ok=ok)
        if not ok:
            msg = ErrorTemplates.mismatch(field=field, expected=f"< {bound}", actual=actual)
            attach_failure(msg)
            raise AssertionError(msg)
