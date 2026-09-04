"""Raw httpx helper for security / transport tests (headers, JWT craft, non-JSON)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Union

import httpx

from partest.client import format_expected_status, status_matches
from partest.reporting.attach import attach_failure, attach_request, attach_response
from partest.reporting.steps import step
from partest.reporting.templates import ErrorTemplates, StepTemplates

ExpectedStatus = Optional[Union[int, Sequence[int]]]


class SecHttp:
    """Per-request AsyncClient for security suites.

    Use when you need response **headers**, raw body, custom Content-Type, or
    crafted Authorization — outside ApiClient JSON helpers.

    ``token_or_manager``: ``TokenManager`` (fresh Bearer each call) or str token.
    """

    def __init__(
        self,
        base_url: str,
        token_or_manager: Any = None,
        *,
        token: Optional[str] = None,
        verify: bool = False,
        timeout: float = 40.0,
        follow_redirects: bool = True,
        instrument: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self._token_manager = None
        self.token = token
        self.verify = verify
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.instrument = instrument
        if token_or_manager is not None:
            if hasattr(token_or_manager, "get_token"):
                self._token_manager = token_or_manager
            else:
                self.token = str(token_or_manager)

    async def _bearer(self) -> Optional[str]:
        if self._token_manager is not None:
            return await self._token_manager.get_token()
        return self.token

    async def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        headers: Optional[Dict[str, str]] = None,
        expected_status: ExpectedStatus = None,
        **kwargs: Any,
    ) -> httpx.Response:
        hdrs = dict(headers or {})
        if auth and "Authorization" not in hdrs:
            bearer = await self._bearer()
            if bearer:
                hdrs["Authorization"] = f"Bearer {bearer}"
        body = kwargs.get("json") or kwargs.get("content") or kwargs.get("data")
        exp_label = (
            format_expected_status(expected_status)
            if expected_status is not None
            else None
        )
        title = StepTemplates.http(method, path, exp_label)

        async def _do() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                verify=self.verify,
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
            ) as client:
                return await client.request(method, path, headers=hdrs, **kwargs)

        if not self.instrument:
            response = await _do()
            if expected_status is not None and not status_matches(
                response.status_code, expected_status
            ):
                raise AssertionError(
                    f"Expected status {format_expected_status(expected_status)}, "
                    f"got {response.status_code}"
                )
            return response

        with step(title):
            attach_request(
                method=method,
                path=path,
                headers=hdrs,
                body=body,
                expected_status=exp_label,
            )
            response = await _do()
            try:
                resp_body: Any = response.json()
            except Exception:
                resp_body = (response.text or "")[:2000]
            attach_response(status=response.status_code, body=resp_body)
            if expected_status is not None and not status_matches(
                response.status_code, expected_status
            ):
                msg = ErrorTemplates.status(
                    expected=format_expected_status(expected_status),
                    actual=response.status_code,
                    method=method,
                    path=path,
                    response_body=resp_body,
                )
                attach_failure(msg)
                raise AssertionError(msg)
            return response

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)
