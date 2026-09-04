"""Reusable raw IncorrectBody cases for ``ApiClient.content=`` (LIB-REC-IB).

No entity paths / DTO — consumer passes method + url + headers.
"""

from __future__ import annotations

from typing import Any, Sequence, Tuple, Union

import pytest

from partest.test_types import TypesTestCases as types

ExpectedStatus = Union[int, Sequence[int]]

# Broken JSON + Content-Type mismatch. Gateways vary 400 vs 415 — accept both.
RAW_INCORRECT_BODY_CASES: Tuple[Any, ...] = (
    pytest.param(b'{"a":', "application/json", (400, 415), id="broken_json"),
    pytest.param(b'{"name":"x"}', "text/plain", (400, 415), id="ct_text_plain"),
    pytest.param(b"<nope/>", "application/xml", (400, 415), id="ct_xml"),
)


async def assert_raw_incorrect_body(
    api_client,
    method: str,
    url: str,
    headers: dict,
    *,
    content: bytes,
    content_type: str,
    expected_status_code: ExpectedStatus = (400, 415),
    type: str = types.request_incorrect_body,
    **request_kwargs: Any,
) -> Any:
    """POST/PUT/PATCH raw body via ApiClient so the call counts for coverage."""
    return await api_client.make_request(
        method,
        url,
        headers=headers,
        content=content,
        content_type=content_type,
        expected_status_code=expected_status_code,
        type=type,
        **request_kwargs,
    )
