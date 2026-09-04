"""Async HTTP API client with coverage hooks and rich status errors."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Optional, Sequence, Tuple, Type, Union

import httpx
from pydantic import BaseModel, RootModel, ValidationError

from partest.coverage import track_api_calls
from partest.http_retry import RetryPolicy
from partest.redact import redact_headers
from partest.utils import ErrorDesc, Logger, StatusCode

BodyType = Optional[Union[Dict[str, Any], list, str, bytes, int, float, bool]]
ExpectedStatus = Optional[Union[int, Sequence[int]]]


@contextmanager
def _step(title: str):
    try:
        import allure

        with allure.step(title):
            yield
    except ImportError:
        yield
    except Exception:
        yield


def _attach_text(name: str, text: str) -> None:
    try:
        import allure

        allure.attach(text, name=name, attachment_type=allure.attachment_type.TEXT)
    except Exception:
        pass


def normalize_expected_status(
    expected: Union[int, Sequence[int]],
) -> Tuple[int, ...]:
    """Normalize int or sequence of ints to a non-empty tuple."""
    if isinstance(expected, bool):  # bool is int subclass — reject
        raise TypeError("expected_status_code must be int or sequence of int, not bool")
    if isinstance(expected, int):
        return (expected,)
    vals = tuple(int(x) for x in expected)
    if not vals:
        raise ValueError("expected_status_code sequence must not be empty")
    return vals


def status_matches(actual: int, expected: Union[int, Sequence[int]]) -> bool:
    return actual in normalize_expected_status(expected)


def format_expected_status(expected: Union[int, Sequence[int]]) -> str:
    vals = normalize_expected_status(expected)
    if len(vals) == 1:
        return str(vals[0])
    return "{" + ", ".join(str(v) for v in vals) + "}"


def _truncate(text: Any, limit: int = 2000) -> str:
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f"... [truncated, {len(s)} chars total]"


def _mask_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    return redact_headers(headers)  # type: ignore[return-value]


def format_status_mismatch(
    *,
    method: str,
    url: str,
    expected: Union[int, Sequence[int]],
    actual: int,
    request_body: Any = None,
    response: Optional[httpx.Response] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Human-readable status mismatch message (safe for CI logs)."""
    resp_body = ""
    if response is not None:
        try:
            resp_body = response.text
        except Exception:
            resp_body = "<unavailable>"
    exp_s = format_expected_status(expected)
    parts = [
        f"HTTP status mismatch: expected {exp_s}, got {actual}",
        f"  {method} {url}",
    ]
    if headers:
        parts.append(f"  request headers: {_mask_headers(headers)}")
    if request_body is not None:
        parts.append(f"  request body: {_truncate(request_body)}")
    if resp_body:
        parts.append(f"  response body: {_truncate(resp_body)}")
    hint = _http_status_hint(actual)
    if hint:
        parts.append(f"  hint: {hint}")
    return "\n".join(parts)


def _http_status_hint(code: int) -> str:
    hints = {
        400: "Bad Request — payload/query validation or malformed body",
        401: "Unauthorized — missing/invalid credentials",
        403: "Forbidden — authenticated but not allowed",
        404: "Not Found — resource or route missing",
        405: "Method Not Allowed — verb not supported on this path",
        409: "Conflict — state/unique/parent constraint",
        415: "Unsupported Media Type — Content-Type not accepted",
        422: "Unprocessable Entity — semantic validation failed",
        429: "Too Many Requests — rate limited",
        500: "Internal Server Error — server-side failure",
        502: "Bad Gateway — upstream failure",
        503: "Service Unavailable — temporary outage",
    }
    return hints.get(code, "")


