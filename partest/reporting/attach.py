"""Allure attach helpers (soft-dep; LIB-16 redaction)."""

from __future__ import annotations

import json
import traceback
from typing import Any, Optional

from partest.redact import redact_headers, redact_mapping

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
    safe_headers = redact_headers(headers) if headers else None
    safe_body = redact_mapping(body) if redact_body else body
    attach_json(
        "request",
        {
            "method": method,
            "path": path,
            "expected_status": expected_status,
            "params": params,
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
    safe = redact_mapping(body) if redact_body else body
    attach_json("response", {"status": status, "note": note or None, "body": safe})


def attach_check(*, field: str, expected: Any, actual: Any, ok: bool) -> None:
    attach_json(
        f"check:{field}",
        {"field": field, "expected": expected, "actual": actual, "passed": ok},
    )


def attach_failure(message: str, exc: Optional[BaseException] = None) -> None:
    text = message
    if exc is not None:
        text += "\n\n" + "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    attach_text("failure_details", text)
