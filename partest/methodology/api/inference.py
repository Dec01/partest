"""Infer coverage test-case type from a single HTTP call context.

Explicit ``type=`` always wins. Auto-inference only records a type when
confidence is high enough — ambiguous vertical/horizontal TC that look like
the same request must stay explicit in the suite.
"""

from __future__ import annotations

import json
import numbers
from dataclasses import dataclass
from typing import AbstractSet, Any, Dict, Iterable, Optional, Sequence, Sized, Tuple, Union

from partest.test_types import TypesTestCases as T
from partest.test_types import canonicalize_type

# Only auto-apply when confidence >= this (user asked ~99% for dropping type=)
HIGH_CONFIDENCE = 0.99
# Soft suggestions still recorded as inferred meta but not as sole type without flag
MEDIUM_CONFIDENCE = 0.75


@dataclass(frozen=True)
class InferResult:
    test_type: str
    confidence: float
    reason: str
    inferred: bool  # True if library guessed (not user-provided)

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= HIGH_CONFIDENCE


def _is_broken_json_content(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, (bytes, bytearray)):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return True
    elif isinstance(content, str):
        text = content
    else:
        return False
    text = text.strip()
    if not text:
        return False
    try:
        json.loads(text)
        return False
    except (json.JSONDecodeError, TypeError, ValueError):
        return True


def _ct_mismatch_abuse(headers: Optional[Dict[str, str]], content: Any, json_data: Any) -> bool:
    if not headers:
        return False
    ct = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            ct = (v or "").lower()
            break
    if not ct:
        return False
    if content is not None and "application/json" not in ct and "json" not in ct:
        # sending body with non-json CT — transport abuse style
        return True
    if json_data is not None and "json" not in ct and "application/json" not in ct:
        return True
    return False


#: A set larger than this names no usable status: inference must not materialise a
#: ``range(0, 10**9)`` handed to it by mistake.
MAX_STATUS_SET = 1000


def _read_expectation(expected: Any) -> Tuple[Any, Optional[Tuple[int, ...]]]:
    """Split an expectation into ``(status, statuses)``.

    ``status`` is what the single-status rules compare against; ``statuses`` is a set of
    two or more statuses, decided where the status class is first compared — after every
    status-independent signal, which is the order 2.4.0 had for a set (it raised there).
    ``()`` means a collection that names no usable status.

    * a scalar, ``None`` or something that is not a collection — passed through as before;
    * an empty collection — no status given;
    * a one-shot iterator (not ``Sized``) — no status given, and **nothing is read from
      it**: the status check in the client consumes it, and must find it intact;
    * one distinct status — that status, as a scalar: ``(404,)`` is exactly ``404``;
    * more than :data:`MAX_STATUS_SET`, or anything that does not parse — ``()``.

    Parsing is :func:`partest.client.normalize_expected_status` — the reading the status
    check uses; only its errors are turned into "no usable status", because inference is
    a fallback and must not be what fails the test.
    """
    if expected is None or isinstance(expected, (str, bytes, bytearray, numbers.Number)):
        return expected, None
    if not isinstance(expected, Iterable):
        return expected, None
    if not isinstance(expected, Sized):
        return None, None
    if len(expected) == 0:
        return None, None
    if len(expected) > MAX_STATUS_SET:
        return None, ()
    # Imported here: partest.client imports the coverage decorator, which imports this.
    from partest.client import normalize_expected_status

    try:
        values = tuple(sorted(set(normalize_expected_status(expected))))
    except (TypeError, ValueError, OverflowError):
        return None, ()
    if len(values) == 1:
        return values[0], None
    return None, values


def _is_2xx(status: Any) -> bool:
    """``200 <= status < 300`` for anything that compares, ``False`` for what does not."""
    try:
        return bool(200 <= status < 300)
    except TypeError:
        return False