class ApiClient:
    """Async API client (httpx) with status check, pydantic validation, coverage.

    Lifecycle (L5.1)::

        # per-request client (default — same as 1.3.x)
        api = ApiClient(domain)

        # shared client for session (close explicitly or async with)
        api = ApiClient(domain, shared_client=True)
        ...
        await api.aclose()

        # inject external httpx client (not closed by ApiClient)
        api = ApiClient(domain, client=my_httpx_client)

    Retries (L5.2) default off; enable on client or per call::

        ApiClient(domain, max_retries=2)  # 429/502/503 + network
        await api.make_request(..., max_retries=3)
    """

    def __init__(
        self,
        domain,
        verify=False,
        follow_redirects=True,
        *,
        client: Optional[httpx.AsyncClient] = None,
        shared_client: bool = False,
        timeout: float = 10.0,
        max_retries: int = 0,
        retry_statuses: Sequence[int] = (429, 502, 503),
        retry_backoff: float = 0.4,
        retry_on_network: bool = True,
    ):
        self.domain = domain
        self.verify = verify
        self.follow_redirects = follow_redirects
        self.default_timeout = timeout
        self.logger = Logger()
        self._external_client = client
        self._shared_client = bool(shared_client or client is not None)
        self._owned_client: Optional[httpx.AsyncClient] = None
        self._owns_client = client is None and bool(shared_client)
        self.retry_policy = RetryPolicy(
            max_retries=max(int(max_retries), 0),
            retry_statuses=tuple(retry_statuses),
            retry_on_network=retry_on_network,
            backoff_base=float(retry_backoff),
        )

    async def aclose(self) -> None:
        """Close owned shared httpx client (no-op if external/ephemeral)."""
        if self._owns_client and self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def __aenter__(self) -> "ApiClient":
        if self._shared_client and self._external_client is None:
            await self._ensure_owned_client(self.default_timeout)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def _ensure_owned_client(self, timeout: float) -> httpx.AsyncClient:
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                verify=self.verify,
                follow_redirects=self.follow_redirects,
                timeout=timeout,
            )
            self._owns_client = True
        return self._owned_client

    @track_api_calls
    async def make_request(
        self,
        method: str,
        endpoint: str,
        add_url1: Optional[str] = "",
        add_url2: Optional[str] = "",
        add_url3: Optional[str] = "",
        after_url: Optional[str] = "",
        defining_url: Optional[str] = "",
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Any] = None,
        data: Optional[Any] = None,
        data_type: Optional[Any] = None,
        files: Optional[Dict[str, Any]] = None,
        content: Optional[Union[str, bytes]] = None,
        content_type: Optional[str] = None,
        graphql_query: Optional[str] = None,
        graphql_variables: Optional[Dict[str, Any]] = None,
        expected_status_code: ExpectedStatus = None,
        validate_model: Optional[Type[BaseModel]] = None,
        type: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_statuses: Optional[Sequence[int]] = None,
    ) -> Optional[Any]:
        """Send an HTTP request.

        Parameters
        ----------
        content:
            Raw body sent as-is (bytes or str). Use for broken JSON / transport tests.
            Mutually exclusive in practice with json_data for the wire body.
        content_type:
            Force/override ``Content-Type`` header.
        expected_status_code:
            Single status (``200``) or several allowed (``(400, 415)``).
        type:
            Coverage test-case type. Optional — library infers high-confidence cases
            (405, 404, broken raw body). Pass explicitly for permissions / new /
            update / elements / extra / env (inference is intentionally not 99% there).
        max_retries / retry_statuses:
            Override client-level RetryPolicy for this call only.
        """
        url = f"{self.domain}{endpoint}{add_url1 or ''}{add_url2 or ''}{add_url3 or ''}{after_url or ''}"
        timeout = self.default_timeout if timeout is None else timeout
        headers = dict(headers) if headers else {}

        if graphql_query:
            if method.upper() != "POST":
                self.logger.warning(
                    f"GraphQL requests are usually POST; got {method}."
                )
            graphql_body = {"query": graphql_query.strip()}
            if graphql_variables:
                graphql_body["variables"] = graphql_variables
            json_data = graphql_body
            headers.setdefault("Content-Type", "application/json")

        if content_type:
            headers["Content-Type"] = content_type

        if isinstance(data, dict) and data is not None and json_data is None and content is None and not graphql_query:
            self.logger.warning(
                "Using data=dict(...) instead of json_data= is discouraged; "
                "prefer json_data= for application/json."
            )

        log_body = content if content is not None else (json_data if json_data is not None else data)
        self.logger.log_request(
            method,
            url,
            params=params,
            headers=_mask_headers(headers),
            data=log_body,
            data_type=data_type,
            files=files,
        )

        policy = self.retry_policy
        if max_retries is not None or retry_statuses is not None:
            policy = RetryPolicy(
                max_retries=(
                    self.retry_policy.max_retries
                    if max_retries is None
                    else max(int(max_retries), 0)
                ),
                retry_statuses=(
                    self.retry_policy.retry_statuses
                    if retry_statuses is None
                    else tuple(retry_statuses)
                ),
                retry_on_network=self.retry_policy.retry_on_network,
                backoff_base=self.retry_policy.backoff_base,
                backoff_max=self.retry_policy.backoff_max,
                jitter=self.retry_policy.jitter,
            )

        try:
            response = await self._request_with_retries(
                policy,
                method,
                url,
                params=params,
                headers=headers,
                json_data=json_data,
                data=data,
                data_type=data_type,
                files=files,
                content=content,
                timeout=timeout,
            )
            self.logger.log_response(response)

            if expected_status_code is not None:
                with _step("Validate response"):
                    self._check_status_code(
                        response.status_code,
                        expected_status_code,
                        response,
                        log_body,
                        validate_model,
                        method=method,
                        url=url,
                        headers=headers,
                    )

            if not response.text:
                return ""

            try:
                return response.json()
            except ValueError:
                return response.text

        except httpx.HTTPStatusError as err:
            self.logger.error(
                f"HTTP error {err.response.status_code}: {err.response.text}"
            )
            raise AssertionError(
                f"Server returned {err.response.status_code}: {err.response.text}"
            ) from err

        except httpx.RequestError as e:
            self.logger.error(f"Network/request error: {e}")
            raise

    async def graphql(
        self,
        query: str,
        *,
        variables: Optional[Dict[str, Any]] = None,
        endpoint: str = "/graphql",
        headers: Optional[Dict[str, str]] = None,
        expected_status_code: ExpectedStatus = 200,
        type: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """POST GraphQL query (L5.5 convenience)."""
        return await self.make_request(
            "POST",
            endpoint,
            headers=headers,
            graphql_query=query,
            graphql_variables=variables,
            expected_status_code=expected_status_code,
            type=type,
            **kwargs,
        )

    async def _request_with_retries(
        self,
        policy: RetryPolicy,
        method: str,
        url: str,
        *,
        params,
        headers,
        json_data,
        data,
        data_type,
        files,
        content,
        timeout: float,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._send_once(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json_data=json_data,
                    data=data,
                    data_type=data_type,
                    files=files,
                    content=content,
                    timeout=timeout,
                )
            except httpx.RequestError:
                if policy.should_retry_network(attempt):
                    await policy.sleep(attempt)
                    attempt += 1
                    continue
                raise

            if policy.should_retry_status(response.status_code, attempt):
                await policy.sleep(attempt)
                attempt += 1
                continue
            return response

    async def _send_once(
        self,
        method: str,
        url: str,
        *,
        params,
        headers,
        json_data,
        data,
        data_type,
        files,
        content,
        timeout: float,
    ) -> httpx.Response:
        if self._external_client is not None:
            return await self._perform_request(
                self._external_client,
                method,
                url,
                params=params,
                headers=headers,
                json_data=json_data,
                data=data,
                data_type=data_type,
                files=files,
                content=content,
            )
        if self._shared_client:
            client = await self._ensure_owned_client(timeout)
            return await self._perform_request(
                client,
                method,
                url,
                params=params,
                headers=headers,
                json_data=json_data,
                data=data,
                data_type=data_type,
                files=files,
                content=content,
            )
        async with httpx.AsyncClient(
            verify=self.verify,
            follow_redirects=self.follow_redirects,
            timeout=timeout,
        ) as client:
            return await self._perform_request(
                client,
                method,
                url,
                params=params,
                headers=headers,
                json_data=json_data,
                data=data,
                data_type=data_type,
                files=files,
                content=content,
            )

    async def _perform_request(
        self,
        client,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Any] = None,
        data: Optional[Any] = None,
        data_type: Optional[Any] = None,
        files: Optional[Dict[str, Any]] = None,
        content: Optional[Union[str, bytes]] = None,
    ) -> httpx.Response:
        method_u = method.upper()
        common = {"params": params, "headers": headers}

        if content is not None:
            body = content.encode("utf-8") if isinstance(content, str) else content
            return await client.request(method_u, url, content=body, **common)

        if method_u == "GET":
            return await client.get(url, **common)
        if method_u == "DELETE":
            return await client.delete(url, **common)

        if method_u in {"POST", "PUT", "PATCH"}:
            if json_data is not None:
                return await client.request(
                    method_u, url, json=json_data, files=files, **common
                )
            # legacy form / files path
            kwargs = dict(common)
            if data is not None:
                kwargs["data"] = data
            if files is not None:
                kwargs["files"] = files
            # data_type was historically passed; httpx does not support it — ignore safely
            _ = data_type
            return await client.request(method_u, url, **kwargs)

        raise ValueError(f"Unsupported HTTP method: {method}")

    def _check_status_code(
        self,
        actual_code: int,
        expected_code: Union[int, Sequence[int]],
        response: httpx.Response,
        request_data: Optional[Any],
        validate_model: Optional[Type[BaseModel]],
        *,
        method: str = "",
        url: str = "",
        headers: Optional[Dict[str, str]] = None,
    ):
        exp_s = format_expected_status(expected_code)
        with _step(f"Status code: expected {exp_s}, got {actual_code}"):
            if not status_matches(actual_code, expected_code):
                primary_expected = normalize_expected_status(expected_code)[0]
                error_description = ErrorDesc()
                error_description.codeExpected = primary_expected
                error_description.codeActual = actual_code
                error_description.responseBody = response
                error_description.requestBody = request_data
                self.logger.error(
                    ErrorDesc.status(
                        codeExpected=primary_expected,
                        codeActual=error_description.codeActual,
                        responseBody=error_description.responseBody,
                    )
                )
                req_method = ""
                req_url = ""
                if response is not None and response.request is not None:
                    req_method = response.request.method or ""
                    req_url = str(response.request.url)
                msg = format_status_mismatch(
                    method=method or req_method,
                    url=url or req_url,
                    expected=expected_code,
                    actual=actual_code,
                    request_body=request_data,
                    response=response,
                    headers=headers,
                )
                _attach_text("status_mismatch", msg)
                raise AssertionError(msg)

        with _step("Response body validation"):
            if not validate_model:
                return
            if not response.text:
                try:
                    if 200 <= actual_code < 300:
                        validate_model.validate_success({})
                    else:
                        validate_model.validate_error({})
                except ValidationError as e:
                    self.logger.error(
                        ErrorDesc.validate(
                            validateModel=validate_model,
                            validateData={},
                            error=str(e),
                        )
                    )
                    raise AssertionError(
                        f"Response data validation failed for empty response: {e}"
                    ) from e
                return

            try:
                data = response.json()
                if 200 <= actual_code < 300:
                    validate_model.validate_success(data)
                else:
                    validate_model.validate_error(data)
            except ValueError:
                if (
                    hasattr(validate_model, "ResponseSuccessBody")
                    and issubclass(validate_model.ResponseSuccessBody, RootModel)
                    and validate_model.ResponseSuccessBody.__annotations__.get("root")
                    == str
                ):
                    try:
                        if 200 <= actual_code < 300:
                            validate_model.validate_success(response.text)
                        else:
                            validate_model.validate_error(response.text)
                    except ValidationError as e:
                        self.logger.error(
                            ErrorDesc.validate(
                                validateModel=validate_model,
                                validateData=response.text,
                                error=str(e),
                            )
                        )
                        raise AssertionError(
                            f"Response data validation failed for string response: {e}"
                        ) from e
                else:
                    raise AssertionError(
                        f"Failed to parse JSON response and model does not expect a string: "
                        f"{_truncate(response.text)}"
                    )
            except ValidationError as e:
                self.logger.error(
                    ErrorDesc.validate(
                        validateModel=validate_model,
                        validateData=data,
                        error=str(e),
                    )
                )
                raise AssertionError(f"Response data validation failed: {e}") from e

    def _handle_http_error(self, err: httpx.HTTPStatusError, request_data: Optional[Any]):
        error_description = ErrorDesc()
        error_description.codeExpected = StatusCode.ok
        error_description.codeActual = err.response.status_code
        error_description.responseBody = err.response
        error_description.requestBody = request_data
        self.logger.error(
            ErrorDesc.status(
                codeExpected=StatusCode.ok,
                codeActual=error_description.codeActual,
                responseBody=error_description.responseBody,
            )
        )
        return None


class Get(ApiClient):
    async def get(
        self,
        endpoint,
        add_url1=None,
        add_url2=None,
        add_url3=None,
        after_url=None,
        params=None,
        headers=None,
        data=None,
        data_type=None,
        expected_status_code=None,
        validate_model=None,
        type=None,
    ):
        return await self.make_request(
            "GET",
            endpoint,
            add_url1=add_url1,
            add_url2=add_url2,
            add_url3=add_url3,
            after_url=after_url,
            params=params,
            data=data,
            data_type=data_type,
            headers=headers,
            expected_status_code=expected_status_code,
            validate_model=validate_model,
            type=type,
        )


class Post(ApiClient):
    async def post(
        self,
        endpoint,
        add_url1=None,
        add_url2=None,
        add_url3=None,
        after_url=None,
        params=None,
        json_data=None,
        data=None,
        data_type=None,
        headers=None,
        files=None,
        content=None,
        content_type=None,
        expected_status_code=None,
        validate_model=None,
        type=None,
    ):
        return await self.make_request(
            "POST",
            endpoint,
            add_url1=add_url1,
            add_url2=add_url2,
            add_url3=add_url3,
            after_url=after_url,
            params=params,
            json_data=json_data,
            data=data,
            data_type=data_type,
            headers=headers,
            files=files,
            content=content,
            content_type=content_type,
            expected_status_code=expected_status_code,
            validate_model=validate_model,
            type=type,
        )


class Patch(ApiClient):
    async def patch(
        self,
        endpoint,
        add_url1=None,
        add_url2=None,
        add_url3=None,
        after_url=None,
        params=None,
        json_data=None,
        data=None,
        data_type=None,
        headers=None,
        content=None,
        content_type=None,
        expected_status_code=None,
        validate_model=None,
        type=None,
    ):
        return await self.make_request(
            "PATCH",
            endpoint,
            add_url1=add_url1,
            add_url2=add_url2,
            add_url3=add_url3,
            after_url=after_url,
            params=params,
            json_data=json_data,
            data=data,
            data_type=data_type,
            headers=headers,
            content=content,
            content_type=content_type,
            expected_status_code=expected_status_code,
            validate_model=validate_model,
            type=type,
        )


class Put(ApiClient):
    async def put(
        self,
        endpoint,
        add_url1=None,
        add_url2=None,
        add_url3=None,
        after_url=None,
        params=None,
        json_data=None,
        data=None,
        data_type=None,
        headers=None,
        content=None,
        content_type=None,
        expected_status_code=None,
        validate_model=None,
        type=None,
    ):
        return await self.make_request(
            "PUT",
            endpoint,
            add_url1=add_url1,
            add_url2=add_url2,
            add_url3=add_url3,
            after_url=after_url,
            params=params,
            json_data=json_data,
            data=data,
            data_type=data_type,
            headers=headers,
            content=content,
            content_type=content_type,
            expected_status_code=expected_status_code,
            validate_model=validate_model,
            type=type,
        )


class Delete(ApiClient):
    async def delete(
        self,
        endpoint,
        add_url1=None,
        add_url2=None,
        add_url3=None,
        after_url=None,
        params=None,
        data=None,
        data_type=None,
        headers=None,
        expected_status_code=None,
        validate_model=None,
        type=None,
    ):
        return await self.make_request(
            "DELETE",
            endpoint,
            add_url1=add_url1,
            add_url2=add_url2,
            add_url3=add_url3,
            after_url=after_url,
            params=params,
            data=data,
            data_type=data_type,
            headers=headers,
            expected_status_code=expected_status_code,
            validate_model=validate_model,
            type=type,
        )
