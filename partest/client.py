"""Async HTTP API client with coverage hooks and rich status errors."""

from __future__ import annotations

import json
import warnings
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Sized, Tuple, Type, Union

import httpx
from pydantic import BaseModel, RootModel, ValidationError

from partest.allure_step import allure_step as _step
from partest.coverage import track_api_calls
from partest.http.client import _install_httpx_log_filter, httpx_async_client
from partest.http_retry import RetryPolicy
from partest.redact import (
    _MASKED_MARK,
    _already_masked,
    _body_text,
    _mark_masked,
    _scrub_at,
    _scrub_headers,
    _scrub_text,
)
from partest.tls import (
    VerifySetting,
    certificate_error,
    is_certificate_error,
    note_unknown_tls_host,
    resolve_verify,
)
from partest.utils import ErrorDesc, Logger, StatusCode

BodyType = Optional[Union[Dict[str, Any], list, str, bytes, int, float, bool]]
ExpectedStatus = Optional[Union[int, Sequence[int]]]
# hook(method, endpoint, parsed_body, response) — see ApiClient.add_response_hook
ResponseHook = Callable[[str, str, Any, httpx.Response], None]




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


def _expected_tuple(expected: Any) -> Tuple[int, ...]:
    """The allowed statuses, or ``()`` when none were given or they cannot be read."""
    if expected is None:
        return ()
    try:
        return normalize_expected_status(expected)
    except (TypeError, ValueError):
        return ()


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


_NO_BODY = object()


def _redacted_body(data: Any = _NO_BODY, text: str = "", limit: int = 1000) -> str:
    """A body for a message or a log — the package's one implementation, ``_body_text``."""
    return _body_text(text if data is _NO_BODY else data, limit=limit)


_CONTEXT_ERRORS = 5




def _validation_errors(err: ValidationError) -> List[Dict[str, Any]]:
    """``loc`` / ``type`` / ``msg`` of every error — never the input value, never the URL.

    A message is masked too: a custom validator may quote the value it rejected.
    """
    try:
        errors = err.errors(include_input=False, include_url=False)
    except TypeError:  # pydantic before include_input
        errors = err.errors()
    return [
        {
            "loc": tuple(e.get("loc", ())),
            "type": str(e.get("type", "")),
            "msg": _scrub_text(e.get("msg", "")),
        }
        for e in errors
    ]


def _validation_failure(
    err: ValidationError, *, data: Any = _NO_BODY, text: str = "", what: str = ""
) -> str:
    """Schema failure message without input values: path, type and message per error.

    The first few errors nested below the top level also show their parent object, masked
    and shortened like the body, because the failing element often lies beyond the cut.
    """
    errors = _validation_errors(err)
    lines = []
    for i, e in enumerate(errors):
        path = e["loc"]
        loc = ".".join(str(part) for part in path) or "<root>"
        lines.append(f"  {loc} [{e['type']}]: {e['msg']}")
        if i < _CONTEXT_ERRORS and len(path) > 1 and data is not _NO_BODY:
            # Walked with its path: a parent stored under a secret key is `***`, as it is in
            # the whole body, not shown because the path into it skipped the key.
            parent = _scrub_at(data, path[:-1], _NO_BODY)
            if parent is not _NO_BODY:
                where = ".".join(str(part) for part in path[:-1])
                lines.append(f"    in {where} = {_redacted_body(parent, limit=200)}")
    count = len(errors)
    noun = "error" if count == 1 else "errors"
    head = f"Response data validation failed for {err.title}{what} ({count} {noun}):"
    body = _redacted_body(data, text)
    detail = _truncate("\n".join(lines))
    return f"{head}\n{detail}\nResponse body: {body}"


def _schema_failure(message: str, errors: List[Dict[str, Any]]) -> AssertionError:
    """The ``AssertionError`` of a schema failure, carrying ``validation_errors``."""
    failure = AssertionError(message)
    failure.validation_errors = errors  # type: ignore[attr-defined]
    return _mark_masked(failure)


class StatusMismatchError(AssertionError):
    """The response status is not one the call expected.

    An ``AssertionError``, so a test fails rather than errors, and code that caught
    ``AssertionError`` keeps catching it. ``str()`` is the message of
    :func:`format_status_mismatch` — masked; ``status_code`` is the status that came and
    ``expected`` the allowed statuses, as a tuple.
    """

    def __init__(
        self,
        message: str = "",
        *,
        status_code: Optional[int] = None,
        expected: Sequence[int] = (),
    ):
        super().__init__(message)
        self.status_code = status_code
        self.expected = tuple(expected)

    def __reduce__(self):
        return (
            type(self),
            (self.args[0] if self.args else "",),
            {
                "status_code": self.status_code,
                "expected": self.expected,
                **({_MASKED_MARK: True} if _already_masked(self) else {}),
            },
        )


def _model_name(validate_model: Any) -> str:
    """The model's name for a log line — not the validator instance's repr."""
    model = getattr(validate_model, "ResponseSuccessBody", None)
    if isinstance(model, type):
        return model.__name__
    return type(validate_model).__name__