def _format_statuses(statuses: Tuple[int, ...]) -> str:
    """``{200, 201}``; a run of three or more collapses, so ``range(200, 300)`` is ``{200-299}``."""
    runs = []
    for s in statuses:
        if runs and s == runs[-1][1] + 1:
            runs[-1][1] = s
        else:
            runs.append([s, s])
    parts = []
    for lo, hi in runs:
        if hi - lo >= 2:
            parts.append(f"{lo}-{hi}")
        else:
            parts.extend(str(s) for s in range(lo, hi + 1))
    return "{" + ", ".join(parts) + "}"


def _infer_for_status_set(statuses: Tuple[int, ...], **context: Any) -> InferResult:
    """One type for a set of allowed statuses — or an honest "unknown".

    Every status of the set is inferred on its own, with the rest of the call unchanged.
    If they all name the same type, that type stands, at the *lowest* confidence among
    them: ``(401, 403)`` is permissions at 0.75, ``(200, 201)`` is default at 0.4,
    ``(404,)`` is not-found exactly as ``404`` is. If they disagree — ``(200, 400)``, or
    ``(404, 405)``, which share a class and still mean two different cells — the call is
    recorded as ``unknown`` with low confidence and a reason that names the split: a
    request that accepts either outcome does not say which case it tests, and guessing
    one would file it in the wrong cell, silently.
    """
    if not statuses:
        return InferResult(
            T.type_unknown,
            0.2,
            "expected_status_code names no usable status",
            True,
        )
    per_status = [
        (status, infer_test_type(expected_status_code=status, **context))
        for status in statuses
    ]
    types = {result.test_type for _, result in per_status}
    label = _format_statuses(statuses)
    if len(types) == 1:
        weakest = min((result for _, result in per_status), key=lambda r: r.confidence)
        return InferResult(
            weakest.test_type,
            weakest.confidence,
            f"every expected status in {label} agrees: {weakest.reason}",
            True,
        )
    by_type: Dict[str, list] = {}
    for status, result in per_status:
        by_type.setdefault(result.test_type, []).append(status)
    split = ", ".join(
        f"{_format_statuses(tuple(group))} → {test_type}" for test_type, group in by_type.items()
    )
    return InferResult(
        T.type_unknown,
        0.2,
        f"expected statuses {label} imply different types ({split}); pass type= explicitly",
        True,
    )


