"""Infer coverage test-case type from a single HTTP call context.

Explicit ``type=`` always wins. Auto-inference only records a type when
confidence is high enough — ambiguous vertical/horizontal TC that look like
the same request must stay explicit in the suite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

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


def infer_test_type(
    *,
    method: str,
    endpoint: str = "",
    expected_status_code: Optional[int] = None,
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

    status = expected_status_code

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

    if status is not None and 200 <= status < 300:
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
