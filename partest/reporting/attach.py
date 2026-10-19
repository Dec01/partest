"""Allure attach helpers (soft-dep; LIB-16 redaction)."""

from __future__ import annotations

import json
import traceback
from typing import Any, Optional

from partest.redact import (
    _already_masked,
    _body_structure,
    _field_value,
    _scrub_headers,
    _scrub_params,
    _scrub_text,
)

try:
    import allure
    from allure_commons.types import AttachmentType
except ImportError:  # pragma: no cover
    allure = None  # type: ignore
    AttachmentType = None  # type: ignore


def _safe_json(data: Any, limit: int = 8000) -> str:
    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        else:
            text = str(data)
    except Exception:
        text = repr(data)
    if len(text) > limit:
        return text[:limit] + f"\n… [truncated, total {len(text)} chars]"
    return text


def attach_json(name: str, data: Any) -> None:
    if allure is None:
        return
    allure.attach(_safe_json(data), name=name, attachment_type=AttachmentType.JSON)


def attach_text(name: str, text: str) -> None:
    if allure is None:
        return
    allure.attach(str(text), name=name, attachment_type=AttachmentType.TEXT)


def attach_request(
    *,
    method: str,
    path: str,
    headers: Optional[dict] = None,
    body: Any = None,
    params: Any = None,
    expected_status: Any = None,
    redact_body: bool = True,
) -> None:
    """Attach a request. Headers, ``params`` and the query in ``path`` are always masked
    (a secret header or key whole); the body too unless ``redact_body=False``."""
    safe_headers = _scrub_headers(headers) if headers else None
    safe_body = _body_structure(body) if redact_body else body
    attach_json(
        "request",
        {
            "method": method,
            "path": _scrub_text(path),
            "expected_status": expected_status,
            "params": _scrub_params(params),
            "headers": safe_headers,
            "body": safe_body,
        },
    )


def attach_response(
    *,
    status: Any = None,
    body: Any = None,
    note: str = "",
    redact_body: bool = False,
) -> None:
    """Attach a response. The body is attached as received unless ``redact_body=True``.

    Every call inside the package passes ``redact_body=True``. The default stays ``False``
    for a caller's own calls: changing the default of a public function is a major change,
    planned for 3.0.
    """
    safe = _body_structure(body) if redact_body else body
    attach_json("response", {"status": status, "note": note or None, "body": safe})


def attach_check(*, field: str, expected: Any, actual: Any, ok: bool) -> None:
    """Attach ``check:<field>``. Under a secret field name (``token``, ``password`` …) the
    values are ``***``; otherwise they are masked as check values — free text at every level
    (``partest.redact._scrub_check``), the structure kept."""
    attach_json(
        f"check:{field}",
        {
            "field": field,
            "expected": _field_value(field, expected),
            "actual": _field_value(field, actual),
            "passed": ok,
        },
    )


def _attach_check_shown(*, field: str, expected: Any, actual: Any, ok: bool) -> None:
    """:func:`attach_check` for values the caller already masked — attached as they are."""
    attach_json(
        f"check:{field}",
        {"field": field, "expected": expected, "actual": actual, "passed": ok},
    )


def attach_not_measured(*, what: str, reason: str) -> None:
    """The third outcome next to :func:`attach_check`.

    ``passed`` is ``null``, not ``false``: anything scanning attachments for a verdict must
    see that there was none, instead of reading a missing measurement as a pass.
    """
    attach_json(
        f"not_measured:{what}",
        {"what": what, "reason": reason, "outcome": "not_measured", "passed": None},
    )


def attach_failure(message: str, exc: Optional[BaseException] = None) -> None:
    """Attach ``failure_details``: the message and, with *exc*, its formatted traceback.

    The text is masked as free text — URL credentials and secret query values removed,
    then ``redact_text``: an exception text quotes bodies and URLs as they were.
    """
    text = message
    if exc is not None:
        text += "\n\n" + "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    attach_text("failure_details", _scrub_text(text))


def _attach_failure_masked(message: str, exc: Optional[BaseException] = None) -> None:
    """:func:`attach_failure` for a message the package built from already masked parts.

    The message is attached as is. Of the traceback, only the last line of an exception the
    package raised masked — its own ``Type: message`` — is kept as is; the frames (source
    lines such as ``json_data={"password": ...}``) and the chained exceptions are masked. A
    second pass over masked text reads its JSON as free text and breaks it.
    """
    text = message
    if exc is not None:
        trace = traceback.TracebackException.from_exception(exc)
        full = "".join(trace.format())
        own = "".join(trace.format_exception_only())
        notes = "".join(f"{note}\n" for note in getattr(exc, "__notes__", None) or [])
        if notes and own.endswith(notes):
            own = own[: len(own) - len(notes)]  # notes are anyone's text: masked below
        if _already_masked(exc) and full.endswith(own + notes):
            head = full[: len(full) - len(own) - len(notes)]
            shown = _scrub_text(head) + own + (_scrub_text(notes) if notes else "")
        else:
            shown = _scrub_text(full)
        text += "\n\n" + shown
    attach_text("failure_details", text)