def infer_test_type(
    *,
    method: str,
    endpoint: str = "",
    expected_status_code: Optional[Union[int, Sequence[int], AbstractSet[int]]] = None,
    params: Any = None,
    json_data: Any = None,
    data: Any = None,
    content: Any = None,
    content_type: Optional[str] = None,
    files: Any = None,
    headers: Optional[Dict[str, str]] = None,
    explicit_type: Optional[str] = None,
    graphql_query: Optional[str] = None,
) -> InferResult:
    """Infer TC type for coverage storage.

    Rules (high confidence only for automatic sole type):
    - explicit_type → always (confidence 1.0)
    - expected 405 → request_not_allowed (0.99)
    - expected 404 → request_not_found (0.99)
    - broken raw JSON content → request_incorrect_body (0.99)
    - CT abuse with body → request_incorrect_body (0.99)
    - files present + POST → still default unless elem (0.5) — needs explicit for upload suite
    - query params that look like filter/sort/page on GET → request_params (0.85)
    - otherwise → request_default with low confidence (0.4) if 2xx expected, else unknown

    A **set** of allowed statuses (``(200, 201)``, ``[400, 415]``, ``range(200, 300)``)
    is decided status by status: if every status yields the same type, that type at the
    lowest confidence among them; otherwise ``unknown`` at 0.2 with a reason naming
    which status implies what. Status-independent signals (a broken raw body, a
    content-type mismatch, list params on a GET, files) decide before a set of several
    statuses is looked at, as in 2.4.0. A one-element set is its status: ``(404,)`` is
    exactly ``404``. An empty set and a one-shot iterator count as no status at all.

    **Decision for 1.0.0:** do not drop the ``type`` parameter. Callers should
    still pass ``type=`` for permissions / new / update / elements / extra / env.
    """
    if explicit_type is not None and str(explicit_type).strip() != "":
        return InferResult(
            test_type=canonicalize_type(explicit_type),
            confidence=1.0,
            reason="explicit type= argument",
            inferred=False,
        )

    # Merge content_type into headers for mismatch detection
    if content_type:
        headers = dict(headers or {})
        headers.setdefault("Content-Type", content_type)

    # A one-element set becomes its status here; a set of several never matches the
    # single-status rules below and is decided at the class rule, after the signals that
    # do not depend on the status — the order 2.4.0 had, so calls that worked keep their cell.
    status, statuses = _read_expectation(expected_status_code)

    if status == 405:
        return InferResult(
            T.request_not_allowed,
            0.99,
            "expected_status_code=405",
            True,
        )

    if status == 404:
        return InferResult(
            T.request_not_found,
            0.99,
            "expected_status_code=404",
            True,
        )

    if status == 415 or status == 400:
        if content is not None and _is_broken_json_content(content):
            return InferResult(
                T.request_incorrect_body,
                0.99,
                "raw broken body + 4xx",
                True,
            )
        if _ct_mismatch_abuse(headers, content, json_data):
            return InferResult(
                T.request_incorrect_body,
                0.99,
                "content-type abuse + 4xx",
                True,
            )

    if content is not None and _is_broken_json_content(content):
        return InferResult(
            T.request_incorrect_body,
            0.99,
            "raw content is not valid JSON",
            True,
        )

    if _ct_mismatch_abuse(headers, content, json_data) and content is not None:
        return InferResult(
            T.request_incorrect_body,
            0.99,
            "content-type does not match JSON body",
            True,
        )

    # Medium confidence — still used as recorded type when nothing else known
    if params and method.upper() == "GET":
        keys = set()
        if isinstance(params, dict):
            keys = {str(k).lower() for k in params.keys()}
        elif isinstance(params, str):
            keys = {p.split("=")[0].lower() for p in params.split("&") if p}
        list_keys = {"page", "size", "limit", "offset", "sort", "order", "filter", "q", "search"}
        if keys & list_keys:
            return InferResult(
                T.request_params,
                0.85,
                "query params suggest list filtering/pagination",
                True,
            )

    if files is not None and method.upper() in {"POST", "PUT", "PATCH"}:
        return InferResult(
            T.request_default,
            0.5,
            "multipart/files present — use explicit type for upload/elements",
            True,
        )

    if statuses is not None:
        return _infer_for_status_set(
            statuses,
            method=method,
            endpoint=endpoint,
            params=params,
            json_data=json_data,
            data=data,
            content=content,
            content_type=content_type,
            files=files,
            headers=headers,
            explicit_type=explicit_type,
            graphql_query=graphql_query,
        )

    if status is not None and _is_2xx(status):
        return InferResult(
            T.request_default,
            0.4,
            "2xx without explicit type — ambiguous (default vs permissions/new/update)",
            True,
        )

    if status is not None and status == 401:
        return InferResult(
            T.request_permissions,
            0.8,
            "expected 401 suggests auth/permissions",
            True,
        )

    if status is not None and status == 403:
        return InferResult(
            T.request_permissions,
            0.75,
            "expected 403 suggests permissions",
            True,
        )

    if graphql_query:
        return InferResult(
            T.request_default,
            0.5,
            "graphql call without explicit type",
            True,
        )

    return InferResult(
        T.type_unknown,
        0.2,
        "insufficient signals for reliable inference",
        True,
    )


def should_require_explicit_type(result: InferResult) -> bool:
    """True when suite authors should still pass type= for correct coverage."""
    return result.confidence < HIGH_CONFIDENCE
