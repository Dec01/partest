"""HTTP call instrumentation for Allure (used by TrackingApiClient)."""

from __future__ import annotations

import re
from typing import Any, Dict

import allure

from partest.reporting.attach import attach_failure, attach_json, attach_request, attach_response
from partest.reporting.templates import (
    StepTemplates,
    explain_conflict,
    format_http_status_failure,
    http_status_hint,
)

# Matches both legacy and 1.0 rich messages
_STATUS_MISMATCH_RE = re.compile(
    r"(?:Expected status code|HTTP status mismatch: expected)\s+(\d+).*?(?:got|but got)\s+(\d+)",
    re.IGNORECASE | re.DOTALL,
)


def _response_body_from_httpx(response: Any) -> Any:
    if response is None:
        return None
    try:
        text = getattr(response, "text", None)
        if text is None or text == "":
            return None
        try:
            return response.json()
        except Exception:
            return text
    except Exception:
        return None


def build_http_step_title(
    method: str,
    endpoint: str,
    *,
    add_url1: str = "",
    add_url2: str = "",
    expected_status_code: Any = None,
) -> str:
    path = f"{endpoint}{add_url1 or ''}{add_url2 or ''}"
    return StepTemplates.http(method, path, expected_status_code)


async def instrumented_make_request(client_call, method, endpoint, *args, **kwargs):
    """Wrap ApiClient.make_request with Allure step + request/response attaches."""
    add1 = kwargs.get("add_url1") or ""
    add2 = kwargs.get("add_url2") or ""
    expected = kwargs.get("expected_status_code")
    headers = kwargs.get("headers")
    body = kwargs.get("json_data")
    if body is None:
        body = kwargs.get("content") if kwargs.get("content") is not None else kwargs.get("data")
    path = f"{endpoint}{add1}{add2}"
    title = StepTemplates.http(str(method), path, expected)

    captured: Dict[str, Any] = {
        "actual_status": None,
        "response_body": None,
        "request_data": body,
    }
    client = getattr(client_call, "__self__", None)
    original_check = None

    if client is not None and hasattr(client, "_check_status_code"):
        original_check = client._check_status_code

        def _capturing_check(actual_code, expected_code, response, request_data, validate_model, **kw):
            captured["actual_status"] = actual_code
            captured["request_data"] = request_data if request_data is not None else body
            captured["response_body"] = _response_body_from_httpx(response)
            return original_check(
                actual_code, expected_code, response, request_data, validate_model, **kw
            )

        client._check_status_code = _capturing_check  # type: ignore[method-assign]

    with allure.step(title):
        attach_request(
            method=str(method),
            path=path,
            headers=headers if isinstance(headers, dict) else None,
            body=body,
            expected_status=expected,
        )
        try:
            result = await client_call(method, endpoint, *args, **kwargs)
        except Exception as exc:
            actual = captured.get("actual_status")
            resp_body = captured.get("response_body")
            req_body = captured.get("request_data")
            original = str(exc)

            m = _STATUS_MISMATCH_RE.search(original)
            if m:
                exp_from_msg, act_from_msg = int(m.group(1)), int(m.group(2))
                if expected is None:
                    expected = exp_from_msg
                if actual is None:
                    actual = act_from_msg

            is_status_mismatch = m is not None or (
                expected is not None and actual is not None and actual != expected
            )

            if is_status_mismatch:
                human = format_http_status_failure(
                    method=str(method),
                    path=path,
                    expected=expected,
                    actual=actual,
                    request_body=req_body,
                    response_body=resp_body,
                    original_message=original,
                )
                attach_response(
                    status=actual if actual is not None else "unknown",
                    body=resp_body,
                    note="status mismatch — see failure_details",
                )
                attach_json(
                    "status_mismatch",
                    {
                        "method": str(method),
                        "path": path,
                        "expected_status": expected,
                        "actual_status": actual,
                        "hint": http_status_hint(actual),
                        "entity_hint": (
                            explain_conflict(path, req_body)
                            if actual == 409 or actual == "409"
                            else None
                        ),
                        "request_body": req_body,
                        "response_body": resp_body,
                    },
                )
                attach_failure(human, exc)
                raise AssertionError(human) from exc

            attach_response(
                status=captured.get("actual_status") or "error",
                body=resp_body,
                note=f"{type(exc).__name__}",
            )
            attach_failure(
                f"Request failed: {type(exc).__name__}: {exc}",
                exc,
            )
            raise
        finally:
            if original_check is not None and client is not None:
                client._check_status_code = original_check  # type: ignore[method-assign]

        if result is None or result == "":
            attach_response(status=expected or "no-body", body=None, note="empty body")
        else:
            attach_response(status=expected, body=result)
        return result