def _mask_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    return _scrub_headers(headers) or {}


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
    """Human-readable status mismatch message (safe for CI logs).

    Everything in it is masked: a secret request header whole, the bodies walked by key and
    shortened, URL credentials and secret query values removed.
    """
    resp_body = ""
    if response is not None:
        try:
            resp_body = response.text
        except Exception:
            resp_body = "<unavailable>"
    exp_s = format_expected_status(expected)
    parts = [
        f"HTTP status mismatch: expected {exp_s}, got {actual}",
        f"  {method} {_scrub_text(url)}",
    ]
    if headers:
        parts.append(f"  request headers: {_mask_headers(headers)}")
    if request_body is not None:
        parts.append(f"  request body: {_body_text(request_body)}")
    if resp_body:
        parts.append(f"  response body: {_body_text(resp_body)}")
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

    TLS certificates are **verified** unless told otherwise. ``verify=`` takes ``False``, a
    path to a CA bundle, or an :class:`ssl.SSLContext`; leaving it ``None`` reads
    ``PARTEST_TLS_VERIFY`` / ``confpartest.tls_verify`` (see :mod:`partest.tls`), which is
    how a self-signed stand is handled once instead of at every call site.

    ``self.verify`` is what *this* client decided — and it is ``None`` when ``client=`` was
    given, because then TLS belongs to the client that was handed in and httpx does not
    expose its setting. Claiming ``True`` there would be a guess, and the warning about an
    unverified run would be both false-positive and false-negative. The run artifact says
    the same thing now instead of quietly reporting the run as verified: the domain lands
    in ``meta.tlsUnknownHosts``, which is "partest did not decide this one" and not
    "this one was unverified".
    """

    def __init__(
        self,
        domain,
        verify: Optional[VerifySetting] = None,
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
        if client is not None:
            # Not our decision and not readable: say nothing rather than something false.
            if verify is not None:
                warnings.warn(
                    "partest: verify= is ignored when an external client= is given — "
                    "TLS verification belongs to the client you passed in.",
                    UserWarning,
                    stacklevel=2,
                )
            self.verify: Optional[VerifySetting] = None
            # "Not our decision" used to be said to the caller and to nobody else: the
            # artifact of the same run reported `tlsVerified: true`, i.e. verified. The
            # domain is the right thing to name — every call this client makes is built
            # from it — and it goes into a list of its own, so a reader can tell "checked"
            # from "not ours to check" without the flag changing type or meaning.
            note_unknown_tls_host(domain)
        else:
            self.verify = resolve_verify(verify)
        self.follow_redirects = follow_redirects
        self.default_timeout = timeout
        self.logger = Logger()
        # httpx's own INFO line shows every URL as sent; an injected client did not come
        # through the factory that installs the filter.
        _install_httpx_log_filter()
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
        self._response_hooks: List[ResponseHook] = []

    def add_response_hook(self, hook: "ResponseHook") -> None:
        """Register a callback fired after the status check, before schema validation.

        Signature: ``hook(method, endpoint, body, response)`` where ``body`` is the
        parsed JSON (or raw text, or ``None``). Used by
        :class:`partest.tracking.TrackingApiClient` so that a created resource reaches
        the cleanup registry even if ``validate_model`` then rejects the response.

        Hooks must not raise: an exception here would mask the real assertion. Anything
        they raise is swallowed and logged.
        """
        self._response_hooks.append(hook)

    def _log_error_masked(self, message: str) -> None:
        """Log an ERROR line built from parts the package already masked, without masking it
        again (a second pass reads its JSON as free text and breaks it)."""
        log = getattr(self.logger, "_error_masked", None) or self.logger.error
        log(message)

    def _emit_response(self, method, endpoint, body, response) -> None:
        for hook in self._response_hooks:
            try:
                hook(str(method), str(endpoint), body, response)
            except Exception as exc:  # never let a hook hide the real failure
                self.logger.error(f"response hook failed: {exc}")

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
            self._owned_client = httpx_async_client(
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
        if (
            expected_status_code is not None
            and not isinstance(expected_status_code, (int, str, bytes, Sized))
            and isinstance(expected_status_code, Iterable)
        ):
            # A one-shot iterator is read twice below (the step title, then the match):
            # the second reading found it empty and raised. Read it once, here.
            expected_status_code = normalize_expected_status(expected_status_code)
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
                expected=_expected_tuple(expected_status_code),
            )
            self.logger.log_response(response)

            if expected_status_code is not None:
                with _step("Validate response"):
                    # Status first, without the model: hooks must see a 2xx create
                    # before schema validation gets a chance to raise.
                    self._check_status_code(
                        response.status_code,
                        expected_status_code,
                        response,
                        log_body,
                        None,
                        method=method,
                        url=url,
                        headers=headers,
                    )

            body: Any = ""
            if response.text:
                try:
                    body = response.json()
                except ValueError:
                    body = response.text

            self._emit_response(method, endpoint, body, response)

            if expected_status_code is not None and validate_model is not None:
                self._validate_response_body(
                    response.status_code, response, validate_model
                )

            return body

        except httpx.HTTPStatusError as err:
            # The body masked, and the httpx error not chained: its text carries the URL
            # with its query string.
            status_code = err.response.status_code
            status_failure = f"{status_code}: {_body_text(err.response.text)}"
            self._log_error_masked(f"HTTP error {status_failure}")

        except httpx.RequestError as e:
            if is_certificate_error(e):
                # "Network/request error: [SSL: CERTIFICATE_VERIFY_FAILED]" is where a
                # consumer would otherwise meet the changed default, with nothing in it
                # naming the setting that decides.
                explained = certificate_error(e, url=_scrub_text(url), verify=self.verify)
                self.logger.error(str(explained))
                raise explained from e
            self.logger.error(f"Network/request error: {e}")
            raise

        # Reached only from the HTTPStatusError branch (an injected client whose hook calls
        # `raise_for_status`): raised outside it, so no context, and with the status readable.
        allowed = _expected_tuple(expected_status_code)
        if status_code in allowed:
            # The status is the one the call asked for: what refused it is the client, not
            # the service. Not an assertion — a test of "404 is answered" must not fail as if
            # the service had answered something else.
            raise RuntimeError(
                f"an event hook of the injected httpx client rejected the expected status "
                f"{status_code} (raise_for_status in its event_hooks?) — remove it, or "
                f"leave the status check to expected_status_code"
            )
        raise _mark_masked(StatusMismatchError(
            f"Server returned {status_failure}", status_code=status_code, expected=allowed
        ))

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
        expected: Sequence[int] = (),
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
            except httpx.RequestError as exc:
                if policy.should_retry_network(attempt, exc):
                    await policy.sleep(attempt)
                    attempt += 1
                    continue
                raise

            # A status the call expects is the answer, not a transient failure: a test of
            # "the service throttles with 429" must not be retried until it gets a 200.
            if response.status_code not in expected and policy.should_retry_status(
                response.status_code, attempt
            ):
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
        async with httpx_async_client(
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
                self._log_error_masked(
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
                raise _mark_masked(StatusMismatchError(
                    msg,
                    status_code=actual_code,
                    expected=normalize_expected_status(expected_code),
                ))

        self._validate_response_body(actual_code, response, validate_model)

    def _validate_response_body(
        self,
        actual_code: int,
        response: httpx.Response,
        validate_model: Optional[Type[BaseModel]],
    ):
        """Schema validation, split out so callers can run it after their own hooks.

        ``make_request`` checks the status, lets response hooks run (a create id must
        reach the cleanup registry even when the schema then fails), and only then
        validates the body.
        """
        # Every failure below is raised outside the `except` that caught it, so the
        # AssertionError has neither a cause nor a context: pydantic's ValidationError
        # prints `input_value=…` — values from the body, unmasked — and a traceback shows the
        # whole chain. The message already names each failing path, type and message, and
        # the same list, without values, is on the error as `validation_errors`.
        failure: Optional[str] = None
        errors: List[Dict[str, Any]] = []
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
                    failure = _validation_failure(e, data={}, what=" on empty response")
                    errors = _validation_errors(e)
                    self._log_error_masked(
                        ErrorDesc.validate(
                            validateModel=_model_name(validate_model),
                            validateData={},
                            error=failure,
                        )
                    )
                if failure is not None:
                    raise _schema_failure(failure, errors)
                return

            try:
                data = response.json()
                if 200 <= actual_code < 300:
                    validate_model.validate_success(data)
                else:
                    validate_model.validate_error(data)
            except ValueError as err:
                # pydantic's ValidationError is a ValueError: it lands here, not below.
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
                        failure = _validation_failure(
                            e, text=response.text, what=" on string response"
                        )
                        errors = _validation_errors(e)
                        self._log_error_masked(
                            ErrorDesc.validate(
                                validateModel=_model_name(validate_model),
                                validateData=_redacted_body(text=response.text),
                                error=failure,
                            )
                        )
                elif isinstance(err, ValidationError):
                    failure = _validation_failure(err, data=data)
                    errors = _validation_errors(err)
                    self._log_error_masked(
                        ErrorDesc.validate(
                            validateModel=_model_name(validate_model),
                            validateData=_redacted_body(data),
                            error=failure,
                        )
                    )
                else:
                    failure = (
                        f"Failed to parse JSON response and model does not expect a string: "
                        f"{_redacted_body(text=response.text, limit=2000)}"
                    )
            if failure is not None:
                raise _schema_failure(failure, errors)

    def _handle_http_error(self, err: httpx.HTTPStatusError, request_data: Optional[Any]):
        error_description = ErrorDesc()
        error_description.codeExpected = StatusCode.ok
        error_description.codeActual = err.response.status_code
        error_description.responseBody = err.response
        error_description.requestBody = request_data
        self._log_error_masked(
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
